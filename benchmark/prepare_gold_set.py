"""Resolve the checked-in candidate manifest against ClinVar.

Usage:
  python benchmark/prepare_gold_set.py --output data/benchmarks/gold_variants.csv

The resolver uses NCBI E-utilities, records the retrieval date, and refuses to
silently turn a gene-level or ambiguous hit into an exact-variant gold label.
Review the generated CSV before treating it as a scientific reference set.
"""

from __future__ import annotations

import argparse
import csv
import re
import json
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "benchmark" / "gold_variants.seed.csv"
FIELDS = ["variant_id", "gene", "variant", "label", "clinvar_variation_id", "review_status", "condition", "source_url", "date_retrieved"]
AA3 = {"A":"Ala", "R":"Arg", "N":"Asn", "D":"Asp", "C":"Cys", "Q":"Gln", "E":"Glu", "G":"Gly", "H":"His", "I":"Ile", "L":"Leu", "K":"Lys", "M":"Met", "F":"Phe", "P":"Pro", "S":"Ser", "T":"Thr", "W":"Trp", "Y":"Tyr", "V":"Val"}


def resolve(row: dict[str, str]) -> dict[str, str]:
    gene, variant = row["gene"], row["variant"]
    match = re.fullmatch(r"([A-Z])(\d+)([A-Z])", variant.upper())
    aliases = [variant.upper()]
    if match:
        old, position, new = match.groups()
        aliases.extend([
            f"{AA3.get(old, old)}{position}{AA3.get(new, new)}",
            f"p.{AA3.get(old, old)}{position}{AA3.get(new, new)}",
            f"p.{variant.upper()}",
        ])
    query = f'{gene}[gene] AND (' + " OR ".join(f'"{alias}"' for alias in aliases) + ")"
    params = {"db": "clinvar", "term": query, "retmode": "json", "retmax": 20, "tool": "NeuroCapstoneBenchmark"}
    result = dict(row)
    result["date_retrieved"] = date.today().isoformat()
    result["source_url"] = "https://www.ncbi.nlm.nih.gov/clinvar/?term=" + quote_plus(query)
    try:
        data = _get_json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params)
        ids = data.get("esearchresult", {}).get("idlist", [])
        if not ids:
            result["clinvar_variation_id"] = "UNRESOLVED"
            result["review_status"] = "missing_exact_variant"
            return result
        summary = _get_json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi", {"db": "clinvar", "id": ",".join(ids[:50]), "retmode": "json"})
        expected = {_normalise(alias) for alias in aliases}
        matches = []
        for variation_id in ids:
            doc = summary.get("result", {}).get(str(variation_id), {})
            title = _normalise(doc.get("title", ""))
            protein_change = _normalise(doc.get("protein_change", ""))
            doc_str = _normalise(json.dumps(doc))
            if any(alias in title or alias in protein_change for alias in expected):
                matches.append((str(variation_id), doc))
            elif any(alias in doc_str for alias in expected):
                matches.append((str(variation_id), doc))

        if not matches:
            result["clinvar_variation_id"] = "UNRESOLVED"
            result["review_status"] = "missing_exact_variant"
            return result

        # Prioritize matching records: prefer those with review_status / germline classification
        def score_match(m: tuple[str, dict]) -> int:
            d = m[1]
            score = 0
            if d.get("germline_classification", {}).get("description"):
                score += 10
            rev = str(d.get("review_status", "")).lower()
            if "practice" in rev or "expert" in rev:
                score += 5
            elif "criteria" in rev or "multiple" in rev:
                score += 3
            elif rev and rev != "no assertion criteria provided":
                score += 1
            return score

        matches.sort(key=score_match, reverse=True)
        variation_id, doc = matches[0]
        result["clinvar_variation_id"] = variation_id
        result["review_status"] = str(doc.get("review_status", "retrieved"))
        result["condition"] = str(doc.get("title", row.get("condition", "")))
    except Exception as exc:
        result["clinvar_variation_id"] = "UNRESOLVED"
        result["review_status"] = f"retrieval_error:{type(exc).__name__}"
    return result


def _normalise(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _get_json(endpoint: str, params: dict[str, object]) -> dict:
    """GET JSON using requests or urllib with fallback."""
    try:
        import requests
        query = "&".join(f"{quote_plus(str(key))}={quote_plus(str(value))}" for key, value in params.items())
        resp = requests.get(f"{endpoint}?{query}", headers={"User-Agent": "NeuroCapstoneBenchmark/1.0"}, timeout=30)
        return resp.json()
    except ImportError:
        pass
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    query = "&".join(f"{quote_plus(str(key))}={quote_plus(str(value))}" for key, value in params.items())
    request = Request(f"{endpoint}?{query}", headers={"User-Agent": "NeuroCapstoneBenchmark/1.0"})
    with urlopen(request, context=ctx, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, default=SEED)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "benchmarks" / "gold_variants.csv")
    args = parser.parse_args()
    with args.seed.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    malformed = [index + 2 for index, row in enumerate(rows) if None in row]
    if malformed:
        raise ValueError(f"malformed seed CSV row(s) with extra columns: {malformed}")
    out = [resolve(row) for row in rows]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(out)
    unresolved = [row for row in out if row["clinvar_variation_id"] == "UNRESOLVED"]
    if unresolved:
        audit_path = args.output.with_name(args.output.stem + "_unresolved.csv")
        with audit_path.open("w", newline="", encoding="utf-8") as audit_handle:
            writer = csv.DictWriter(audit_handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(unresolved)
        print(f"wrote {len(out)} rows to {args.output} ({len(unresolved)} unresolved; audit: {audit_path})")
    else:
        print(f"wrote {len(out)} verified rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

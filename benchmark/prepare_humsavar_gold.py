"""Generate a balanced 100-variant neurodegenerative benchmark from UniProt humsavar.txt.

Uses Swiss-Prot/UniProtKB human variant classifications (LP/P vs LB/B) rather
than ClinVar so the benchmark ground truth is independent of the pipeline's
ClinVar lookup stage.
"""
from __future__ import annotations

import argparse
import csv
import re
import ssl
import urllib.request
from collections import defaultdict
from pathlib import Path

HUMSAVAR_URL = "https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/docs/humsavar.txt"
NEURO_GENES = (
    "SNCA", "TTR", "MAPT", "APP", "PSEN1", "PSEN2", "SOD1", "TARDBP",
    "LRRK2", "GBA1", "GRN", "FUS", "PRKN", "PINK1", "VCP", "PARK7",
)
AA3_TO_1 = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
    "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H", "Ile": "I",
    "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
    "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
}


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _round_robin_sample(by_gene: dict[str, list[dict[str, str]]], limit: int) -> list[dict[str, str]]:
    """Deterministically select up to `limit` items spread evenly across genes."""
    picked: list[dict[str, str]] = []
    cursors = {g: 0 for g in NEURO_GENES}
    while len(picked) < limit:
        added_any = False
        for gene in NEURO_GENES:
            items = by_gene.get(gene, [])
            idx = cursors[gene]
            if idx < len(items):
                picked.append(items[idx])
                cursors[gene] = idx + 1
                added_any = True
                if len(picked) >= limit:
                    break
        if not added_any:
            break
    return picked


def build_humsavar_set(out_path: Path, per_class: int = 50) -> list[dict[str, str]]:
    req = urllib.request.Request(HUMSAVAR_URL, headers={"User-Agent": "neuro_capstone-humsavar/1.0"})
    text = urllib.request.urlopen(req, context=_ssl_context(), timeout=60).read().decode("utf-8", errors="replace")

    by_class_gene: dict[str, dict[str, list[dict[str, str]]]] = {
        "pathogenic": defaultdict(list),
        "benign": defaultdict(list),
    }
    seen_ids: set[str] = set()

    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        gene, acc, ftid, aa_chg, cat, dbsnp = parts[:6]
        if gene not in NEURO_GENES or cat not in {"LP/P", "LB/B"}:
            continue
        m = re.match(r"^p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})$", aa_chg)
        if not m:
            continue
        wt3, pos, mut3 = m.groups()
        if wt3 not in AA3_TO_1 or mut3 not in AA3_TO_1 or wt3 == mut3:
            continue
        var = f"{AA3_TO_1[wt3]}{pos}{AA3_TO_1[mut3]}"
        vid = f"{gene.lower()}-{var.lower()}"
        if vid in seen_ids:
            continue
        seen_ids.add(vid)
        label = "pathogenic" if cat == "LP/P" else "benign"
        disease = " ".join(parts[6:]) if len(parts) > 6 else "UniProt humsavar"
        by_class_gene[label][gene].append({
            "variant_id": vid,
            "gene": gene,
            "variant": var,
            "label": label,
            "label_source": f"UniProt humsavar {ftid} ({cat}; {dbsnp})",
            "clinvar_variation_id": ftid,
            "review_status": "humsavar_curated",
            "condition": disease,
            "source_url": f"https://www.uniprot.org/uniprotkb/{acc}/entry",
            "date_retrieved": "2026-11-20",
        })

    selected = _round_robin_sample(by_class_gene["pathogenic"], per_class) + _round_robin_sample(by_class_gene["benign"], per_class)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "variant_id", "gene", "variant", "label", "label_source",
        "clinvar_variation_id", "review_status", "condition", "source_url", "date_retrieved",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Build balanced neurodegenerative dataset from UniProt humsavar.txt")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "benchmarks" / "humsavar_neuro_100.csv",
    )
    parser.add_argument("--per-class", type=int, default=50)
    args = parser.parse_args()
    rows = build_humsavar_set(args.out, per_class=args.per_class)
    n_p = sum(1 for r in rows if r["label"] == "pathogenic")
    n_b = sum(1 for r in rows if r["label"] == "benign")
    print(f"Wrote {len(rows)} variants ({n_p} pathogenic, {n_b} benign) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Deterministic validator for data/benchmarks/gold_variants.csv.

Verifies every row against live NCBI ClinVar, NCBI PubMed, and UniProt
canonical sequences with zero LLM involvement.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import sys
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any


def _ascii_fold(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).lower()

UNIPROT_MAP = {
    "SNCA": ("P37840", 0),
    "TTR": ("P02766", 20),  # +20 signal peptide offset for mature numbering
    "MAPT": ("P10636", 0),  # P10636-1 is 2N4R (758 aa) or P10636-8 (441 aa)
}

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


def _fetch_json(url: str, ctx: ssl.SSLContext) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "neuro_capstone-gold-verifier/1.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_uniprot_sequences(ctx: ssl.SSLContext) -> dict[str, str]:
    """Fetch canonical FASTA sequences from UniProt."""
    seqs: dict[str, str] = {}
    # For MAPT, P10636-8 (441 aa 2N4R CNS tau) is standard for P301L/V337M/R406W numbering
    isoforms = {
        "SNCA": "P37840",
        "TTR": "P02766",
        "MAPT": "P10636-8",
    }
    for gene, acc in isoforms.items():
        url = f"https://rest.uniprot.org/uniprotkb/{acc}.fasta"
        req = urllib.request.Request(url, headers={"User-Agent": "neuro_capstone-gold-verifier/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            lines = resp.read().decode("utf-8").splitlines()
        seqs[gene] = "".join(line.strip() for line in lines if not line.startswith(">"))
    return seqs


def _check_residue(gene: str, variant: str, seq: str) -> tuple[bool, str]:
    """Check if the wild-type amino acid at the variant position matches UniProt."""
    m = re.match(r"^([A-Z])(\d+)([A-Z])$", variant.strip())
    if not m:
        return False, f"unparsed_variant:{variant}"
    wt, pos_str, _mut = m.groups()
    pos = int(pos_str)

    if pos <= len(seq) and seq[pos - 1] == wt:
        return True, f"exact_pos_{pos}={wt}"
    if gene == "TTR" and (pos + 20) <= len(seq) and seq[pos + 20 - 1] == wt:
        return True, f"mature_pos_{pos}(precursor_{pos + 20})={wt}"
    actual = seq[pos - 1] if pos <= len(seq) else "OUT_OF_RANGE"
    return False, f"wt_mismatch:expected_{wt}_found_{actual}_at_{pos}"


def verify_gold_csv(csv_path: Path) -> int:
    ctx = _ssl_context()
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"Loaded {len(rows)} rows from {csv_path}")
    print("Fetching UniProt canonical sequences...")
    seqs = _fetch_uniprot_sequences(ctx)

    # Collect ClinVar IDs
    cids = [r["clinvar_variation_id"] for r in rows if r["clinvar_variation_id"] not in {"", "UNRESOLVED", "NA"}]
    clinvar_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=clinvar&id={','.join(cids)}&retmode=json"
    print(f"Fetching {len(cids)} ClinVar records...")
    clinvar_data = _fetch_json(clinvar_url, ctx).get("result", {})

    # Collect PMIDs
    pmids: list[str] = []
    for r in rows:
        pmids.extend(re.findall(r"PMID:(\d+)", r.get("label_source", "")))
    pmids = sorted(set(pmids))
    pubmed_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={','.join(pmids)}&retmode=json"
    print(f"Fetching {len(pmids)} PubMed records...")
    pubmed_data = _fetch_json(pubmed_url, ctx).get("result", {})

    print("\n" + "=" * 90)
    print("DETERMINISTIC AUDIT REPORT")
    print("=" * 90)

    errors = 0
    warnings = 0

    for r in rows:
        vid = r["variant_id"]
        gene = r["gene"]
        variant = r["variant"]
        label = r["label"]
        cid = r["clinvar_variation_id"]
        source = r.get("label_source", "")

        seq_ok, seq_msg = _check_residue(gene, variant, seqs[gene])
        if not seq_ok:
            if cid == "UNRESOLVED":
                warnings += 1
                print(f"[WARN]  {vid:12} | Residue check: {seq_msg} (excluded UNRESOLVED)")
            else:
                errors += 1
                print(f"[ERROR] {vid:12} | Residue check FAILED: {seq_msg}")

        # ClinVar check
        if cid not in {"", "UNRESOLVED", "NA"}:
            cv = clinvar_data.get(cid, {})
            cv_title = cv.get("title", "")
            cv_class = cv.get("germline_classification", {}).get("description", "")
            if not cv_title:
                errors += 1
                print(f"[ERROR] {vid:12} | ClinVar ID {cid} NOT FOUND")
            else:
                # Check gene in ClinVar title
                if f"({gene})" not in cv_title:
                    errors += 1
                    print(f"[ERROR] {vid:12} | ClinVar ID {cid} gene mismatch: {cv_title}")

                # Check obvious label conflict
                cv_lower = cv_class.lower()
                if label == "pathogenic" and "benign" in cv_lower and "pathogenic" not in cv_lower:
                    errors += 1
                    print(f"[ERROR] {vid:12} | Label={label} vs ClinVar={cv_class}")
                elif label == "benign" and "pathogenic" in cv_lower and "benign" not in cv_lower and "conflicting" not in cv_lower:
                    errors += 1
                    print(f"[ERROR] {vid:12} | Label={label} vs ClinVar={cv_class}")

        # PubMed check
        row_pmids = re.findall(r"PMID:(\d+)", source)
        for p in row_pmids:
            pm = pubmed_data.get(p, {})
            pm_title = pm.get("title", "")
            pm_date = pm.get("pubdate", "")
            if not pm_title:
                errors += 1
                print(f"[ERROR] {vid:12} | PMID:{p} NOT FOUND in PubMed")
                continue

            # Check if title mentions gene or protein or variant or disease keywords
            keywords = {gene.lower(), "synuclein", "transthyretin", "amyloid", "prealbumin", "tau", "frontotemporal", "parkinson", "pick", "alzheimer"}
            if not any(kw in pm_title.lower() for kw in keywords):
                errors += 1
                print(f"[ERROR] {vid:12} | PMID:{p} title does not match {gene} domain: {pm_title!r}")

            # Check if author surname preceding PMID matches first author or co-authors
            m_auth = re.search(rf"([A-Z][a-z]+)\s+et\s+al\.\s+(\d{{4}})\s*\([^)]*PMID:{p}", source)
            if m_auth:
                surname, year = m_auth.groups()
                if year not in pm_date:
                    errors += 1
                    print(f"[ERROR] {vid:12} | PMID:{p} year mismatch: expected {year}, PubMed has {pm_date!r}")
                authors_list = " ".join(a.get("name", "") for a in pm.get("authors", []))
                if _ascii_fold(surname) not in _ascii_fold(authors_list):
                    errors += 1
                    print(f"[ERROR] {vid:12} | PMID:{p} author {surname!r} not in PubMed authors: {authors_list!r}")

    print("-" * 90)
    print(f"Summary: {len(rows)} rows checked | {errors} errors | {warnings} warnings (unresolved artifacts)")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministically verify gold_variants.csv against NCBI/UniProt.")
    parser.add_argument(
        "--gold",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "benchmarks" / "gold_variants.csv",
    )
    args = parser.parse_args()
    return verify_gold_csv(args.gold)


if __name__ == "__main__":
    sys.exit(main())

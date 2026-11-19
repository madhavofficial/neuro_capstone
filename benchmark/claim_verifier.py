"""Verify synthesis claims against supplied literature and clinical records.

Paper citations are valid only when their PMID is present in payload["evidence"].
Clinical-database claims (ClinVar, AlphaMissense, dbSNP) are verified against
their corresponding fields in payload["clinical_context"]. Gene-level context
claims (Open Targets / Ensembl gene associations) are tagged separately and do
not count as exact-variant evidence.
"""

from __future__ import annotations

import re
from typing import Any

from benchmark.benchmark import _clinical_class

_NULL_PMID_TOKENS = {"", "null", "none", "n/a", "na"}


def _normalise_pmid(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text.lower() in _NULL_PMID_TOKENS:
        return None
    match = re.fullmatch(r"(?:PMID:?\s*)?(\d+)", text, flags=re.IGNORECASE)
    return match.group(1) if match else text


def _claimed_class(text: str) -> str:
    lower = text.lower()
    if any(
        token in lower
        for token in (
            "conflicting",
            "uncertain",
            "vus",
            "ambiguous",
            "unknown",
            "indeterminate",
        )
    ):
        return "vus"
    if re.search(r"\b(?:likely\s+)?pathogenic\b", lower) and not re.search(
        r"\b(?:not|non|unlikely)\s+(?:likely\s+)?pathogenic\b", lower
    ):
        return "pathogenic"
    if re.search(r"\b(?:likely\s+)?benign\b", lower) and not re.search(
        r"\b(?:not|non|unlikely)\s+(?:likely\s+)?benign\b", lower
    ):
        return "benign"
    return ""


def _clinvar_tier(text: str) -> str:
    """Return granular ClinVar significance tier so Pathogenic != Likely pathogenic."""
    lower = text.lower()
    if any(
        token in lower
        for token in (
            "conflicting",
            "uncertain",
            "vus",
            "ambiguous",
            "unknown",
            "indeterminate",
        )
    ):
        return "vus"
    has_pathogenic_likely = bool(re.search(r"\bpathogenic\s*/\s*likely\s+pathogenic\b", lower))
    has_benign_likely = bool(re.search(r"\bbenign\s*/\s*likely\s+benign\b", lower))
    if has_pathogenic_likely:
        return "pathogenic/likely_pathogenic"
    if has_benign_likely:
        return "benign/likely_benign"
    if re.search(r"\blikely\s+pathogenic\b", lower) and not re.search(r"\b(?:not|non|unlikely)\s+likely\s+pathogenic\b", lower):
        return "likely_pathogenic"
    if re.search(r"\bpathogenic\b", lower) and not re.search(r"\b(?:not|non|unlikely)\s+pathogenic\b", lower):
        return "pathogenic"
    if re.search(r"\blikely\s+benign\b", lower) and not re.search(r"\b(?:not|non|unlikely)\s+likely\s+benign\b", lower):
        return "likely_benign"
    if re.search(r"\bbenign\b", lower) and not re.search(r"\b(?:not|non|unlikely)\s+benign\b", lower):
        return "benign"
    return ""


def _clinvar_tiers_match(stated: str, expected: str) -> bool:
    if stated == expected:
        return True
    if expected == "pathogenic/likely_pathogenic" and stated in {"pathogenic", "likely_pathogenic"}:
        return True
    if expected == "benign/likely_benign" and stated in {"benign", "likely_benign"}:
        return True
    return False


def _verify_clinvar_claim(text: str, clinvar: dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(clinvar, dict) or not clinvar:
        return False, "clinvar_missing_from_payload"

    expected_tier = _clinvar_tier(str(clinvar.get("clinical_significance") or ""))
    stated_tier = _clinvar_tier(text)
    if not expected_tier or not stated_tier:
        return False, "clinvar_class_missing"
    if not _clinvar_tiers_match(stated_tier, expected_tier):
        return False, f"clinvar_class_mismatch:{stated_tier}!={expected_tier}"

    expected_var_id = str(clinvar.get("variation_id") or "").strip()
    expected_acc = str(clinvar.get("accession") or "").strip()
    expected_acc_base = expected_acc.split(".")[0] if expected_acc else ""

    stated_vcvs = re.findall(r"\bVCV0*\d+(?:\.\d+)?\b", text, flags=re.IGNORECASE)
    stated_var_ids = re.findall(r"variation\s+id\s*[:#]?\s*(\d+)", text, flags=re.IGNORECASE)

    id_matched = False
    if expected_acc:
        for vcv in stated_vcvs:
            vcv_upper = vcv.upper()
            if vcv_upper == expected_acc.upper() or vcv_upper.split(".")[0] == expected_acc_base.upper():
                id_matched = True
            else:
                return False, f"clinvar_accession_mismatch:{vcv}"

    if expected_var_id:
        for vid in stated_var_ids:
            if vid == expected_var_id:
                id_matched = True
            else:
                return False, f"clinvar_variation_id_mismatch:{vid}"
        if not id_matched and re.search(rf"\b{re.escape(expected_var_id)}\b", text):
            id_matched = True

    if not id_matched:
        return False, "clinvar_identifier_missing"

    return True, "clinvar_verified"


def _verify_alphamissense_claim(text: str, am: dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(am, dict) or not am:
        return False, "alphamissense_missing_from_payload"

    raw_score = am.get("score")
    raw_verdict = str(am.get("verdict") or "").strip()
    if raw_score is None or not raw_verdict:
        return False, "alphamissense_fields_incomplete"
    try:
        expected_score = float(raw_score)
    except (TypeError, ValueError):
        return False, "alphamissense_score_invalid"

    expected_verdict = _clinvar_tier(raw_verdict)
    stated_verdict = _clinvar_tier(text)
    if not expected_verdict or not stated_verdict:
        return False, "alphamissense_verdict_missing"
    if not _clinvar_tiers_match(stated_verdict, expected_verdict):
        return False, f"alphamissense_verdict_mismatch:{stated_verdict}!={expected_verdict}"

    # Extract decimal numbers (e.g. 0.7863, 0.794, 0.09) from claim text.
    numbers = [float(m) for m in re.findall(r"(?<![A-Za-z0-9])0?\.\d+|(?<![A-Za-z0-9])1\.0+\b", text)]
    if not numbers:
        return False, "alphamissense_score_missing"
    if not any(abs(num - expected_score) <= 0.005 for num in numbers):
        return False, "alphamissense_score_mismatch"

    return True, "alphamissense_verified"


def _collect_dbsnp_frequencies(dbsnp: dict[str, Any]) -> list[float]:
    freqs: list[float] = []
    dbsnp_data = dbsnp.get("dbsnp_data")
    if not isinstance(dbsnp_data, dict):
        return freqs

    alleles = dbsnp_data.get("alleles")
    if isinstance(alleles, list):
        for entry in alleles:
            if not isinstance(entry, dict):
                continue
            freq_map = entry.get("freq")
            if isinstance(freq_map, dict):
                for val in freq_map.values():
                    if isinstance(val, (int, float)) and not isinstance(val, bool):
                        freqs.append(float(val))
    for key in ("gmaf", "maf", "af"):
        val = dbsnp_data.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            freqs.append(float(val))
    return freqs


def _extract_claimed_frequencies(text: str) -> list[tuple[float, float]]:
    """Return list of (value, tolerance) in proportion units [0, 1]."""
    claimed: list[tuple[float, float]] = []
    # Percentage values like "5%" or "0.1%"
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%", text):
        val = float(match.group(1)) / 100.0
        claimed.append((val, max(0.01, val * 0.25)))
    # Decimal frequencies like "0.001", "0.05", "1e-4" (skip percentages already matched)
    text_no_pct = re.sub(r"\d+(?:\.\d+)?\s*%", " ", text)
    for match in re.finditer(r"(?<![A-Za-z0-9])(0\.\d+(?:e-?\d+)?|\d+(?:\.\d+)?e-\d+)", text_no_pct, flags=re.IGNORECASE):
        val = float(match.group(1))
        claimed.append((val, max(0.001, val * 0.25)))
    return claimed


def _verify_dbsnp_claim(text: str, dbsnp: dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(dbsnp, dict) or not dbsnp:
        return False, "dbsnp_missing_from_payload"

    dbsnp_data = dbsnp.get("dbsnp_data") if isinstance(dbsnp.get("dbsnp_data"), dict) else {}
    expected_rsid = str(dbsnp.get("rsid") or dbsnp_data.get("rsid") or "").strip().lower()
    stated_rsids = [m.lower() for m in re.findall(r"\brs\d+\b", text, flags=re.IGNORECASE)]

    rsid_matched = False
    if stated_rsids:
        if not expected_rsid or any(rs != expected_rsid for rs in stated_rsids):
            return False, f"dbsnp_rsid_mismatch:{stated_rsids}"
        rsid_matched = True

    claimed_freqs = _extract_claimed_frequencies(text)
    freq_matched = False
    if claimed_freqs:
        supplied_freqs = _collect_dbsnp_frequencies(dbsnp)
        if not supplied_freqs:
            return False, "dbsnp_frequencies_missing_from_payload"
        for val, tol in claimed_freqs:
            if not any(abs(val - actual) <= tol for actual in supplied_freqs):
                return False, f"dbsnp_frequency_mismatch:{val}"
        freq_matched = True

    if not rsid_matched and not freq_matched:
        return False, "dbsnp_value_missing"

    return True, "dbsnp_verified"


def _is_gene_context_claim(text: str, claim_type: str, clinical_context: dict[str, Any]) -> bool:
    lower = text.lower()
    ct_lower = claim_type.lower()
    if any(token in lower for token in ("open targets", "opentargets", "gene-level", "gene level")):
        return True
    if "gene_context" in ct_lower or "gene_level" in ct_lower:
        return True
    if "ensembl" in lower and "association" in lower and isinstance(clinical_context.get("gene_level_context"), dict):
        return True
    return False


def _verify_gene_context_claim(text: str, gene_level_context: dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(gene_level_context, dict) or not gene_level_context:
        return False, "gene_level_context_missing"
    lower = text.lower()
    # Collect disease names from Open Targets and Ensembl gene-level context.
    diseases: list[str] = []
    ot = gene_level_context.get("precision_layer_opentargets")
    if isinstance(ot, dict):
        for item in ot.get("top_diseases", []) or []:
            if isinstance(item, dict) and item.get("disease"):
                diseases.append(str(item["disease"]).lower())
    ens = gene_level_context.get("recall_layer_ensembl")
    if isinstance(ens, dict):
        for item in ens.get("top_diseases", []) or []:
            if isinstance(item, dict) and item.get("disease"):
                diseases.append(str(item["disease"]).lower())
    if diseases and any(d in lower for d in diseases if len(d) >= 4):
        return True, "gene_context_verified"
    return False, "gene_context_unmatched"


def verify_claim(
    claim: Any,
    payload: dict[str, Any],
    target: dict[str, str],
) -> dict[str, Any]:
    """Verify a single synthesis claim against supplied literature or clinical records."""
    text = str(claim.get("text", "")) if isinstance(claim, dict) else str(claim or "")
    claim_type = str(claim.get("claim_type", "")) if isinstance(claim, dict) else ""
    raw_pmid = claim.get("pmid", claim.get("citation", claim.get("source_pmid"))) if isinstance(claim, dict) else None
    pmid = _normalise_pmid(raw_pmid)

    evidence = payload.get("evidence", []) if isinstance(payload, dict) else []
    supplied_pmids = {str(item.get("pmid")).strip() for item in evidence if isinstance(item, dict) and item.get("pmid")}
    clinical_context = payload.get("clinical_context") if isinstance(payload, dict) and isinstance(payload.get("clinical_context"), dict) else {}

    scope_mistake = (
        target.get("variant", "").lower() not in text.lower()
        and target.get("gene", "").lower() not in text.lower()
    )

    # 1. Explicit PMID -> paper citation check (must be in payload["evidence"]).
    #    If the sentence also makes an explicit ClinVar / AlphaMissense / dbSNP
    #    claim, verify that clinical statement too so a real PMID cannot hide a
    #    false database claim.
    if pmid is not None:
        paper_valid = pmid in supplied_pmids
        lower = text.lower()
        clinical_valid: bool | None = None
        clinical_reason: str | None = None
        if "clinvar" in lower or re.search(r"\bVCV0*\d+", text, flags=re.IGNORECASE):
            clinical_valid, clinical_reason = _verify_clinvar_claim(text, clinical_context.get("clinvar"))
        elif "alphamissense" in lower:
            clinical_valid, clinical_reason = _verify_alphamissense_claim(text, clinical_context.get("alphamissense_sniper"))
        elif (
            "dbsnp" in lower
            or re.search(r"\brs\d+\b", text, flags=re.IGNORECASE)
            or (
                clinical_context.get("dbsnp")
                and any(tok in lower for tok in ("allele frequency", "minor allele", "maf", "gnomad"))
            )
        ):
            clinical_valid, clinical_reason = _verify_dbsnp_claim(text, clinical_context.get("dbsnp"))

        unsupported = (not paper_valid) or (clinical_valid is False)
        reason = "paper_pmid_verified" if paper_valid else "pmid_not_in_evidence"
        if clinical_valid is False and clinical_reason:
            reason = f"{reason};{clinical_reason}"
        return {
            "pmid": pmid,
            "claim_category": "paper_citation",
            "citation_valid": paper_valid,
            "clinical_field_valid": clinical_valid,
            "gene_context": False,
            "variant_level_evidence": True,
            "unsupported": unsupported,
            "scope_mistake": scope_mistake,
            "reason": reason,
        }

    lower = text.lower()

    # 2. Gene-level context (Open Targets / Ensembl gene associations) -> not exact-variant evidence.
    if _is_gene_context_claim(text, claim_type, clinical_context):
        gc_valid, reason = _verify_gene_context_claim(text, clinical_context.get("gene_level_context"))
        return {
            "pmid": None,
            "claim_category": "gene_context",
            "citation_valid": None,
            "clinical_field_valid": None,
            "gene_context": True,
            "gene_context_valid": gc_valid,
            "variant_level_evidence": False,
            "unsupported": not gc_valid,
            "scope_mistake": False,
            "reason": reason,
        }

    # 3. ClinVar clinical-database claim.
    if "clinvar" in lower or re.search(r"\bVCV0*\d+", text, flags=re.IGNORECASE):
        valid, reason = _verify_clinvar_claim(text, clinical_context.get("clinvar"))
        return {
            "pmid": None,
            "claim_category": "clinical_database",
            "database": "clinvar",
            "citation_valid": None,
            "clinical_field_valid": valid,
            "gene_context": False,
            "variant_level_evidence": True,
            "unsupported": not valid,
            "scope_mistake": scope_mistake,
            "reason": reason,
        }

    # 4. AlphaMissense clinical-database claim.
    if "alphamissense" in lower:
        valid, reason = _verify_alphamissense_claim(text, clinical_context.get("alphamissense_sniper"))
        return {
            "pmid": None,
            "claim_category": "clinical_database",
            "database": "alphamissense",
            "citation_valid": None,
            "clinical_field_valid": valid,
            "gene_context": False,
            "variant_level_evidence": True,
            "unsupported": not valid,
            "scope_mistake": scope_mistake,
            "reason": reason,
        }

    # 5. dbSNP rsID / allele-frequency claim.
    if (
        "dbsnp" in lower
        or re.search(r"\brs\d+\b", text, flags=re.IGNORECASE)
        or any(tok in lower for tok in ("allele frequency", "minor allele", "maf", "gnomad"))
    ):
        valid, reason = _verify_dbsnp_claim(text, clinical_context.get("dbsnp"))
        return {
            "pmid": None,
            "claim_category": "clinical_database",
            "database": "dbsnp",
            "citation_valid": None,
            "clinical_field_valid": valid,
            "gene_context": False,
            "variant_level_evidence": True,
            "unsupported": not valid,
            "scope_mistake": scope_mistake,
            "reason": reason,
        }

    # 6. Ungrounded claim without PMID or verifiable clinical-database record.
    return {
        "pmid": None,
        "claim_category": "ungrounded",
        "citation_valid": False,
        "clinical_field_valid": None,
        "gene_context": False,
        "variant_level_evidence": True,
        "unsupported": True,
        "scope_mistake": scope_mistake,
        "reason": "missing_pmid_and_no_clinical_match",
    }

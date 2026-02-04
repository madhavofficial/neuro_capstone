import requests
import json
import os
import argparse
import sys
import re

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
DATA_DIR = "data/context"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# APIs
ENSEMBL_URL = "https://rest.ensembl.org/phenotype/gene/human/"
OT_GRAPHQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"
UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/search"
VEP_URL = "https://rest.ensembl.org/vep/human/hgvs/"
ENSEMBL_XREF_SYMBOL_URL = "https://rest.ensembl.org/xrefs/symbol/homo_sapiens/"
ENSEMBL_LOOKUP_ID_URL = "https://rest.ensembl.org/lookup/id/"

# The Target: Remote AlphaMissense File (Hg38)
HEADERS = {
    "User-Agent": "NeuroCapstone/1.0",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# 3-Letter Amino Acid Map
AA_MAP = {'A':'Ala','R':'Arg','N':'Asn','D':'Asp','C':'Cys','Q':'Gln','E':'Glu','G':'Gly',
          'H':'His','I':'Ile','L':'Leu','K':'Lys','M':'Met','F':'Phe','P':'Pro','S':'Ser',
          'T':'Thr','W':'Trp','Y':'Tyr','V':'Val'}

# ==========================================
# 1️⃣ IDENTITY LAYER: UniProt
# ==========================================
def get_protein_metadata(query):
    print(f"🔍 [UniProt] Verifying Identity for: '{query}'...")
    search_query = f"(gene:{query} OR protein_name:{query}) AND organism_id:9606 AND reviewed:true"
    params = {"query": search_query, "format": "json", "size": 1}
    
    try:
        response = requests.get(UNIPROT_URL, params=params, headers=HEADERS, timeout=10)
        data = response.json()
        
        if not data.get("results"):
            print("❌ [UniProt] No reviewed human protein found.")
            return None, None, None

        result = data["results"][0]
        uniprot_id = result["primaryAccession"]
        try: gene_name = result["genes"][0]["geneName"]["value"]
        except: gene_name = query
        sequence = result["sequence"]["value"]

        print(f"✅ [UniProt] Confirmed: {gene_name} (ID: {uniprot_id})")
        return uniprot_id, sequence, gene_name
    except Exception as e:
        print(f"❌ [UniProt] Error: {e}")
        return None, None, None

# ==========================================
# 2️⃣ SNIPER LAYER: AlphaMissense (Raw Access)
# ==========================================
# ==========================================
# 2️⃣ SNIPER LAYER: AlphaMissense (API Sniper)
# ==========================================
def _get_uniprot_signal_peptide_length(uniprot_id: str) -> int | None:
    """Best-effort: fetch signal peptide length from UniProt features.

    Returns length (end position) if available, else None.
    """
    if not uniprot_id:
        return None
    url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        feats = data.get("features")
        if not isinstance(feats, list):
            return None
        for feat in feats:
            if not isinstance(feat, dict):
                continue
            # Typical type strings: "Signal peptide" / "SIGNAL"
            ftype = str(feat.get("type", "")).lower()
            if "signal" not in ftype:
                continue
            loc = feat.get("location")
            if not isinstance(loc, dict):
                continue
            end = loc.get("end")
            if isinstance(end, dict) and "value" in end:
                return int(end["value"])
        return None
    except Exception:
        return None


def _uniprot_starts_with_m(uniprot_id: str) -> bool | None:
    """Best-effort check for N-terminal methionine in UniProt sequence."""
    if not uniprot_id:
        return None
    url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        seq = data.get("sequence", {}).get("value")
        if isinstance(seq, str) and seq:
            return seq[0] == "M"
        return None
    except Exception:
        return None


def _get_ensembl_protein_id_from_symbol(gene_symbol: str) -> str | None:
    """Resolve ENSP (Ensembl protein) ID for a gene symbol using Ensembl lookup.

    Returns the canonical transcript's protein translation ID when available.
    """
    if not gene_symbol:
        return None
    try:
        xref_url = f"{ENSEMBL_XREF_SYMBOL_URL}{gene_symbol}"
        resp = requests.get(xref_url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        xrefs = resp.json()
        ensg = None
        if isinstance(xrefs, list):
            for item in xrefs:
                if isinstance(item, dict) and str(item.get("id", "")).startswith("ENSG"):
                    ensg = item["id"]
                    break
        if not ensg:
            return None

        lookup_url = f"{ENSEMBL_LOOKUP_ID_URL}{ensg}"
        resp = requests.get(lookup_url, params={"expand": 1}, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        gene_obj = resp.json()
        transcripts = gene_obj.get("Transcript")
        if not isinstance(transcripts, list):
            return None

        canonical = None
        for tr in transcripts:
            if isinstance(tr, dict) and tr.get("is_canonical") == 1:
                canonical = tr
                break
        if canonical is None and transcripts:
            canonical = transcripts[0] if isinstance(transcripts[0], dict) else None

        if not canonical:
            return None
        translation = canonical.get("Translation")
        if isinstance(translation, dict) and translation.get("id"):
            return str(translation["id"])
        return None
    except Exception:
        return None


def _query_vep_hgvs(hgvs: str):
    url = f"{VEP_URL}{hgvs}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if not data:
        return None
    return data[0]

def get_genomic_coordinates(gene, old_aa, pos, new_aa, *, uniprot_id: str | None = None):
    """
    Helper: Converts a protein-level mutation into hg38 genomic coordinates.

    Returns a dict with at least: {chrom, pos}. When Ensembl VEP provides alleles,
    also includes {ref, alt} for more precise downstream queries.
    """
    print(f"   🗺️  [Mapping] Converting {gene} {old_aa}{pos}{new_aa} to Genome Coordinates...")
    
    aa_old = AA_MAP.get(old_aa, "")
    aa_new = AA_MAP.get(new_aa, "")
    if not aa_old or not aa_new:
        return None

    # Some proteins (secreted/mature peptides) are commonly reported using mature-protein
    # numbering (i.e. after the signal peptide). If VEP fails at the reported position,
    # try adding the UniProt signal peptide length as an offset.
    signal_len = _get_uniprot_signal_peptide_length(uniprot_id) if uniprot_id else None
    starts_with_m = _uniprot_starts_with_m(uniprot_id) if uniprot_id else None
    if signal_len:
        print(f"      ℹ️  Detected UniProt signal peptide length: {signal_len}. Will try position offsets.")
    if starts_with_m:
        print("      ℹ️  UniProt sequence starts with 'M'. Will also try +1 position (initiator Met cleavage numbering).")

    ensp = _get_ensembl_protein_id_from_symbol(gene)

    # Try multiple identifiers because Ensembl VEP HGVS resolver is picky.
    identifiers: list[str] = [gene]
    if ensp:
        identifiers.append(ensp)
    if uniprot_id:
        identifiers.append(uniprot_id)

    positions: list[int] = [int(pos)]
    if starts_with_m and (int(pos) + 1) not in positions:
        positions.append(int(pos) + 1)
    if signal_len:
        cand = int(pos) + int(signal_len)
        if cand not in positions:
            positions.append(cand)
        if starts_with_m:
            cand2 = int(pos) + int(signal_len) + 1
            if cand2 not in positions:
                positions.append(cand2)

    try:
        res = None
        for ident in identifiers:
            for try_pos in positions:
                hgvs = f"{ident}:p.{aa_old}{try_pos}{aa_new}"
                out = _query_vep_hgvs(hgvs)
                if out:
                    if try_pos != int(pos):
                        print(f"      ✅ Resolved using offset position: {pos} -> {try_pos} via {ident}")
                    res = out
                    break
            if res:
                break
        if not res:
            return None

        chrom = res.get('seq_region_name')  # Ensembl returns e.g. '18'
        start = res.get('start')
        allele_string = res.get('allele_string')  # often like 'G/A'

        if chrom is None or start is None:
            return None

        mapping = {"chrom": str(chrom), "pos": int(start)}
        if isinstance(allele_string, str) and "/" in allele_string:
            ref, alt = allele_string.split("/", 1)
            if ref and alt and len(ref) == 1 and len(alt) == 1:
                mapping["ref"] = ref
                mapping["alt"] = alt

        if "ref" in mapping and "alt" in mapping:
            print(f"      📍 Mapped to: chr{mapping['chrom']}:{mapping['pos']} {mapping['ref']}>{mapping['alt']}")
        else:
            print(f"      📍 Mapped to: chr{mapping['chrom']}:{mapping['pos']}")

        return mapping
        
    except Exception as e:
        print(f"      ⚠️ Mapping Error: {e}")
        return None

def get_alphamissense_sniper(gene, variant_code, *, uniprot_id: str | None = None):
    """
    THE API SNIPER (MyVariant.info) - ROBUST VERSION
    Handles hg38 and nested list responses from the API.
    """
    if not variant_code: return None

    # 1. Parse Variant
    match = re.match(r"([A-Z])(\d+)([A-Z])", variant_code.upper())
    if not match: return None
    old_aa, pos, new_aa = match.groups()

    # 2. Get Coordinates (hg38)
    mapping = get_genomic_coordinates(gene, old_aa, pos, new_aa, uniprot_id=uniprot_id)
    if not mapping:
        print("      ⚠️ Could not resolve genomic coordinates. Skipping Sniper. (This can happen when variants are reported using mature-protein numbering.)")
        return None

    chrom, loc = mapping["chrom"], mapping["pos"]

    print(f"   🎯 [Sniper] Querying MyVariant Cloud at chr{chrom}:{loc} (hg38)...")
    
    # 3. Query MyVariant
    url = "https://myvariant.info/v1/query"

    # MyVariant indexing can vary; try HGVS g. and plain coordinate queries.
    queries: list[str] = []
    if mapping.get("ref") and mapping.get("alt"):
        queries.append(f"chr{chrom}:g.{loc}{mapping['ref']}>{mapping['alt']}")
    queries.append(f"chr{chrom}:{loc}")
    
    try:
        hit = None
        for q in queries:
            params = {
                "q": q,
                "fields": "alphamissense,dbnsfp.alphamissense",
                "assembly": "hg38",
                "size": 1,
            }
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
            data = resp.json()
            if "hits" in data and len(data["hits"]) > 0:
                hit = data["hits"][0]
                break

        if hit:
            
            # 4. Extract Data Block
            am_data = None
            if "alphamissense" in hit:
                am_data = hit["alphamissense"]
            elif "dbnsfp" in hit and "alphamissense" in hit["dbnsfp"]:
                am_data = hit["dbnsfp"]["alphamissense"]

            if am_data:
                # API Quirk: am_data might be a list of dicts
                if isinstance(am_data, list):
                    am_data = am_data[0] # Take the first record
                
                # API Quirk: The score itself might be a list [0.98, 0.99]
                raw_score = am_data.get("score", am_data.get("pathogenicity", 0))
                
                final_score = 0.0
                if isinstance(raw_score, list):
                    final_score = float(max(raw_score)) # Take the highest risk score
                else:
                    final_score = float(raw_score)
                
                verdict = "Pathogenic" if final_score > 0.56 else "Benign"
                
                print(f"      ✅ HIT: AlphaMissense Score {final_score} ({verdict})")
                return {"score": final_score, "verdict": verdict}
            else:
                print("      ℹ️  Variant found, but AlphaMissense score not in DB.")
        else:
            print("      ❌ No variant record found (Double-check coordinate mapping / MyVariant coverage).")

    except Exception as e:
        print(f"      ❌ Sniper Error: {e}")
        return None
        
    return None


def get_clinvar_myvariant(gene: str, variant_code: str, *, uniprot_id: str | None = None):
    """Fetch ClinVar annotations for a protein variant via Ensembl VEP -> MyVariant.

    Returns a small normalized dict (or None if unavailable).
    """
    if not variant_code:
        return None

    match = re.match(r"([A-Z])(\d+)([A-Z])", variant_code.upper())
    if not match:
        return None
    old_aa, pos, new_aa = match.groups()

    mapping = get_genomic_coordinates(gene, old_aa, pos, new_aa, uniprot_id=uniprot_id)
    if not mapping:
        return None

    chrom, loc = mapping["chrom"], mapping["pos"]
    queries: list[str] = []
    if mapping.get("ref") and mapping.get("alt"):
        queries.append(f"chr{chrom}:g.{loc}{mapping['ref']}>{mapping['alt']}")
    queries.append(f"chr{chrom}:{loc}")

    print(f"   🧬 [ClinVar] Querying MyVariant (hg38)...")

    url = "https://myvariant.info/v1/query"
    try:
        hit = None
        for q in queries:
            params = {
                "q": q,
                "fields": "clinvar,dbnsfp.clinvar",
                "assembly": "hg38",
                "size": 1,
            }
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
            data = resp.json()
            if "hits" in data and data["hits"]:
                hit = data["hits"][0]
                break

        if not hit:
            print("      ℹ️  No ClinVar record found.")
            return None
        clinvar = hit.get("clinvar")
        if not clinvar and "dbnsfp" in hit:
            clinvar = hit["dbnsfp"].get("clinvar")
        if not clinvar:
            print("      ℹ️  Variant found, but ClinVar data not present.")
            return None

        # Normalize common fields while keeping raw for debugging.
        rcv = clinvar.get("rcv") if isinstance(clinvar, dict) else None
        if isinstance(rcv, list) and rcv:
            rcv0 = rcv[0]
        elif isinstance(rcv, dict):
            rcv0 = rcv
        else:
            rcv0 = None

        sig = None
        conditions: list[str] = []
        accession = None
        review_status = None

        if isinstance(rcv0, dict):
            accession = rcv0.get("accession")
            sig = rcv0.get("clinical_significance")
            if isinstance(sig, dict):
                review_status = sig.get("review_status")
                sig = sig.get("description")
            conditions_raw = rcv0.get("conditions")
            if isinstance(conditions_raw, dict) and "name" in conditions_raw:
                conditions.append(str(conditions_raw["name"]))
            elif isinstance(conditions_raw, list):
                for item in conditions_raw:
                    if isinstance(item, dict) and item.get("name"):
                        conditions.append(str(item["name"]))

        normalized = {
            "accession": accession,
            "clinical_significance": sig,
            "review_status": review_status,
            "conditions": conditions[:10],
            "mapping": mapping,
            "raw": clinvar,
        }
        if sig:
            print(f"      ✅ ClinVar: {sig}{' (' + accession + ')' if accession else ''}")
        return normalized
    except Exception as e:
        print(f"      ❌ ClinVar query error: {e}")
        return None
# ==========================================
# 3️⃣ RECALL LAYER: Ensembl
# ==========================================
def get_ensembl_phenotypes(gene_symbol):
    print(f"   🔹 [Ensembl] Querying Aggregated Phenotypes (Recall Layer)...")
    url = f"{ENSEMBL_URL}{gene_symbol}"
    params = {"include_associated": 1}
    
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            if not data: return []
            
            disease_counts = {}
            for entry in data:
                desc = entry.get('description')
                if desc:
                    if desc not in disease_counts:
                        disease_counts[desc] = 0
                    disease_counts[desc] += 1
            
            sorted_diseases = sorted(disease_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            
            results = [{"disease": name, "count": count} for name, count in sorted_diseases]
            print(f"      ✅ Success! Found {len(data)} associations.")
            return results
        else:
            return []
    except Exception:
        return []

# ==========================================
# 4️⃣ PRECISION LAYER: Open Targets
# ==========================================
def get_opentargets_validation(gene_symbol):
    print(f"   🔸 [OpenTargets] Querying Validation Scores (Precision Layer)...")
    
    search_query = """
    query search($queryString: String!) {
      search(queryString: $queryString, entityNames: ["target"], page: {index: 0, size: 1}) {
        hits { id }
      }
    }
    """
    try:
        resp = requests.post(OT_GRAPHQL_URL, json={"query": search_query, "variables": {"queryString": gene_symbol}}, headers=HEADERS, timeout=10)
        hits = resp.json().get("data", {}).get("search", {}).get("hits", [])
        
        if not hits: return []
        target_id = hits[0]["id"]
        
        data_query = """
        query target($id: String!) {
          target(ensemblId: $id) {
            associatedDiseases {
              rows {
                disease { name }
                score
              }
            }
          }
        }
        """
        resp = requests.post(OT_GRAPHQL_URL, json={"query": data_query, "variables": {"id": target_id}}, headers=HEADERS, timeout=10)
        rows = resp.json().get("data", {}).get("target", {}).get("associatedDiseases", {}).get("rows", [])
        
        results = []
        for item in sorted(rows, key=lambda x: x['score'], reverse=True)[:5]:
            results.append({"disease": item['disease']['name'], "overall_score": round(item['score'], 4)})
            
        print(f"      ✅ Success! Validated {len(rows)} targets.")
        return results
    except Exception:
        return []

# ==========================================
# 🚀 MAIN CONTROLLER
# ==========================================
def fetch_all_context(protein_name, variant_input=None):
    print(f"\n--- 🌍 STARTING ROBUST CONTEXT RETRIEVAL: {protein_name} ---")
    
    # 1. Identity Verification
    uid, seq, gene = get_protein_metadata(protein_name)
    if not uid: return None

    # 2. Variant-layer (AlphaMissense + ClinVar via MyVariant)
    am_data = None
    clinvar_data = None
    if variant_input:
        # Note: these functions do their own VEP mapping; kept separate for simplicity.
        # If you want to avoid repeated mapping logs entirely, we can refactor to compute mapping once.
        am_data = get_alphamissense_sniper(gene, variant_input, uniprot_id=uid)
        clinvar_data = get_clinvar_myvariant(gene, variant_input, uniprot_id=uid)
        
        # 🚦 FILTER LOGIC
        if am_data and am_data['score'] < 0.2:
            print(f"\n   ⚠️  [FILTER WARNING] Variant {variant_input} appears BENIGN.")
            print("       The structural analysis may yield negative results.\n")

    print("🏥 [Context] Executing Ensembl (Recall) + OpenTargets (Precision)...")
    
    # 3. Data Fetch
    recall_data = get_ensembl_phenotypes(gene)
    precision_data = get_opentargets_validation(gene)
    
    # 4. Structure the Final Report
    context_data = {
        "gene": gene,
        "uniprot_id": uid,
        "variant": variant_input,
        "alphamissense_sniper": am_data, # <--- Specific field for Sniper results
        "clinvar": clinvar_data,
        "medical_context": {
            "recall_layer_ensembl": recall_data,
            "precision_layer_opentargets": precision_data
        }
    }
    
    label = f"{gene}_{variant_input}" if variant_input else gene
    save_path = os.path.join(DATA_DIR, f"{label}_context.json")
    with open(save_path, "w") as f:
        json.dump(context_data, f, indent=4)
        
    print(f"✅ Context saved to {save_path}")
    return context_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("protein", type=str, help="Gene Symbol (e.g., SNCA)")
    parser.add_argument("--variant", type=str, help="Optional Variant (e.g., A53T)", default=None)
    args = parser.parse_args()
    
    fetch_all_context(args.protein, args.variant)

"""
=============================================================================
🧬 MODULE: Context Retrieval Engine (Stage 1) - SNIPER EDITION
=============================================================================
PURPOSE: 
    Retrieves, filters, and validates clinical knowledge for a target protein.
    Features the "Sniper Method" for high-precision, offline-capable 
    Pathogenicity verification.

ARCHITECTURAL LOGIC:
    1.  IDENTITY LAYER (UniProt): Verifies Gene & Species.
    
        2.  SNIPER LAYER (Ensembl VEP + MyVariant.info):
                - Uses Ensembl VEP to map Protein Mutation (A53T) -> Genomic Coordinates.
                - Uses MyVariant.info to retrieve AlphaMissense annotations (when available)
                    via a lightweight cloud query, avoiding large local downloads.
    
    3.  RECALL LAYER (Ensembl): Broad disease association search.
    4.  PRECISION LAYER (Open Targets): Validated therapeutic targets.

DATABASES / TOOLS USED (AND WHY):
        - UniProt REST API: identity verification (reviewed human proteins + sequence).
        - Ensembl REST (Phenotype): broad phenotype/disease associations (recall layer).
        - Ensembl VEP REST: deterministic variant-to-genome coordinate mapping (hg38).
        - MyVariant.info API: fast lookup for AlphaMissense annotations without hosting
            the full dataset locally.
        - Open Targets GraphQL API: ranked evidence scores for target–disease links
            (precision layer).
        - Local JSON files (data/context): simple, reproducible storage with no database
            dependency for this capstone pipeline.

OUTPUT:
    - JSON Context file with raw AlphaMissense scores.
=============================================================================
"""
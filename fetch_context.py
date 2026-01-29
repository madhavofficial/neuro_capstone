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
def get_genomic_coordinates(gene, old_aa, pos, new_aa):
    """
    Helper: Converts 'TTR V50M' -> 'chr18:31592974'
    """
    print(f"   🗺️  [Mapping] Converting {gene} {old_aa}{pos}{new_aa} to Genome Coordinates...")
    
    # Format: TTR:p.Val50Met
    hgvs = f"{gene}:p.{AA_MAP.get(old_aa, '')}{pos}{AA_MAP.get(new_aa, '')}"
    url = f"{VEP_URL}{hgvs}"
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200: return None
        
        data = resp.json()
        if not data: return None
        
        res = data[0]
        chrom = res['seq_region_name'] # Ensembl returns '18'
        start = res['start']
        
        print(f"      📍 Mapped to: chr{chrom}:{start}")
        return chrom, int(start)
        
    except Exception as e:
        print(f"      ⚠️ Mapping Error: {e}")
        return None

def get_alphamissense_sniper(gene, variant_code):
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
    coords = get_genomic_coordinates(gene, old_aa, pos, new_aa)
    if not coords:
        print("      ⚠️ Could not resolve genomic coordinates. Skipping Sniper.")
        return None
    
    chrom, loc = coords

    print(f"   🎯 [Sniper] Querying MyVariant Cloud at chr{chrom}:{loc} (hg38)...")
    
    # 3. Query MyVariant
    url = "https://myvariant.info/v1/query"
    params = {
        "q": f"chr{chrom}:{loc}",
        "fields": "alphamissense,dbnsfp.alphamissense",
        "assembly": "hg38",
        "size": 1
    }
    
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = resp.json()
        
        if "hits" in data and len(data["hits"]) > 0:
            hit = data["hits"][0]
            
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
            print("      ❌ No variant record found (Double-check coordinate mapping).")

    except Exception as e:
        print(f"      ❌ Sniper Error: {e}")
        return None
        
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

    # 2. The Sniper (AlphaMissense Raw Check)
    am_data = None
    if variant_input:
        am_data = get_alphamissense_sniper(gene, variant_input)
        
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
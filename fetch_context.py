import requests
import json
import os
import argparse
import sys
import time

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
DATA_DIR = "data/context"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# 1. RECALL API: Ensembl (Aggregates GWAS, ClinVar, OMIM)
ENSEMBL_URL = "https://rest.ensembl.org/phenotype/gene/human/"

# 2. PRECISION API: Open Targets (Validation)
OT_GRAPHQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"

# 3. IDENTITY API: UniProt
UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/search"

# Headers
HEADERS = {
    "User-Agent": "NeuroCapstone/1.0",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

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
# 2️⃣ RECALL LAYER: Ensembl (The Aggregator)
# ==========================================
def get_ensembl_phenotypes(gene_symbol):
    """
    Fetches phenotype associations from Ensembl.
    Explicitly aggregates: GWAS Catalog, ClinVar, OMIM, Cancer Gene Census.
    """
    print(f"   🔹 [Ensembl] Querying Aggregated Phenotypes (Recall Layer)...")
    
    url = f"{ENSEMBL_URL}{gene_symbol}"
    params = {"include_associated": 1} # Important: Gets variant-linked diseases
    
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        
        if resp.status_code == 200:
            data = resp.json()
            if not data:
                print("      ℹ️  No phenotypes found in Ensembl.")
                return []
            
            # --- Aggregation Logic ---
            disease_counts = {}
            all_sources_found = set()
            
            for entry in data:
                desc = entry.get('description')
                raw_source = entry.get('source')
                
                # Normalize Source Names for cleaner reporting
                if "GWAS" in raw_source: clean_source = "GWAS Catalog"
                elif "ClinVar" in raw_source: clean_source = "ClinVar"
                elif "OMIM" in raw_source: clean_source = "OMIM"
                elif "Cancer Gene Census" in raw_source: clean_source = "Cancer Gene Census"
                else: clean_source = raw_source

                all_sources_found.add(clean_source)

                if desc:
                    if desc not in disease_counts:
                        disease_counts[desc] = {"sources": set(), "count": 0}
                    disease_counts[desc]["sources"].add(clean_source)
                    disease_counts[desc]["count"] += 1
            
            # Sort by evidence count (Frequency proxy)
            sorted_diseases = sorted(disease_counts.items(), key=lambda x: x[1]['count'], reverse=True)[:5]
            
            results = []
            for name, meta in sorted_diseases:
                results.append({
                    "disease": name,
                    "sources": list(meta['sources']),
                    "evidence_count": meta['count']
                })
            
            print(f"      ✅ Success! Found {len(data)} associations.")
            print(f"      📚 Aggregated Sources: {', '.join(sorted(list(all_sources_found)))}")
            return results
            
        else:
            print(f"      ⚠️  Ensembl Error: {resp.status_code}")
            return []
            
    except Exception as e:
        print(f"      ❌ Ensembl Connection Failed: {e}")
        return []

# ==========================================
# 3️⃣ PRECISION LAYER: Open Targets
# ==========================================
def get_opentargets_validation(gene_symbol):
    print(f"   🔸 [OpenTargets] Querying Validation Scores (Precision Layer)...")
    
    # 1. Get Target ID
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
        
        # 2. Get Diseases
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
            results.append({
                "disease": item['disease']['name'],
                "overall_score": round(item['score'], 4)
            })
            
        print(f"      ✅ Success! Validated {len(rows)} targets.")
        return results

    except Exception as e:
        print(f"      ❌ Open Targets Error: {e}")
        return []

# ==========================================
# 🚀 MAIN CONTROLLER
# ==========================================
def fetch_all_context(protein_name):
    print(f"\n--- 🌍 STARTING ROBUST CONTEXT RETRIEVAL: {protein_name} ---")
    
    # 1. Identity Verification
    uid, seq, gene = get_protein_metadata(protein_name)
    if not uid: return None

    print("🏥 [Context] Executing Ensembl (Recall) + OpenTargets (Precision)...")
    
    # 2. Parallel Data Fetch
    recall_data = get_ensembl_phenotypes(gene)
    precision_data = get_opentargets_validation(gene)
    
    # 3. Structure the Final Report
    context_data = {
        "gene": gene,
        "uniprot_id": uid,
        "sequence": seq,
        "medical_context": {
            "recall_layer_ensembl": recall_data,
            "precision_layer_opentargets": precision_data
        }
    }
    
    save_path = os.path.join(DATA_DIR, f"{gene}_context.json")
    with open(save_path, "w") as f:
        json.dump(context_data, f, indent=4)
        
    print(f"✅ Context saved to {save_path}")
    return context_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("protein", type=str, help="Gene Symbol (e.g., SNCA)")
    args = parser.parse_args()
    
    fetch_all_context(args.protein)


"""
=============================================================================
🧬 MODULE: Context Retrieval Engine (Layer 1)
=============================================================================
PURPOSE: 
    Retrieves, aggregates, and validates clinical knowledge for a target protein.
    Implements a "Recall vs. Precision" architecture to balance broad literature
    discovery with strict biological validation.

-----------------------------------------------------------------------------
🛠️ TECH STACK & DATA SOURCES
-----------------------------------------------------------------------------
1. IDENTITY LAYER: UniProt API
   - Role: The "Gold Standard" for protein metadata.
   - Usage: Verifies gene symbols, retrieves UniProt IDs (e.g., P37840),
     and fetches canonical amino acid sequences.

2. RECALL LAYER: Ensembl Phenotype API
   - Role: The "Wide Net" (Maximum Coverage).
   - Usage: Aggregates raw gene-disease associations from:
     * GWAS Catalog (Genome-Wide Association Studies)
     * ClinVar (Clinical Variant Significance)
     * OMIM (Mendelian Inheritance in Man)
     * Orphanet (Rare Diseases)
     * Cancer Gene Census
   - Why: Replaces DisGeNET to avoid IP blocking while accessing the same
     underlying datasets (ClinVar/GWAS) via a robust, open REST API.

3. PRECISION LAYER: Open Targets Platform (GraphQL)
   - Role: The "Validator" (High Confidence).
   - Usage: Fetches 'Overall Association Scores' based on drug targets and
     multi-omics evidence.
   - Why: Prioritizes diseases that are actual therapeutic targets over
     loose mentions in literature.

-----------------------------------------------------------------------------
⚙️ ARCHITECTURE: "Recall vs. Precision"
-----------------------------------------------------------------------------
This script operates on a two-tier logic:
  - TIER A (Recall):   "What *might* this protein cause?" (Ensembl)
                       -> Result: High volume, includes rare/weak signals.
  - TIER B (Precision): "What *definitely* causes disease?" (Open Targets)
                       -> Result: Ranked, scored, and validated targets.

OUTPUT:
    Generates a structured JSON file (e.g., `data/context/SNCA_context.json`)
    containing the merged intelligence, ready for the LLM Analysis Layer.
=============================================================================
"""
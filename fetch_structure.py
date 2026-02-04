import requests
import os
import argparse
import sys
import re

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
STRUCTURE_DIR = "data/structure"
if not os.path.exists(STRUCTURE_DIR):
    os.makedirs(STRUCTURE_DIR)

# URLs
ESMFOLD_API_URL = "https://api.esmatlas.com/foldSequence/v1/pdb/"
UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
ALPHAFOLD_API_URL = "https://alphafold.ebi.ac.uk/api/prediction/{}"

# Headers (Essential to avoid being blocked by EBI/UniProt)
HEADERS = {
    "User-Agent": "NeuroCapstone/1.0 (Educational Research)",
    "Accept": "application/json"
}

# ==========================================
# 🧠 INTELLIGENCE LAYER (Resolvers)
# ==========================================

def resolve_uniprot_id(gene_symbol):
    """
    Auto-detects the UniProt ID for a gene symbol.
    Defaults to: Human (9606) + Reviewed (Swiss-Prot).
    """
    print(f"   🔍 Resolving ID for gene '{gene_symbol}'...")
    
    # Query: Gene Name + Human + Reviewed (High Confidence)
    query = f"gene_exact:{gene_symbol} AND organism_id:9606 AND reviewed:true"
    params = {
        "query": query,
        "format": "json",
        "size": 1  # We only want the top match
    }
    
    try:
        response = requests.get(UNIPROT_SEARCH_URL, params=params, headers=HEADERS)
        data = response.json()
        
        if response.status_code == 200 and data["results"]:
            primary_accession = data["results"][0]["primaryAccession"]
            protein_name = data["results"][0]["proteinDescription"]["recommendedName"]["fullName"]["value"]
            print(f"      ✅ Found: {primary_accession} ({protein_name})")
            return primary_accession
        else:
            print(f"      ❌ Could not resolve UniProt ID for '{gene_symbol}'.")
            return None
            
    except Exception as e:
        print(f"      ❌ Connection Error resolving ID: {e}")
        return None

def get_uniprot_sequence(uniprot_id):
    """
    Fetches the canonical amino acid sequence from UniProt.
    """
    url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.fasta"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            lines = response.text.splitlines()
            # Join lines, skipping the header (>sp|...)
            sequence = "".join([line.strip() for line in lines if not line.startswith(">")])
            return sequence
    except Exception as e:
        print(f"   ❌ UniProt Connection Failed: {e}")
        return None
    return None

def get_alphafold_url_via_api(uniprot_id):
    """
    Asks AlphaFold API for the latest PDB URL (No more version guessing).
    """
    api_url = ALPHAFOLD_API_URL.format(uniprot_id)
    try:
        resp = requests.get(api_url, headers=HEADERS, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list):
                # The API returns a list; the first entry is usually the best model
                pdb_url = data[0].get("pdbUrl")
                return pdb_url
    except Exception as e:
        print(f"      ⚠️  AlphaFold API Check Failed: {e}")
    
    return None

def generate_esmfold_structure(sequence, filename_label):
    """
    Generates structure via Meta ESMFold API.
    """
    # Clean input
    clean_seq = "".join(sequence.split()).replace("*", "").upper()
    print(f"   ⚠️  Generating structure for {filename_label} via ESMFold...")
    print(f"   🧪 Sending {len(clean_seq)} residues...")
    
    save_path = os.path.join(STRUCTURE_DIR, f"{filename_label}.pdb")
    
    try:
        # Disable SSL warnings for cleaner output
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        response = requests.post(ESMFOLD_API_URL, data=clean_seq, verify=False) 
        
        if response.status_code == 200 and not response.text.startswith("Error"):
            with open(save_path, "wb") as f:
                f.write(response.content)
            print(f"   ✅ Success! Generated PDB saved to: {save_path}")
            return save_path
        else:
            print(f"   ❌ ESMFold Error: {response.text}")
            return None
    except Exception as e:
        print(f"   ❌ ESMFold Connection Failed: {e}")
        return None

def apply_mutation(wild_type_seq, mutation_code):
    """
    Parses 'A53T', checks validity against WT, and applies it.
    """
    match = re.match(r"([A-Z])(\d+)([A-Z])", mutation_code.upper())
    if not match:
        print(f"   ❌ Error: Invalid mutation format '{mutation_code}'. Use format like 'A53T'.")
        return None

    old_aa, pos_str, new_aa = match.groups()
    position = int(pos_str) - 1 

    if position < 0 or position >= len(wild_type_seq):
        print(f"   ❌ Error: Position {pos_str} is outside sequence length.")
        return None

    actual_aa = wild_type_seq[position]
    if actual_aa != old_aa:
        print(f"   ❌ BIOLOGY ERROR: Position {pos_str} is '{actual_aa}', not '{old_aa}'. Check your gene/mutation.")
        return None

    seq_list = list(wild_type_seq)
    seq_list[position] = new_aa
    print(f"   ✅ Mutation Verified: Swapped {old_aa} -> {new_aa} at position {pos_str}.")
    return "".join(seq_list)

# ==========================================
# 🚀 MAIN LOGIC
# ==========================================

def get_structure(gene_symbol, uniprot_id_arg=None, manual_sequence=None, variant_tag=None):
    print(f"\n--- 🧬 STARTING STRUCTURE RETRIEVAL: {gene_symbol} ---")

    # 1. RESOLVE ID
    uniprot_id = uniprot_id_arg
    if not uniprot_id:
        uniprot_id = resolve_uniprot_id(gene_symbol)
        if not uniprot_id:
            return None # Cannot proceed without ID

    # ------------------------------------------
    # PATH A: EXPLICIT VARIANT (Force Generation)
    # ------------------------------------------
    if variant_tag:
        label = f"{gene_symbol}_{variant_tag}"
        target_seq = None

        if manual_sequence:
            print(f"   🔧 Mode: Manual Variant Sequence Provided.")
            target_seq = manual_sequence
        else:
            print(f"   🤖 Mode: Auto-Mutating '{variant_tag}' from Wild Type...")
            wt_seq = get_uniprot_sequence(uniprot_id)
            if wt_seq:
                target_seq = apply_mutation(wt_seq, variant_tag)
        
        if target_seq:
            return generate_esmfold_structure(target_seq, label)
        else:
            print("   ❌ Failed to prepare variant sequence.")
            return None

    # ------------------------------------------
    # PATH B: CANONICAL (Check AlphaFold API)
    # ------------------------------------------
    print(f"   ℹ️  Mode: Canonical (Wild Type). Checking AlphaFold DB...")
    
    save_path = os.path.join(STRUCTURE_DIR, f"{gene_symbol}.pdb")
    if os.path.exists(save_path):
        print(f"   ✅ Structure already exists at: {save_path}")
        return save_path

    # Step 1: Discover URL via API
    pdb_url = get_alphafold_url_via_api(uniprot_id)
    
    if pdb_url:
        print(f"      🔍 Found URL via API: {pdb_url}")
        try:
            # Step 2: Download the file
            pdb_resp = requests.get(pdb_url, headers=HEADERS)
            if pdb_resp.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(pdb_resp.content)
                print(f"   ✅ Success! Downloaded from AlphaFold DB (High Confidence).")
                return save_path
        except Exception as e:
            print(f"      ❌ Download Error: {e}")
    else:
        print(f"   ⚠️  No AlphaFold model found in API.")

    # ------------------------------------------
    # PATH C: FALLBACK (ESMFold)
    # ------------------------------------------
    print(f"   ⚠️  Falling back to ESMFold Generation...")
    wt_seq = manual_sequence or get_uniprot_sequence(uniprot_id)
    return generate_esmfold_structure(wt_seq, gene_symbol) if wt_seq else None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("gene", type=str, help="Gene Symbol (e.g., SNCA)")
    
    # Optional Arguments
    parser.add_argument("--id", type=str, help="Optional: UniProt ID. If skipped, auto-detects Human ID.", default=None)
    parser.add_argument("--variant_tag", type=str, help="Mutation Code (e.g., A53T)", default=None)
    parser.add_argument("--seq", type=str, help="Manual sequence override", default=None)
    
    args = parser.parse_args()
    
    # Safety Check
    if args.seq and not args.variant_tag:
        print("❌ CRITICAL ERROR: You provided a sequence but no --variant_tag.")
        sys.exit(1)

    get_structure(args.gene, args.id, args.seq, args.variant_tag)
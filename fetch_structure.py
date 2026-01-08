import requests
import os
import argparse
import sys

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
STRUCTURE_DIR = "data/structure"
if not os.path.exists(STRUCTURE_DIR):
    os.makedirs(STRUCTURE_DIR)

# AlphaFold Database Endpoint (Pre-calculated structures)
ALPHAFOLD_BASE_URL = "https://alphafold.ebi.ac.uk/files/AF-{}-F1-model_v4.pdb"

# ESMFold API Endpoint (Meta AI - Generates structure from string)
ESMFOLD_API_URL = "https://api.esmatlas.com/foldSequence/v1/pdb/"

def get_uniprot_sequence(uniprot_id):
    """Helper: Fetches the amino acid sequence from UniProt if we need to generate it."""
    url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.fasta"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            # Parse FASTA to get just the sequence string
            lines = response.text.splitlines()
            sequence = "".join([line for line in lines if not line.startswith(">")])
            return sequence
    except Exception:
        return None
    return None

def generate_esmfold_structure(sequence, gene_symbol):
    """
    Fallback: Generates structure using Meta's ESMFold API.
    """
    print(f"   ⚠️  AlphaFold 404. Switching to ESMFold (Meta AI) generation...")
    
    if not sequence:
        print("   ❌ Error: No sequence available for generation.")
        return None

    print(f"   🧪 Sending {len(sequence)} residues to ESMFold API...")
    
    save_path = os.path.join(STRUCTURE_DIR, f"{gene_symbol}_ESM.pdb")
    
    try:
        response = requests.post(ESMFOLD_API_URL, data=sequence, verify=False) 
        # Note: verify=False is sometimes needed for this specific API depending on local certs
        
        if response.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(response.content)
            print(f"   ✅ Success! Generated structure via ESMFold: {save_path}")
            return save_path
        else:
            print(f"   ❌ ESMFold Error: {response.text}")
            return None
    except Exception as e:
        print(f"   ❌ ESMFold Connection Failed: {e}")
        return None

def get_structure(uniprot_id, gene_symbol, manual_sequence=None):
    """
    Main Logic: Try AlphaFold -> Fail -> Try ESMFold
    """
    print(f"\n--- 🧬 STARTING STRUCTURE RETRIEVAL: {gene_symbol} ({uniprot_id}) ---")
    
    # 1. Try AlphaFold DB
    af_url = ALPHAFOLD_BASE_URL.format(uniprot_id)
    save_path = os.path.join(STRUCTURE_DIR, f"{gene_symbol}.pdb")
    
    if os.path.exists(save_path):
        print(f"   ✅ Structure already exists at: {save_path}")
        return save_path

    print(f"   ⬇️  Checking AlphaFold DB...")
    response = requests.get(af_url)

    if response.status_code == 200:
        with open(save_path, "wb") as f:
            f.write(response.content)
        print(f"   ✅ Success! Downloaded from AlphaFold DB.")
        return save_path
    
    # 2. If 404, Fallback to ESMFold
    elif response.status_code == 404:
        # If the user provided a specific mutant sequence, use that.
        # Otherwise, fetch the wild-type sequence from UniProt.
        target_sequence = manual_sequence
        
        if not target_sequence:
            print("   ℹ️  Fetching sequence from UniProt for generation...")
            target_sequence = get_uniprot_sequence(uniprot_id)
            
        return generate_esmfold_structure(target_sequence, gene_symbol)
        
    else:
        print(f"   ❌ Error: AlphaFold server returned {response.status_code}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("uniprot_id", type=str, help="UniProt ID (e.g., P37840)")
    parser.add_argument("gene", type=str, help="Gene Symbol (e.g., SNCA)")
    # Added optional argument for custom sequences (Mutants/Synthetic)
    parser.add_argument("--seq", type=str, help="Optional: Manual sequence for ESMFold", default=None)
    
    args = parser.parse_args()
    
    get_structure(args.uniprot_id, args.gene, args.seq)
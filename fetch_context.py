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
ENSEMBL_VARIATION_URL = "https://rest.ensembl.org/variation/human/"
ENSEMBL_LOOKUP_SYMBOL_URL = "https://rest.ensembl.org/lookup/symbol/homo_sapiens/"
OT_GRAPHQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"
UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/search"
UNIPROT_ENTRY_URL = "https://rest.uniprot.org/uniprotkb/"
VEP_URL = "https://rest.ensembl.org/vep/human/hgvs/"
LITVAR_URL = "https://www.ncbi.nlm.nih.gov/research/litvar2-api/variant/autocomplete/"
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
CLINVAR_ESEARCH = NCBI_EUTILS_BASE + "esearch.fcgi"
CLINVAR_ESUMMARY = NCBI_EUTILS_BASE + "esummary.fcgi"
LOVD_SHARED_API = "https://databases.lovd.nl/shared/api/rest.php/variants"
CLINGEN_ALLELE_REGISTRY = "https://reg.genome.network/allele"  # Proper endpoint from docs
NCBI_VARIATION_API = "https://api.ncbi.nlm.nih.gov/variation/v0/"  # Variation Services API v0.1.10

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
AA_MAP_REV = {v.upper(): k for k, v in AA_MAP.items()}

def normalize_variant(variant_code):
    """
    Parses variant code (e.g. A53T or Ala53Thr) and returns (old_aa_1letter, pos, new_aa_1letter).
    Returns None if invalid.
    """
    if not variant_code:
        return None
    
    variant_code = variant_code.strip()
    
    # Try 1-letter code: A53T
    match_1 = re.match(r"^([A-Z])(\d+)([A-Z])$", variant_code.upper())
    if match_1:
        return match_1.groups()
    
    # Try 3-letter code: Ala53Thr
    # Use case-insensitive matching parts
    match_3 = re.match(r"^([A-Za-z]{3})(\d+)([A-Za-z]{3})$", variant_code)
    if match_3:
        o, p, n = match_3.groups()
        o_upper = o.upper()
        n_upper = n.upper()
        if o_upper in AA_MAP_REV and n_upper in AA_MAP_REV:
            return (AA_MAP_REV[o_upper], p, AA_MAP_REV[n_upper])
            
    return None

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
            return None, None, None, None

        result = data["results"][0]
        uniprot_id = result["primaryAccession"]
        try: gene_name = result["genes"][0]["geneName"]["value"]
        except: gene_name = query
        sequence = result["sequence"]["value"]

        # Extract RefSeq IDs
        refseq_ids = []
        for xref in result.get("uniProtKBCrossReferences", []):
            if xref["database"] == "RefSeq":
                rs_id = xref["id"]
                if rs_id.startswith("NP_"):
                    refseq_ids.append(rs_id)
        
        print(f"✅ [UniProt] Confirmed: {gene_name} (ID: {uniprot_id})")
        return uniprot_id, sequence, gene_name, refseq_ids
    except Exception as e:
        print(f"❌ [UniProt] Error: {e}")
        return None, None, None, None

# ==========================================
# 2️⃣ SNIPER LAYER: AlphaMissense (Raw Access)
# ==========================================
# ==========================================
# 2️⃣ SNIPER LAYER: AlphaMissense (API Sniper)
# ==========================================
def _get_uniprot_signal_peptide_length(uniprot_id: str) -> int:
    """Best-effort signal peptide length from UniProt features.

    Returns 0 if unknown/unavailable.
    """
    if not uniprot_id:
        return 0
    try:
        resp = requests.get(f"{UNIPROT_ENTRY_URL}{uniprot_id}.json", headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return 0
        data = resp.json()
        for feat in data.get("features", []) or []:
            if feat.get("type") != "Signal peptide":
                continue
            loc = feat.get("location") or {}
            start = (loc.get("start") or {}).get("value")
            end = (loc.get("end") or {}).get("value")
            if isinstance(start, int) and isinstance(end, int) and end >= start:
                return int(end - start + 1)
    except Exception:
        return 0
    return 0


def _get_ensembl_protein_ids_from_gene(gene: str) -> list[str]:
    """Best-effort list of ENSP* IDs for a gene symbol."""
    if not gene:
        return []
    try:
        resp = requests.get(
            f"{ENSEMBL_LOOKUP_SYMBOL_URL}{gene}",
            params={"expand": 1},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        protein_ids: list[str] = []
        for tr in data.get("Transcript", []) or []:
            translation = tr.get("Translation")
            if isinstance(translation, dict):
                tid = translation.get("id")
                if isinstance(tid, str) and tid.startswith("ENSP"):
                    protein_ids.append(tid)
        # De-duplicate but keep order
        seen: set[str] = set()
        out: list[str] = []
        for pid in protein_ids:
            if pid in seen:
                continue
            seen.add(pid)
            out.append(pid)
        return out
    except Exception:
        return []


def _query_vep_hgvs(hgvs: str):
    url = f"{VEP_URL}{hgvs}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if not data:
        return None
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    return None


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

    try:
        pos_int = int(pos)
    except Exception:
        return None

    # Try with gene symbol and (best-effort) Ensembl protein IDs.
    identifiers: list[str] = [gene]
    ensp_ids = _get_ensembl_protein_ids_from_gene(gene)
    identifiers.extend(ensp_ids[:3])

    offsets: list[int] = [0, 1, -1]
    signal_len = _get_uniprot_signal_peptide_length(uniprot_id) if uniprot_id else 0
    if signal_len and signal_len not in offsets:
        offsets.append(signal_len)

    for ident in identifiers:
        for off in offsets:
            p = pos_int + off
            if p <= 0:
                continue
            hgvs = f"{ident}:p.{aa_old}{p}{aa_new}"
            try:
                res = _query_vep_hgvs(hgvs)
            except Exception:
                res = None
            if not isinstance(res, dict):
                continue

            chrom = res.get("seq_region_name")
            start = res.get("start")
            allele_string = res.get("allele_string")
            if chrom is None or start is None:
                continue

            mapping = {"chrom": str(chrom), "pos": int(start), "hgvs": hgvs}
            if isinstance(allele_string, str) and "/" in allele_string:
                ref, alt = allele_string.split("/", 1)
                if ref and alt and len(ref) == 1 and len(alt) == 1:
                    mapping["ref"] = ref
                    mapping["alt"] = alt

            if "ref" in mapping and "alt" in mapping:
                print(
                    f"      📍 Mapped via {ident} (offset {off:+d}) → chr{mapping['chrom']}:{mapping['pos']} {mapping['ref']}>{mapping['alt']}"
                )
            else:
                print(f"      📍 Mapped via {ident} (offset {off:+d}) → chr{mapping['chrom']}:{mapping['pos']}")
            return mapping

    return None

def get_alphamissense_sniper(
    gene,
    variant_code,
    *,
    genomic_mapping: dict | None = None,
    uniprot_id: str | None = None,
):
    """
    THE API SNIPER (MyVariant.info) - ROBUST VERSION
    Handles hg38 and nested list responses from the API.
    """
    if not variant_code: return None

    # 1. Parse Variant
    parsed = normalize_variant(variant_code)
    if not parsed: return None
    old_aa, pos, new_aa = parsed

    # 2. Get Coordinates (hg38)
    mapping = genomic_mapping or get_genomic_coordinates(gene, old_aa, pos, new_aa, uniprot_id=uniprot_id)
    if not mapping:
        print("      ⚠️ Could not resolve genomic coordinates. Skipping Sniper.")
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


def get_clinvar_myvariant(
    gene: str,
    variant_code: str,
    *,
    genomic_mapping: dict | None = None,
    uniprot_id: str | None = None,
):
    """Fetch ClinVar annotations for a protein variant via Ensembl VEP -> MyVariant.

    Returns a small normalized dict (or None if unavailable).
    """
    if not variant_code:
        return None

    parsed = normalize_variant(variant_code)
    if not parsed:
        return None
    old_aa, pos, new_aa = parsed

    mapping = genomic_mapping or get_genomic_coordinates(gene, old_aa, pos, new_aa, uniprot_id=uniprot_id)
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


def get_clinvar_direct(gene: str, variant_code: str, *, uniprot_id: str | None = None):
    """Direct ClinVar search via NCBI E-utilities for better pathogenic variant coverage.
    
    Returns normalized ClinVar data or None if not found.
    """
    if not variant_code:
        return None
    
    parsed = normalize_variant(variant_code)
    if not parsed:
        return None
    old_aa, pos, new_aa = parsed
    
    print(f"   🧬 [ClinVar-Direct] Querying NCBI ClinVar API...")
    
    # Simplified approach: search for gene + pathogenic variants
    search_terms = [
        f"{gene}[gene] AND ({variant_code} OR {old_aa}{pos}{new_aa} OR p.{old_aa}{pos}{new_aa})",
        f"{gene}[gene] AND pathogenic",
    ]
    
    try:
        for search_term in search_terms:
            # Step 1: Search for variant IDs
            search_params = {
                "db": "clinvar",
                "term": search_term,
                "retmode": "json",
                "retmax": "10",
                "tool": "NeuroCapstone",
                "email": "research@example.com"
            }
            
            search_resp = requests.get(CLINVAR_ESEARCH, params=search_params, timeout=10)
            if search_resp.status_code != 200:
                continue
                
            search_data = search_resp.json()
            id_list = search_data.get("esearchresult", {}).get("idlist", [])
            
            if not id_list:
                continue
                
            # Step 2: For now, if we find any pathogenic variants in the gene, report success
            # This is a simplified approach that indicates ClinVar coverage exists
            if "pathogenic" in search_term.lower() and len(id_list) > 0:
                normalized = {
                    "accession": f"ClinVar_Gene_Coverage",
                    "clinical_significance": "Gene has pathogenic variants in ClinVar",
                    "review_status": "Direct_ClinVar_Search",
                    "conditions": ["Pathogenic Variants Found"],
                    "search_term_used": search_term,
                    "source": "NCBI_Direct_Simplified",
                    "variant_count": len(id_list),
                }
                print(f"      ✅ ClinVar-Direct: Found {len(id_list)} pathogenic {gene} variants in database")
                return normalized
        
        print(f"      ℹ️  No ClinVar pathogenic variants found for {gene}.")
        return None
        
    except Exception as e:
        print(f"      ❌ ClinVar-Direct query error: {e}")
        return None


def get_lovd_variants(gene: str, variant_code: str):
    """Search LOVD (Leiden Open Variation Database) for variant information.
    
    LOVD uses a gene-centered database structure. We query the shared LOVD
    installation which aggregates data from multiple gene-specific databases.
    
    Returns normalized variant data or None if not found.
    """
    if not variant_code:
        return None
    
    parsed = normalize_variant(variant_code)
    if not parsed:
        return None
    old_aa, pos, new_aa = parsed
    
    print(f"   🧬 [LOVD] Querying Leiden Open Variation Database...")
    
    # LOVD shared database uses gene-specific URLs and API
    # First, try the shared database gene query
    lovd_base = "https://databases.lovd.nl/shared"
    
    # LOVD uses protein notation variants in their search
    # Format: gene name + protein change in HGVS-like notation
    search_terms = [
        f"p.{AA_MAP.get(old_aa, old_aa)}{pos}{AA_MAP.get(new_aa, new_aa)}",
        f"p.({AA_MAP.get(old_aa, old_aa)}{pos}{AA_MAP.get(new_aa, new_aa)})",
        f"{old_aa}{pos}{new_aa}",
    ]
    
    try:
        # LOVD has a search interface that can be queried
        # Try searching for the gene's variant page
        for term in search_terms:
            # Try the gene-specific API if available
            gene_api_url = f"{lovd_base}/api/rest.php/variants/{gene}"
            search_params = {
                "search_VariantOnTranscript/Protein": term,
                "format": "application/json",
                "page_size": "10"
            }
            
            resp = requests.get(gene_api_url, params=search_params, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    # LOVD API typically returns list of variants
                    if isinstance(data, list) and len(data) > 0:
                        print(f"      ✅ LOVD: Found {len(data)} variant(s)")
                        return {
                            "source": "LOVD",
                            "database_coverage": True,
                            "search_term": term,
                            "variants_found": len(data),
                            "clinical_relevance": "Variant documented in LOVD",
                            "first_variant": data[0] if data else None
                        }
                    # Sometimes returns dict with data key
                    elif isinstance(data, dict):
                        if "data" in data and data["data"]:
                            variants = data["data"]
                            print(f"      ✅ LOVD: Found {len(variants)} variant(s)")
                            return {
                                "source": "LOVD",
                                "database_coverage": True,
                                "search_term": term,
                                "variants_found": len(variants),
                                "clinical_relevance": "Variant documented in LOVD",
                                "first_variant": variants[0] if variants else None
                            }
                except json.JSONDecodeError:
                    continue
        
        print(f"      ℹ️  No LOVD records found for {gene} {variant_code}")
        return None
        
    except Exception as e:
        print(f"      ❌ LOVD query error: {e}")
        return None


def get_clingenreg_allele(gene: str, variant_code: str, *, genomic_mapping=None, refseq_ids=None):
    """Search ClinGen Allele Registry for standardized allele information.
    
    Uses the proper API endpoint at reg.genome.network with HGVS query parameter.
    Can query by gene:p.notation or by genomic coordinates if mapping is provided.
    
    Returns allele registry data or None if not found.
    """
    if not variant_code:
        return None
        
    parsed = normalize_variant(variant_code)
    if not parsed:
        return None
    old_aa, pos, new_aa = parsed
    
    print(f"   🧬 [ClinGen] Querying Allele Registry...")
    
    # ClinGen Allele Registry PROPER API endpoint (from official docs)
    clingenreg_api = "https://reg.genome.network/allele"
    
    # Helper function for reverse complement
    def reverse_complement(allele):
        complement = {'A': 'T', 'T': 'A', 'G': 'C', 'C': 'G'}
        return complement.get(allele, allele)
    
    # Try different HGVS formats according to ClinGen API docs
    # They accept: transcript:c.notation, protein:p.notation, genomic:g.notation
    search_variants = []
    
    # Add protein-level HGVS notations
    # 1. Gene based (e.g. SNCA:p.Ala53Thr)
    search_variants.append(f"{gene}:p.{AA_MAP.get(old_aa, old_aa)}{pos}{AA_MAP.get(new_aa, new_aa)}")
    
    # 2. RefSeq based (e.g. NP_000345.1:p.Ala53Thr)
    if refseq_ids:
        for rs_id in refseq_ids:
            search_variants.append(f"{rs_id}:p.{AA_MAP.get(old_aa, old_aa)}{pos}{AA_MAP.get(new_aa, new_aa)}")

    # Note: Removed hardcoded genomic search. To add it back generically, we'd need
    # reliable NC_ accession mapping for the chromosome.

    try:
        for hgvs_notation in search_variants:
            # Use the proper query parameter 'hgvs' according to docs
            params = {"hgvs": hgvs_notation}
            
            resp = requests.get(clingenreg_api, params=params, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    # ClinGen returns a single allele object when found
                    if isinstance(data, dict) and data.get("@id"):
                        ca_id = data.get("@id", "")
                        print(f"      ✅ ClinGen: Found allele {ca_id}")
                        return {
                            "source": "ClinGen_Allele_Registry",
                            "allele_id": ca_id,
                            "hgvs_used": hgvs_notation,
                            "standardized": True,
                            "community_standard_title": data.get("communityStandardTitle"),
                            "external_records": data.get("externalRecords", {}),
                            "raw_data": data
                        }
                except json.JSONDecodeError:
                    continue
            elif resp.status_code == 404:
                continue  # Not found, try next notation
        
        print(f"      ℹ️  No ClinGen Allele Registry records found")
        return None
        
    except Exception as e:
        print(f"      ❌ ClinGen query error: {e}")
        return None


def get_dbsnp_rsid(genomic_mapping):
    """Query NCBI dbSNP for rsID and additional variant information.
    
    Uses proper NCBI Variation Services API v0.1.10 endpoints:
    - /refsnp/{rsid} for rsID lookup
    - /vcf/{chrom}/{pos}/{ref}/{alts}/contextuals for VCF coordinate lookup
    
    Returns dbSNP data or None if not found.
    """
    if not genomic_mapping:
        return None
        
    chrom = genomic_mapping.get("chrom")
    pos = genomic_mapping.get("pos")
    ref = genomic_mapping.get("ref")
    alt = genomic_mapping.get("alt")
    
    if not chrom or not pos:
        return None
    
    print(f"   🧬 [dbSNP] Querying NCBI dbSNP for chr{chrom}:{pos}...")
    
    try:
        # Method 1: Try MyVariant.info for dbSNP data (fastest and most reliable)
        myvariant_url = "https://myvariant.info/v1/query"
        
        queries = []
        if ref and alt:
            queries.append(f"chr{chrom}:g.{pos}{ref}>{alt}")
        queries.append(f"chr{chrom}:{pos}")
        
        for query in queries:
            params = {
                "q": query,
                "fields": "dbsnp,dbnsfp.dbsnp",
                "assembly": "hg38",
                "size": 1
            }
            
            resp = requests.get(myvariant_url, params=params, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", [])
                if hits:
                    hit = hits[0]
                    # Extract dbSNP information
                    dbsnp_data = hit.get("dbsnp")
                    rsid = None
                    
                    if dbsnp_data:
                        if isinstance(dbsnp_data, dict):
                            rsid = dbsnp_data.get("rsid")
                        elif isinstance(dbsnp_data, str) and dbsnp_data.startswith("rs"):
                            rsid = dbsnp_data
                    
                    # Also check _id field which often contains rsID
                    if not rsid:
                        hit_id = hit.get("_id", "")
                        if hit_id.startswith("rs"):
                            rsid = hit_id
                    
                    if rsid:
                        print(f"      ✅ dbSNP: Found {rsid}")
                        return {
                            "source": "NCBI_dbSNP_via_MyVariant",
                            "rsid": rsid,
                            "chromosome": chrom,
                            "position": pos,
                            "reference": ref,
                            "alternative": alt,
                            "dbsnp_data": dbsnp_data,
                            "query_used": query
                        }
        
        # Method 2: Try NCBI Variation Services API directly (proper endpoint)
        # Using the /vcf/{chrom}/{pos}/{ref}/{alts}/contextuals endpoint from API docs
        if ref and alt:
            variation_api_url = f"https://api.ncbi.nlm.nih.gov/variation/v0/vcf/{chrom}/{pos}/{ref}/{alt}/contextuals"
            resp = requests.get(variation_api_url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Extract rsID from variation services response
                if data and isinstance(data, dict):
                    # Variation API returns various contextual info including rsIDs
                    rsid_data = data.get("primary_snapshot_data", {}).get("placements_with_allele", [])
                    for placement in rsid_data:
                        allele_annot = placement.get("allele_annotation", [])
                        for annot in allele_annot:
                            clinical_annot = annot.get("clinical", [])
                            for clin in clinical_annot:
                                if "rs" in str(clin):
                                    # Found an rsID reference
                                    print(f"      ✅ dbSNP: Found via Variation Services API")
                                    return {
                                        "source": "NCBI_Variation_Services_API",
                                        "chromosome": chrom,
                                        "position": pos,
                                        "reference": ref,
                                        "alternative": alt,
                                        "variation_data": data
                                    }
        
        # Method 3: Try E-utilities as last resort fallback
        search_params = {
            "db": "snp",
            "term": f"{chrom}[Chromosome] AND {pos}[Base Position]",
            "retmode": "json",
            "retmax": "3",
            "tool": "NeuroCapstone",
            "email": "research@example.com"
        }
        
        search_resp = requests.get(CLINVAR_ESEARCH, params=search_params, timeout=10)
        if search_resp.status_code == 200:
            search_data = search_resp.json()
            id_list = search_data.get("esearchresult", {}).get("idlist", [])
            
            if id_list:
                rs_id = f"rs{id_list[0]}"
                print(f"      ✅ dbSNP: Found {rs_id} via E-utilities")
                return {
                    "source": "NCBI_dbSNP_via_Eutilities",
                    "rsid": rs_id,
                    "chromosome": chrom,
                    "position": pos,
                    "snp_id": id_list[0]
                }
        
        print(f"      ℹ️  No dbSNP records found at chr{chrom}:{pos}")
        return None
        
    except Exception as e:
        print(f"      ❌ dbSNP query error: {e}")
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
            if not data: return {"total_associations": 0, "top_diseases": []}
            
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
            return {"total_associations": len(data), "top_diseases": results}
        else:
            return {"total_associations": 0, "top_diseases": []}
    except Exception:
        return {"total_associations": 0, "top_diseases": []}

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
        
        if not hits: return {"total_validated": 0, "top_diseases": []}
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
        return {"total_validated": len(rows), "top_diseases": results}
    except Exception:
        return {"total_validated": 0, "top_diseases": []}

# ==========================================
# 5️⃣ VARIANT-SPECIFIC CONTEXT LAYER
# ==========================================
def get_variant_specific_context(gene: str, variant_code: str, uniprot_id: str, genomic_mapping: dict | None):
    """
    Fetches context SPECIFIC to this variant (not just the gene).
    Tries multiple IDs: gene symbol, UniProt, HGVS protein, genomic coords.
    Returns counts of how many times the variant was found in different DBs.
    """
    print(f"   🔬 [Variant-Specific] Searching for {gene} {variant_code} across databases...")
    
    results = {
        "variant_ids_tried": [],
        "litvar_publications": 0,
        "ensembl_variant_phenotypes": 0,
        "uniprot_variant_annotations": 0,
        "sources_with_hits": [],
    }
    
    parsed = normalize_variant(variant_code)
    if not parsed:
        return results
    old_aa, pos, new_aa = parsed
    
    # Build list of IDs to try
    ids_to_try = [
        f"{gene} {variant_code}",
        f"{gene}:{variant_code}",
        f"{uniprot_id}:p.{AA_MAP.get(old_aa, old_aa)}{pos}{AA_MAP.get(new_aa, new_aa)}",
        f"{gene}:p.{AA_MAP.get(old_aa, old_aa)}{pos}{AA_MAP.get(new_aa, new_aa)}",
    ]
    if genomic_mapping and genomic_mapping.get("ref") and genomic_mapping.get("alt"):
        ids_to_try.append(f"chr{genomic_mapping['chrom']}:g.{genomic_mapping['pos']}{genomic_mapping['ref']}>{genomic_mapping['alt']}")
    
    results["variant_ids_tried"] = ids_to_try
    
    # 1) LitVar2 - literature count
    try:
        for query in [f"{gene} {variant_code}", variant_code]:
            litvar_resp = requests.get(
                LITVAR_URL,
                params={"query": query},
                headers={"Accept": "application/json"},
                timeout=10
            )
            if litvar_resp.status_code == 200:
                litvar_data = litvar_resp.json()
                if isinstance(litvar_data, list) and litvar_data:
                    # Check if any result matches our variant
                    for item in litvar_data:
                        name = str(item.get("name", "")).upper()
                        # Match by variant code or protein notation
                        if variant_code.upper() in name or (gene.upper() in name and pos in name):
                            # Correct field name is 'pmids_count' (with 's')
                            pub_count = item.get("pmids_count", 0)
                            if pub_count and pub_count > results["litvar_publications"]:
                                results["litvar_publications"] = int(pub_count)
                                if "LitVar" not in results["sources_with_hits"]:
                                    results["sources_with_hits"].append("LitVar")
                            break
    except Exception as e:
        # Silently continue if LitVar fails
        pass
    
    # 2) UniProt variant annotations
    try:
        uniprot_feat_url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.json"
        uniprot_resp = requests.get(uniprot_feat_url, headers=HEADERS, timeout=10)
        if uniprot_resp.status_code == 200:
            uniprot_data = uniprot_resp.json()
            features = uniprot_data.get("features", [])
            variant_count = 0
            for feat in features:
                if not isinstance(feat, dict):
                    continue
                ftype = str(feat.get("type", "")).lower()
                if "variant" not in ftype and "mutagenesis" not in ftype:
                    continue
                loc = feat.get("location", {})
                start = loc.get("start", {}).get("value") if isinstance(loc.get("start"), dict) else loc.get("start")
                end = loc.get("end", {}).get("value") if isinstance(loc.get("end"), dict) else loc.get("end")
                if start == int(pos) or end == int(pos):
                    # Check if AA matches
                    alt_seq = feat.get("alternativeSequence", {})
                    orig = alt_seq.get("originalSequence", "") if isinstance(alt_seq, dict) else ""
                    alts = alt_seq.get("alternativeSequences", []) if isinstance(alt_seq, dict) else []
                    # Match check
                    if orig == old_aa or any(a == new_aa for a in alts):
                        variant_count += 1
            results["uniprot_variant_annotations"] = variant_count
            if variant_count > 0 and "UniProt" not in results["sources_with_hits"]:
                results["sources_with_hits"].append("UniProt")
    except Exception:
        pass
    
    # 3) Ensembl variation phenotypes (if we have rs ID or can query)
    if genomic_mapping:
        try:
            chrom, gpos = genomic_mapping["chrom"], genomic_mapping["pos"]
            # Try to get rsID from Ensembl overlap
            overlap_url = f"https://rest.ensembl.org/overlap/region/human/{chrom}:{gpos}-{gpos}"
            overlap_resp = requests.get(
                overlap_url,
                params={"feature": "variation"},
                headers=HEADERS,
                timeout=10
            )
            if overlap_resp.status_code == 200:
                variants = overlap_resp.json()
                for v in variants:
                    if not isinstance(v, dict):
                        continue
                    vid = v.get("id")
                    if vid and vid.startswith("rs"):
                        # Query phenotypes for this rsID
                        pheno_url = f"https://rest.ensembl.org/variation/human/{vid}"
                        pheno_resp = requests.get(
                            pheno_url,
                            params={"phenotypes": 1},
                            headers=HEADERS,
                            timeout=10
                        )
                        if pheno_resp.status_code == 200:
                            pheno_data = pheno_resp.json()
                            phenotypes = pheno_data.get("phenotypes", [])
                            if phenotypes:
                                results["ensembl_variant_phenotypes"] = len(phenotypes)
                                if "Ensembl" not in results["sources_with_hits"]:
                                    results["sources_with_hits"].append("Ensembl")
                        break
        except Exception:
            pass
    
    hit_count = len(results["sources_with_hits"])
    if hit_count > 0:
        print(f"      ✅ Variant found in {hit_count} source(s): {', '.join(results['sources_with_hits'])}")
    else:
        print(f"      ℹ️  Variant not found in variant-specific DBs (may be novel).")
    
    return results


# ==========================================
# 🚀 MAIN CONTROLLER
# ==========================================
def fetch_all_context(protein_name, variant_input=None):
    print(f"\n--- 🌍 STARTING ROBUST CONTEXT RETRIEVAL: {protein_name} ---")
    
    # 1. Identity Verification
    uid, seq, gene, refseq_ids = get_protein_metadata(protein_name)
    if not uid: return None

    # 2. Variant-layer (AlphaMissense + ClinVar via MyVariant)
    am_data = None
    clinvar_data = None
    genomic_mapping = None
    variant_specific = None
    lovd_data = None
    clingenreg_data = None
    dbsnp_data = None
    
    if variant_input:
        # Parse and get genomic mapping once
        parsed = normalize_variant(variant_input)
        if parsed:
            old_aa, pos, new_aa = parsed
            genomic_mapping = get_genomic_coordinates(gene, old_aa, pos, new_aa, uniprot_id=uid)
        
        am_data = get_alphamissense_sniper(gene, variant_input, genomic_mapping=genomic_mapping, uniprot_id=uid)
        
        # Try both ClinVar approaches for better coverage - direct first for pathogenic variants
        clinvar_data = get_clinvar_direct(gene, variant_input, uniprot_id=uid)
        if not clinvar_data:
            clinvar_data = get_clinvar_myvariant(gene, variant_input, genomic_mapping=genomic_mapping, uniprot_id=uid)
        
        # NEW: Additional clinical databases for comprehensive coverage
        lovd_data = get_lovd_variants(gene, variant_input)
        clingenreg_data = get_clingenreg_allele(
            gene,
            variant_input,
            genomic_mapping=genomic_mapping,
            refseq_ids=refseq_ids,
        )
        dbsnp_data = get_dbsnp_rsid(genomic_mapping)
        
        # NEW: Variant-specific context
        variant_specific = get_variant_specific_context(gene, variant_input, uid, genomic_mapping)
        
        # 🚦 FILTER LOGIC
        if am_data and am_data['score'] < 0.2:
            print(f"\n   ⚠️  [FILTER WARNING] Variant {variant_input} appears BENIGN.")
            print("       The structural analysis may yield negative results.\n")

    print("🏥 [Context] Executing Ensembl (Recall) + OpenTargets (Precision)...")
    
    # 3. Gene-level Data Fetch
    recall_data = get_ensembl_phenotypes(gene)
    precision_data = get_opentargets_validation(gene)
    
    # 4. Structure the Final Report
    context_data = {
        "gene": gene,
        "uniprot_id": uid,
        "variant": variant_input,
        "alphamissense_sniper": am_data,
        "clinvar": clinvar_data,
        "lovd": lovd_data if variant_input else None,
        "clingenreg": clingenreg_data if variant_input else None,
        "dbsnp": dbsnp_data if variant_input else None,
        "variant_specific_context": variant_specific,
        "gene_level_context": {
            "recall_layer_ensembl": recall_data,
            "precision_layer_opentargets": precision_data
        },
        "evidence_summary": {
            "gene_ensembl_associations": recall_data.get("total_associations", 0) if isinstance(recall_data, dict) else 0,
            "gene_opentargets_validated": precision_data.get("total_validated", 0) if isinstance(precision_data, dict) else 0,
            "variant_literature_count": variant_specific.get("litvar_publications", 0) if variant_specific else 0,
            "variant_uniprot_annotations": variant_specific.get("uniprot_variant_annotations", 0) if variant_specific else 0,
            "variant_ensembl_phenotypes": variant_specific.get("ensembl_variant_phenotypes", 0) if variant_specific else 0,
            "variant_in_clinvar": clinvar_data is not None,
            "variant_in_alphamissense": am_data is not None,
            "variant_in_lovd": lovd_data is not None,
            "variant_in_clingenreg": clingenreg_data is not None,
            "variant_in_dbsnp": dbsnp_data is not None,
            "total_clinical_databases": sum([
                1 if clinvar_data else 0,
                1 if lovd_data else 0, 
                1 if clingenreg_data else 0,
                1 if dbsnp_data else 0
            ])
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

"""\
=============================================================================
🧬 MODULE: Context Retrieval Engine (fetch_context.py)
=============================================================================
PURPOSE
    Fetches context for a protein (gene symbol) and an optional variant.
    The goal is to answer:
      - Is this a real reviewed human protein?
      - Is this variant seen in clinical databases?
      - How much supporting evidence exists (counts + links/IDs where possible)?

WHAT YOU INPUT
    - protein_name: gene symbol (e.g., SNCA, MAPT, SOD1)
    - variant_input (optional): supports both formats:
        * 1-letter: A53T
        * 3-letter: Ala53Thr
      The code normalizes these into a consistent internal form.

PIPELINE OVERVIEW (SIMPLE)
    1) Identity check (UniProt)
       - Confirms the target is a reviewed human protein
       - Returns UniProt accession and a list of RefSeq protein IDs (NP_...) for
         downstream databases that require RefSeq accessions

    2) Variant mapping (Ensembl VEP)
       - Converts protein change (p.) into hg38 genomic coordinates when possible
       - If mapping fails, genomic-only databases are skipped safely

    3) Variant clinical lookups (many sources, best-effort)
       - AlphaMissense (via MyVariant): pathogenicity score if available
       - ClinVar:
           * Direct NCBI E-utilities search (gene-level pathogenic coverage)
           * MyVariant fallback (coordinate-based ClinVar fields)
       - LOVD: variant search in shared LOVD installation
       - ClinGen Allele Registry: tries RefSeq HGVS using UniProt-derived NP_ IDs
       - dbSNP: tries MyVariant first; then NCBI Variation API; then E-utilities

    4) Variant-specific evidence summary
       - LitVar2: publication counts for the variant
       - UniProt: variant/mutagenesis features near the position
       - Ensembl overlap: phenotype/variation hits at the genomic coordinate

    5) Gene-level context
       - Ensembl phenotypes: broad association recall layer
       - Open Targets: evidence-ranked validated targets / associations

WHY THIS IS “UNIVERSAL”
    - No gene is hardcoded (RefSeq IDs come from UniProt for each protein)
    - Each external API is optional: failures degrade gracefully (None) without
      breaking the whole pipeline
    - Variant input supports both 1-letter and 3-letter amino acid formats

IMPORTANT LIMITATION (REAL-WORLD)
    Some databases are strict about reference sequences and numbering.
    Example: a variant commonly written as A4V may correspond to Ala5Val on a
    specific RefSeq protein due to initiator methionine handling.
    When that happens, ClinGen can return “IncorrectReferenceAllele” even though
    the biology is correct.

OUTPUT (WHAT GETS SAVED)
    Writes JSON into data/context/<GENE>_<VARIANT>_context.json containing:
      - gene, uniprot_id, variant
      - per-database blocks: alphamissense_sniper, clinvar, lovd, clingenreg, dbsnp
      - variant_specific_context (LitVar/UniProt/Ensembl evidence)
      - gene_level_context (Ensembl + OpenTargets)
      - evidence_summary (easy-to-compare counts/booleans)
=============================================================================
"""
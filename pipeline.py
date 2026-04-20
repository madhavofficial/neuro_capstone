import argparse
import html
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple


@dataclass(frozen=True)
class Target:
    gene: str
    variant: Optional[str] = None


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _parse_batch_line(line: str) -> Optional[Target]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    # Allow comma-separated or whitespace-separated formats:
    #   SNCA A53T
    #   SNCA,A53T
    #   SNCA
    tokens = [t for t in stripped.replace(",", " ").split() if t]
    if not tokens:
        return None

    if len(tokens) == 1:
        return Target(gene=tokens[0], variant=None)

    return Target(gene=tokens[0], variant=tokens[1])


def load_targets(batch_file: Optional[str], gene: Optional[str], variant: Optional[str]) -> list[Target]:
    if batch_file:
        with open(batch_file, "r") as f:
            targets: list[Target] = []
            for line in f:
                target = _parse_batch_line(line)
                if target:
                    targets.append(target)
        return targets

    if not gene:
        raise ValueError("gene is required unless --batch is provided")

    return [Target(gene=gene, variant=variant)]


def save_physics_json(pdb_path: str, variant: str, physics_data: dict, out_dir: Optional[str]) -> str:
    base_name = os.path.basename(pdb_path).replace(".pdb", "")
    filename = f"{base_name}_{variant}_physics.json"

    if out_dir:
        _ensure_dir(out_dir)
        out_path = os.path.join(out_dir, filename)
    else:
        out_path = os.path.join(os.path.dirname(pdb_path), filename)

    with open(out_path, "w") as f:
        json.dump(physics_data, f, indent=4)

    return out_path


def _require_literature_runtime() -> None:
    try:
        import requests  # noqa: F401
        from bs4 import BeautifulSoup  # noqa: F401
        from transformers import AutoTokenizer  # noqa: F401
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Literature stage dependencies are missing. "
            "Please ensure they are in your requirements.txt and installed: "
            "`requests`, `beautifulsoup4`, `transformers` "
            f"(original error: {e})"
        )


def _clean_literature_text(text: str | None) -> str:
    if not text:
        return ""

    from bs4 import BeautifulSoup

    cleaned = html.unescape(text)
    cleaned = BeautifulSoup(cleaned, "html.parser").get_text(" ", strip=True)
    return cleaned.strip()


def _literature_query(gene: str, variant: str) -> str:
    return f'("{gene}" AND "{variant}") AND (pathogenic OR aggregation OR misfolding)'


def fetch_literature_json(gene: str, variant: str, *, literature_dir: str = "data/literature", max_papers: int = 100) -> str:
    import requests

    _require_literature_runtime()
    _ensure_dir(literature_dir)

    query = _literature_query(gene, variant)
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    papers: list[dict] = []
    seen: set[str] = set()
    cursor = "*"

    while len(papers) < max_papers:
        params = {
            "query": query,
            "format": "json",
            "pageSize": 50,
            "resultType": "core",
            "cursorMark": cursor,
        }

        data = None
        for attempt in range(3):
            try:
                time.sleep(1)
                response = requests.get(url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

        if not isinstance(data, dict):
            break

        results = (data or {}).get("resultList", {}).get("result", [])
        if not results:
            break

        for item in results:
            pmid = item.get("pmid")
            paper_id = item.get("id")
            if paper_id and str(paper_id).startswith("PPR"):
                continue

            final_id = str(pmid or paper_id or "").strip()
            if not final_id or final_id in seen:
                continue

            title = _clean_literature_text(item.get("title"))
            abstract = _clean_literature_text(item.get("abstractText"))
            if not title or not abstract:
                continue

            papers.append(
                {
                    "pmid": final_id,
                    "title": title,
                    "abstract": abstract,
                }
            )
            seen.add(final_id)
            if len(papers) >= max_papers:
                break

        next_cursor = (data or {}).get("nextCursorMark")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    output_path = os.path.join(literature_dir, f"{gene}_{variant}_corpus.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(papers, f, indent=4, ensure_ascii=False)
    return output_path


def _chunk_by_tokens_offsets(text: str, tokenizer, chunk_size: int = 400, overlap: int = 80) -> list[str]:
    encoded = tokenizer(
        text,
        add_special_tokens=False,
        return_offsets_mapping=True,
    )
    input_ids = encoded["input_ids"]
    offsets = encoded["offset_mapping"]

    if not input_ids:
        return []

    chunks: list[str] = []
    step = chunk_size - overlap
    for i in range(0, len(input_ids), step):
        window_offsets = offsets[i : i + chunk_size]
        if not window_offsets:
            continue
        start_char = window_offsets[0][0]
        end_char = window_offsets[-1][1]
        chunk_text = text[start_char:end_char]
        chunks.append(chunk_text)
        if i + chunk_size >= len(input_ids):
            break
    return chunks


def _chunk_by_words(text: str, chunk_size: int = 400, overlap: int = 80) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        chunk_words = words[i : i + chunk_size]
        if not chunk_words:
            continue
        chunks.append(" ".join(chunk_words))
        if i + chunk_size >= len(words):
            break
    return chunks


_TOKENIZER_CACHE = None

def process_literature_json(gene: str, variant: str, *, literature_dir: str = "data/literature") -> str:
    from transformers import AutoTokenizer

    _require_literature_runtime()
    _ensure_dir(literature_dir)

    input_path = os.path.join(literature_dir, f"{gene}_{variant}_corpus.json")
    if not os.path.exists(input_path):
        raise RuntimeError(f"Literature corpus not found: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        papers = json.load(f)

    global _TOKENIZER_CACHE
    tokenizer = None
    try:
        if _TOKENIZER_CACHE is None:
            _TOKENIZER_CACHE = AutoTokenizer.from_pretrained("pritamdeka/S-PubMedBert-MS-MARCO", use_fast=True)
        tokenizer = _TOKENIZER_CACHE
        if not tokenizer.is_fast:
            tokenizer = None
    except Exception:
        tokenizer = None

    chunked_data: list[dict] = []
    for paper in papers:
        pmid = paper.get("pmid")
        title = str(paper.get("title", "")).replace("\n", " ").strip()
        abstract = str(paper.get("abstract", "")).replace("\n", " ").strip()
        if not pmid or not abstract:
            continue

        chunks = _chunk_by_tokens_offsets(abstract, tokenizer) if tokenizer else _chunk_by_words(abstract)
        for i, chunk in enumerate(chunks):
            token_count = len(tokenizer.encode(chunk, add_special_tokens=False)) if tokenizer else len(chunk.split())
            if token_count < 40:
                continue
            chunked_data.append(
                {
                    "chunk_id": f"{pmid}_{i}",
                    "pmid": pmid,
                    "title": title,
                    "chunk": chunk,
                }
            )

    output_path = os.path.join(literature_dir, f"{gene}_{variant}_chunked_corpus.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunked_data, f, indent=4, ensure_ascii=False)
    return output_path


def run_pipeline(
    gene: str,
    variant: Optional[str],
    *,
    uniprot_id: Optional[str] = None,
    manual_sequence: Optional[str] = None,
    chain_id: Optional[str] = None,
    run_structure: bool = True,
    run_context: bool = True,
    run_analysis: bool = True,
    run_fetch_literature: bool = True,
    run_process_literature: bool = True,
    literature_dir: str = "data/literature",
    analysis_out_dir: Optional[str] = None,
) -> Tuple[Optional[str], Optional[dict], Optional[str]]:
    """Runs structure -> context -> physics analysis.

    Returns (pdb_path, context_dict, physics_json_path).
    """

    pdb_path: Optional[str] = None
    context_data: Optional[dict] = None
    physics_json_path: Optional[str] = None

    if run_structure:
        try:
            from fetch_structure import get_structure
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "Structure step import failed. This usually means you're running the pipeline with a Python "
                "interpreter that doesn't have the project dependencies installed. "
                "If you have a venv, try: `source .venv/bin/activate` (Linux/macOS) "
                "or `.\\.venv\\Scripts\\Activate.ps1` (Windows PowerShell) then rerun with `python pipeline.py ...` "
                "(or run `./.venv/bin/python pipeline.py ...`). "
                f"Original error: {e}"
            )

        pdb_path = get_structure(
            gene,
            uniprot_id_arg=uniprot_id,
            manual_sequence=manual_sequence,
            # Mutation is handled virtually during analysis; keep structure WT/canonical.
            variant_tag=None,
        )
        if not pdb_path:
            raise RuntimeError(f"Structure step failed for {gene}{' ' + variant if variant else ''}")

    if run_context:
        try:
            from fetch_context import fetch_all_context
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "Context step import failed. This usually means you're running the pipeline with a Python "
                "interpreter that doesn't have the project dependencies installed. "
                "If you have a venv, try: `source .venv/bin/activate` (Linux/macOS) "
                "or `.\\.venv\\Scripts\\Activate.ps1` (Windows PowerShell) then rerun with `python pipeline.py ...` "
                "(or run `./.venv/bin/python pipeline.py ...`). "
                f"Original error: {e}"
            )

        context_data = fetch_all_context(gene, variant)
        if context_data is None:
            raise RuntimeError(f"Context step failed for {gene}{' ' + variant if variant else ''}")

    if run_analysis:
        if not variant:
            raise ValueError("--variant is required to run physics analysis")
        if not pdb_path:
            raise RuntimeError("No PDB available for analysis step")

        try:
            from analyze_structure import calculate_physics_metrics
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "Analysis step import failed. If the error mentions `Bio`/Biopython, you're likely not using the venv. "
                "Try: `source .venv/bin/activate` (Linux/macOS) "
                "or `.\\.venv\\Scripts\\Activate.ps1` (Windows PowerShell) then rerun with `python pipeline.py ...` "
                "(or run `./.venv/bin/python pipeline.py ...`). "
                f"Original error: {e}"
            )

        physics_data = calculate_physics_metrics(pdb_path, variant, chain_id=chain_id)
        if not physics_data:
            raise RuntimeError(f"Analysis step failed for {gene} {variant}")

        physics_json_path = save_physics_json(pdb_path, variant, physics_data, analysis_out_dir)

    if run_fetch_literature or run_process_literature:
        if not variant:
            raise ValueError("--variant is required to run literature stages")

        if run_fetch_literature and run_process_literature:
            fetch_literature_json(gene, variant, literature_dir=literature_dir)
            process_literature_json(gene, variant, literature_dir=literature_dir)
        elif run_fetch_literature:
            fetch_literature_json(gene, variant, literature_dir=literature_dir)
        elif run_process_literature:
            process_literature_json(gene, variant, literature_dir=literature_dir)

    return pdb_path, context_data, physics_json_path


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-command pipeline: structure -> context -> physics analysis",
    )

    parser.add_argument("gene", nargs="?", help="Gene symbol (e.g., SNCA)")
    parser.add_argument("--variant", help="Variant code (e.g., A53T)", default=None)

    parser.add_argument(
        "--batch",
        help="Path to a batch file with one target per line: 'GENE VARIANT' or 'GENE,VARIANT' (variant optional)",
        default=None,
    )

    # Pass-through options to fetch_structure
    parser.add_argument("--id", dest="uniprot_id", help="Optional UniProt ID", default=None)
    parser.add_argument(
        "--seq",
        dest="manual_sequence",
        help="Manual WT/canonical sequence override for structure folding (used if AlphaFold is unavailable)",
        default=None,
    )

    # Analysis options
    parser.add_argument(
        "--chain",
        dest="chain_id",
        help="Chain ID to analyze (passed to analyze_structure; default: first chain)",
        default=None,
    )

    # Pipeline controls
    parser.add_argument("--no-structure", action="store_true", help="Skip structure step")
    parser.add_argument("--no-context", action="store_true", help="Skip context step")
    parser.add_argument("--no-analysis", action="store_true", help="Skip analysis step")
    parser.add_argument("--no-fetch-literature", action="store_true", help="Skip literature fetch JSON stage")
    parser.add_argument("--no-process-literature", action="store_true", help="Skip literature chunking JSON stage")
    parser.add_argument(
        "--literature-dir",
        help="Directory for literature JSON outputs",
        default="data/literature",
    )
    parser.add_argument(
        "--analysis-out-dir",
        help="Where to save physics JSON output (default: data/analysis)",
        default="data/analysis",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    # --seq is allowed without --variant (WT folding override).

    try:
        targets = load_targets(args.batch, args.gene, args.variant)
    except Exception as e:
        print(f"❌ Error: {e}")
        return 2

    failures: list[str] = []

    for target in targets:
        label = f"{target.gene}{' ' + target.variant if target.variant else ''}".strip()
        print(f"\n==============================\n🚀 PIPELINE TARGET: {label}\n==============================")
        try:
            effective_run_analysis = (not args.no_analysis) and bool(target.variant)
            if (not args.no_analysis) and (not target.variant):
                print("ℹ️  No variant provided for this target; skipping physics analysis.")
            effective_run_fetch_lit = (not args.no_fetch_literature) and bool(target.variant)
            effective_run_process_lit = (not args.no_process_literature) and bool(target.variant)
            if (not args.no_fetch_literature or not args.no_process_literature) and (not target.variant):
                print("ℹ️  No variant provided for this target; skipping literature stages.")

            pdb_path, _context, physics_json_path = run_pipeline(
                target.gene,
                target.variant,
                uniprot_id=args.uniprot_id,
                manual_sequence=args.manual_sequence,
                chain_id=args.chain_id,
                run_structure=not args.no_structure,
                run_context=not args.no_context,
                run_analysis=effective_run_analysis,
                run_fetch_literature=effective_run_fetch_lit,
                run_process_literature=effective_run_process_lit,
                literature_dir=args.literature_dir,
                analysis_out_dir=args.analysis_out_dir,
            )

            if pdb_path:
                print(f"✅ Structure: {pdb_path}")
            if physics_json_path:
                print(f"✅ Physics JSON: {physics_json_path}")

            # Automatically invoke NLP query generation if both gene and variant are present
            if target.gene and target.variant:
                try:
                    from nlp_formation import run_nlp_formation
                    print(f"📝 Generating NLP query for {target.gene} {target.variant}...")
                    nlp_query = run_nlp_formation(target.gene, target.variant, data_dir="data")
                    print(f"✅ NLP Query Generated: {nlp_query[:100]}...")

                    try:
                        from orchestration import phase_3_vector_engine, phase_4_assemble_payload
                        
                        print(f"\n🔎 Orchestrating vector retrieval and assembling payload...")
                        ranked_results = phase_3_vector_engine(target.gene, target.variant, nlp_query)
                        
                        output_payload_path = f"data/{target.gene}_{target.variant}_payload.json"
                        payload = phase_4_assemble_payload(
                            query=nlp_query,
                            ranked_results=ranked_results,
                            output_path=output_payload_path
                        )
                        print(f"✅ Final payload successfully saved to {output_payload_path}")
                    except Exception as e:
                        print(f"⚠️  Orchestrator failed to retrieve and assemble evidence: {e}")

                except Exception as e:
                    print(f"⚠️  Failed to generate NLP query: {e}")
        except Exception as e:
            failures.append(f"{label}: {e}")
            print(f"❌ Pipeline failed for {label}: {e}")

    if failures:
        print("\nSome targets failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

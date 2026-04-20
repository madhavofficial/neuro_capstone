import os
import json
import logging
import numpy as np
import faiss
import torch

from sentence_transformers import SentenceTransformer, CrossEncoder

# Configure logging
logger = logging.getLogger(__name__)

MODEL_NAME = "pritamdeka/S-PubMedBert-MS-MARCO"
RERANK_MODEL = "cross-encoder/ms-marco-TinyBERT-L-2-v2"

_BI_ENCODER = None
_CROSS_ENCODER = None
_INDEX = None
_METADATA = None
_CURRENT_TARGET = None  # To track which gene_variant is currently loaded

TOP_K_RETRIEVAL = 50
TOP_K_FINAL = 3

def _get_faiss_dir():
    path = "data/faiss"
    os.makedirs(path, exist_ok=True)
    return path

def _get_paths(gene, variant):
    base_dir = _get_faiss_dir()
    prefix = f"{gene}_{variant}"
    return {
        "embeddings": os.path.join(base_dir, f"{prefix}_embeddings.npy"),
        "index": os.path.join(base_dir, f"{prefix}_index.bin"),
        "metadata": os.path.join(base_dir, f"{prefix}_metadata.json")
    }

def _select_device():
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"

def load_models():
    device = _select_device()
    logger.info(f"Loading Models on device: {device}")
    bi_encoder = SentenceTransformer(MODEL_NAME, device=device)
    cross_encoder = CrossEncoder(RERANK_MODEL, device=device)
    return bi_encoder, cross_encoder

def get_models():
    global _BI_ENCODER, _CROSS_ENCODER
    if _BI_ENCODER is None or _CROSS_ENCODER is None:
        _BI_ENCODER, _CROSS_ENCODER = load_models()
    return _BI_ENCODER, _CROSS_ENCODER

def _get_chunked_corpus_path(gene, variant):
    filename = f"{gene}_{variant}_chunked_corpus.json"
    return os.path.join("data/literature", filename)

def load_corpus(gene, variant):
    data_path = _get_chunked_corpus_path(gene, variant)
    if not os.path.isfile(data_path):
        raise FileNotFoundError(
            f"Chunked corpus not found: {data_path}. "
            "Run literature fetch/chunking for the requested gene and variant."
        )

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

def create_embeddings(bi_encoder, corpus):
    texts = [item["chunk"] for item in corpus]
    logger.info(f"Creating embeddings for {len(texts)} chunks...")
    embeddings = bi_encoder.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True
    )
    return embeddings

def save_embeddings(gene, variant, embeddings, corpus):
    paths = _get_paths(gene, variant)
    np.save(paths["embeddings"], embeddings)
    with open(paths["metadata"], "w", encoding="utf-8") as f:
        json.dump(corpus, f, indent=2)
    logger.info(f"Saved embeddings and metadata for {gene} {variant}")

def build_faiss_index(gene, variant, embeddings):
    paths = _get_paths(gene, variant)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)  # cosine similarity
    index.add(embeddings)
    faiss.write_index(index, paths["index"])
    logger.info(f"Built and saved FAISS index for {gene} {variant}")
    return index

def load_index_and_metadata(gene, variant):
    paths = _get_paths(gene, variant)
    if not os.path.exists(paths["index"]) or not os.path.exists(paths["metadata"]):
        raise FileNotFoundError(f"Index or metadata missing for {gene} {variant}")
        
    index = faiss.read_index(paths["index"])
    with open(paths["metadata"], "r") as f:
        metadata = json.load(f)
    return index, metadata

def get_index_and_metadata(gene, variant):
    global _INDEX, _METADATA, _CURRENT_TARGET
    target_id = f"{gene}_{variant}"
    
    if _INDEX is None or _METADATA is None or _CURRENT_TARGET != target_id:
        logger.info(f"Loading index and metadata for {target_id}...")
        _INDEX, _METADATA = load_index_and_metadata(gene, variant)
        _CURRENT_TARGET = target_id
        
    return _INDEX, _METADATA

def retrieve_candidates(query, bi_encoder, index, metadata):
    query_embedding = bi_encoder.encode(
        [query],
        normalize_embeddings=True
    )

    scores, indices = index.search(query_embedding, TOP_K_RETRIEVAL)
    results = []

    for idx, score in zip(indices[0], scores[0]):
        if idx < 0 or idx >= len(metadata):
            continue

        item = metadata[idx]
        results.append({
            "chunk_id": item["chunk_id"],
            "pmid": item["pmid"],
            "title": item["title"],
            "chunk": item["chunk"],
            "score": float(score)
        })

    return results

def rerank(query, candidates, cross_encoder):
    if not candidates:
        return []
        
    pairs = [(query, item["chunk"]) for item in candidates]
    scores = cross_encoder.predict(pairs)

    for i, item in enumerate(candidates):
        item["rerank_score"] = float(scores[i])

    sorted_results = sorted(
        candidates,
        key=lambda x: x["rerank_score"],
        reverse=True
    )

    return sorted_results[:TOP_K_FINAL]

def retrieve_evidence(gene, variant, query):
    """
    Retrieve and rerank evidence for a specific gene and variant target.
    """
    bi_encoder, cross_encoder = get_models()
    index, metadata = get_index_and_metadata(gene, variant)
    candidates = retrieve_candidates(query, bi_encoder, index, metadata)
    final_results = rerank(query, candidates, cross_encoder)
    return final_results

def setup_pipeline(gene, variant):
    """
    Builds or updates the vector store for a target gene and variant.
    """
    global _INDEX, _METADATA, _CURRENT_TARGET

    bi_encoder, _ = get_models()
    corpus = load_corpus(gene, variant)
    embeddings = create_embeddings(bi_encoder, corpus)
    save_embeddings(gene, variant, embeddings, corpus)

    _INDEX = build_faiss_index(gene, variant, embeddings)
    _METADATA = corpus
    _CURRENT_TARGET = f"{gene}_{variant}"
    logger.info(f"Setup complete for {gene} {variant}")




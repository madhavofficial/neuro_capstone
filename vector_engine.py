import os
import json
import numpy as np
import faiss
import torch

from sentence_transformers import SentenceTransformer, CrossEncoder

MODEL_NAME = "pritamdeka/S-PubMedBert-MS-MARCO"
RERANK_MODEL = "cross-encoder/ms-marco-TinyBERT-L-2-v2"

_BI_ENCODER = None
_CROSS_ENCODER = None
_INDEX = None
_METADATA = None

EMBEDDINGS_PATH = "data/faiss/embeddings.npy"
INDEX_PATH = "data/faiss/faiss_index.bin"
METADATA_PATH = "data/faiss/metadata.json"

TOP_K_RETRIEVAL = 50
TOP_K_FINAL = 3


def _select_device():
    if torch.cuda.is_available():
        return "cuda"

    # Apple Silicon Metal backend in PyTorch
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"

    return "cpu"

def load_models():
    device = _select_device()
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

    embeddings = bi_encoder.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True
    )

    return embeddings

def save_embeddings(embeddings, corpus):
    os.makedirs("data/faiss", exist_ok=True)

    np.save(EMBEDDINGS_PATH, embeddings)

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f)

def build_faiss_index(embeddings):
    dim = embeddings.shape[1]

    index = faiss.IndexFlatIP(dim)  # cosine similarity

    index.add(embeddings)

    faiss.write_index(index, INDEX_PATH)

    return index

def load_index_and_metadata():
    index = faiss.read_index(INDEX_PATH)

    with open(METADATA_PATH, "r") as f:
        metadata = json.load(f)

    return index, metadata

def get_index_and_metadata():
    global _INDEX, _METADATA
    if _INDEX is None or _METADATA is None:
        _INDEX, _METADATA = load_index_and_metadata()
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

def retrieve_evidence(query):
    bi_encoder, cross_encoder = get_models()

    index, metadata = get_index_and_metadata()

    candidates = retrieve_candidates(query, bi_encoder, index, metadata)

    final_results = rerank(query, candidates, cross_encoder)

    return final_results

def setup_pipeline(gene, variant):
    global _INDEX, _METADATA

    bi_encoder, _ = get_models()

    corpus = load_corpus(gene, variant)

    embeddings = create_embeddings(bi_encoder, corpus)

    save_embeddings(embeddings, corpus)

    _INDEX = build_faiss_index(embeddings)
    _METADATA = corpus




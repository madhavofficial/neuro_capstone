import os
import json
import numpy as np
import faiss

from sentence_transformers import SentenceTransformer, CrossEncoder

MODEL_NAME = "pritamdeka/S-PubMedBert-MS-MARCO"
RERANK_MODEL = "cross-encoder/ms-marco-TinyBERT-L-2-v2"


def _resolve_literature_path():
    literature_dir = "data/literature"
    if not os.path.isdir(literature_dir):
        raise FileNotFoundError(f"Literature directory not found: {literature_dir}")

    chunked_files = sorted(
        f for f in os.listdir(literature_dir)
        if f.endswith("_chunked_corpus.json")
    )
    if chunked_files:
        return os.path.join(literature_dir, chunked_files[0])

    json_files = sorted(
        f for f in os.listdir(literature_dir)
        if f.endswith(".json")
    )
    if not json_files:
        raise FileNotFoundError(f"No literature JSON files found in {literature_dir}")

    raise FileNotFoundError(
        "Only raw literature corpus JSON files were found. "
        "Run the literature chunking stage to generate '*_chunked_corpus.json'."
    )


DATA_PATH = _resolve_literature_path()

EMBEDDINGS_PATH = "data/faiss/embeddings.npy"
INDEX_PATH = "data/faiss/faiss_index.bin"
METADATA_PATH = "data/faiss/metadata.json"

TOP_K_RETRIEVAL = 50
TOP_K_FINAL = 3

def load_models():
    bi_encoder = SentenceTransformer(MODEL_NAME, device="cuda")
    cross_encoder = CrossEncoder(RERANK_MODEL, device="cuda")
    return bi_encoder, cross_encoder

def load_corpus():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
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

def retrieve_candidates(query, bi_encoder, index, metadata):
    query_embedding = bi_encoder.encode(
        [query],
        normalize_embeddings=True
    )

    scores, indices = index.search(query_embedding, TOP_K_RETRIEVAL)

    results = []

    for idx, score in zip(indices[0], scores[0]):
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
    bi_encoder, cross_encoder = load_models()

    index, metadata = load_index_and_metadata()

    candidates = retrieve_candidates(query, bi_encoder, index, metadata)

    final_results = rerank(query, candidates, cross_encoder)

    return final_results

def setup_pipeline():
    bi_encoder, _ = load_models()

    corpus = load_corpus()

    embeddings = create_embeddings(bi_encoder, corpus)

    save_embeddings(embeddings, corpus)

    build_faiss_index(embeddings)




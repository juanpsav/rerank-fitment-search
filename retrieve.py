"""Run every retrieval setup over the same queries and corpus; save rankings, latency and usage.

Setups
  bm25                 keyword baseline (local, free)
  embed                embed-v5.0-fast, cosine nearest neighbours
  hybrid               reciprocal rank fusion of bm25 top-50 + embed top-50
  hybrid+rerank-fast   hybrid top-100 reranked by rerank-v4.0-fast
  hybrid+rerank-pro    hybrid top-100 reranked by rerank-v4.0-pro

Usage
  python retrieve.py --smoke   # ~10 API calls: checks key, SDK and plumbing end to end
  python retrieve.py           # full run (~530 API calls on first run, 0 on re-runs)
"""
import argparse
import json
import re
import statistics
import time

import numpy as np
from rank_bm25 import BM25Okapi

import config as C
from cohere_client import Cohere

LATENCY_SAMPLE = 30  # queries embedded one at a time to measure single-query latency


def tokenize(s: str):
    return re.findall(r"[a-z0-9]+", s.lower())


def load(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def embed_corpus(co, texts):
    vecs, tokens = [], 0
    for i in range(0, len(texts), C.EMBED_BATCH):
        data, _, cached = co.embed(texts[i:i + C.EMBED_BATCH], "search_document")
        vecs += data["embeddings"]["float"]
        tokens += (data["meta"]["billed_units"] or {}).get("input_tokens") or 0
        print(f"\r  embedded {min(i + C.EMBED_BATCH, len(texts))}/{len(texts)}"
              f"{' (cached)' if cached else ''}   ", end="", flush=True)
    print()
    m = np.asarray(vecs, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True), tokens


def rrf(*rankings, k=C.RRF_K):
    scores = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="tiny run to check setup before spending calls")
    args = ap.parse_args()

    corpus = load(C.DATA / "corpus.jsonl")
    queries = load(C.DATA / "queries.jsonl")
    if args.smoke:
        corpus, queries = corpus[: 2 * C.EMBED_BATCH], queries[:3]
    ids = [d["id"] for d in corpus]
    texts = {d["id"]: d["text"] for d in corpus}
    co = Cohere()
    runs = {name: {} for name in ["bm25", "embed", "hybrid"] + [f"hybrid+{m}" for m in C.RERANK_MODELS]}
    lat = {name: [] for name in ["bm25", "embed_query"] + C.RERANK_MODELS}
    usage = {"embed_corpus_tokens": 0, "embed_query_tokens": 0,
             "rerank_search_units": {m: 0 for m in C.RERANK_MODELS}}

    print("BM25 index...")
    bm25 = BM25Okapi([tokenize(texts[i]) for i in ids])

    print(f"Embedding corpus with {C.EMBED_MODEL}...")
    doc_vecs, usage["embed_corpus_tokens"] = embed_corpus(co, [texts[i] for i in ids])

    print("Embedding queries...")
    q_texts = [q["query"] for q in queries]
    q_vecs = []
    for i in range(0, len(q_texts), C.EMBED_BATCH):
        data, _, _ = co.embed(q_texts[i:i + C.EMBED_BATCH], "search_query")
        q_vecs += data["embeddings"]["float"]
        usage["embed_query_tokens"] += (data["meta"]["billed_units"] or {}).get("input_tokens") or 0
    q_vecs = np.asarray(q_vecs, dtype=np.float32)
    q_vecs /= np.linalg.norm(q_vecs, axis=1, keepdims=True)
    for q in queries[:LATENCY_SAMPLE]:  # single-query latency, as a live search would see it
        _, latency, _ = co.embed([q["query"]], "search_query")
        lat["embed_query"].append(latency)

    for n, q in enumerate(queries):
        qid = q["qid"]
        t0 = time.perf_counter()
        scores = bm25.get_scores(tokenize(q["query"]))
        bm = [ids[j] for j in np.argsort(-scores)[: C.CANDIDATES]]
        lat["bm25"].append(time.perf_counter() - t0)
        em = [ids[j] for j in np.argsort(-(doc_vecs @ q_vecs[n]))[: C.CANDIDATES]]
        hy = rrf(bm[: C.HYBRID_EACH], em[: C.HYBRID_EACH])[: C.CANDIDATES]
        runs["bm25"][qid], runs["embed"][qid], runs["hybrid"][qid] = bm, em, hy

        for model in C.RERANK_MODELS:
            data, latency, cached = co.rerank(q["query"], [texts[d] for d in hy], model)
            runs[f"hybrid+{model}"][qid] = [hy[r["index"]] for r in data["results"]]
            usage["rerank_search_units"][model] += (data["meta"]["billed_units"] or {}).get("search_units") or 0
            lat[model].append(latency)
        print(f"\r  queries {n + 1}/{len(queries)}  (new API calls so far: {co.api_calls})   ",
              end="", flush=True)
    print()

    out = C.RUNS / ("smoke" if args.smoke else "full")
    out.mkdir(parents=True, exist_ok=True)
    (out / "runs.json").write_text(json.dumps(runs))
    meta = {
        "embed_model": C.EMBED_MODEL, "rerank_models": C.RERANK_MODELS, "n_docs": len(ids),
        "n_queries": len(queries), "candidates": C.CANDIDATES, "usage": usage,
        "latency_ms": {k: {"p50": 1000 * statistics.median(v),
                           "p95": 1000 * float(np.percentile(v, 95)), "n": len(v)}
                       for k, v in lat.items() if v},
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"New API calls this run: {co.api_calls}. Wrote {out}/")


if __name__ == "__main__":
    main()

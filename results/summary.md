# Results (full run)

Corpus: 8,936 products. Embed: `embed-v5.0-fast`. Rerank depth: top 100.

## ESCI fitment queries (n=177)

| Setup | nDCG@10 | MRR@10 | Recall@100 | Δ nDCG vs BM25 (95% CI) |
|---|---|---|---|---|
| bm25 | 0.566 | 0.753 | 0.810 | +0.000 [+0.000, +0.000] |
| embed | 0.659 | 0.792 | 0.877 | +0.094 [+0.062, +0.123] |
| hybrid | 0.631 | 0.785 | 0.846 | +0.065 [+0.046, +0.084] |
| hybrid+rerank-v4.0-fast | 0.683 | 0.826 | 0.846 | +0.117 [+0.090, +0.145] |
| hybrid+rerank-v4.0-pro | 0.702 | 0.811 | 0.846 | +0.136 [+0.108, +0.164] |

## Your catalog: fitment queries (n=25)

Did *your* product make the top 10 among all products in the corpus?

| Setup | In top 10 | MRR@10 | Median rank (top 100) |
|---|---|---|---|
| bm25 | 60% | 0.497 | 1 |
| embed | 56% | 0.443 | 3 |
| hybrid | 80% | 0.481 | 4 |
| hybrid+rerank-v4.0-fast | 96% | 0.765 | 1 |
| hybrid+rerank-v4.0-pro | 100% | 0.771 | 1 |

## Latency (per query, measured from this machine)

| Step | p50 ms | p95 ms | n |
|---|---|---|---|
| bm25 | 13 | 21 | 202 |
| embed_query | 90 | 96 | 30 |
| rerank-v4.0-fast | 266 | 697 | 202 |
| rerank-v4.0-pro | 688 | 2100 | 202 |

## Usage per 1,000 queries

| Item | Units | Cost |
|---|---|---|
| embed-v5.0-fast (query) | 8,386 tokens | set price in config.py |
| rerank-v4.0-fast | 1,000 search units | set price in config.py |
| rerank-v4.0-pro | 1,000 search units | set price in config.py |
| embed-v5.0-fast (index 8,936 docs, one-off) | 1,943,627 tokens | set price in config.py |

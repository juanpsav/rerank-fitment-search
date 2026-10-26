"""Shared settings. Change models, sizes and prices here, not in the scripts."""
from pathlib import Path

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
DATA = ROOT / "data"
CACHE = ROOT / "data" / "cache"
RUNS = ROOT / "results" / "runs"
RESULTS = ROOT / "results"

# Your existing catalog (the "own catalog" slice). Optional: skipped if missing.
CATALOG_DIR = Path.home() / "catalog-optimizer"

# Models under test
EMBED_MODEL = "embed-v5.0-fast"
RERANK_MODELS = ["rerank-v4.0-fast", "rerank-v4.0-pro"]

# Corpus construction
N_DISTRACTORS = 6000          # extra automotive-ish ESCI products nobody labeled for our queries
SEED = 7

# Retrieval
CANDIDATES = 100              # docs sent to Rerank per query (1 search unit = 1 query + up to 100 docs)
HYBRID_EACH = 50              # top-k taken from BM25 and from Embed before fusing
RRF_K = 60                    # reciprocal rank fusion constant
EVAL_K = 10                   # nDCG@10, MRR@10

# ESCI graded gains, as used in the KDD Cup 2022 ESCI task
GAINS = {"E": 1.0, "S": 0.1, "C": 0.01, "I": 0.0}

# Text sent to every retriever (same text for BM25, Embed, Rerank -> fair comparison)
MAX_DOC_CHARS = 1200

# Prices: Cohere does not publish per-call prices for these models on its site.
# Fill these in from your Cohere dashboard or quote to turn usage into dollars.
# Units: USD per 1M embed input tokens / USD per 1k rerank search units.
PRICE_EMBED_PER_1M_TOKENS = {EMBED_MODEL: None}
PRICE_RERANK_PER_1K_SEARCHES = {m: None for m in RERANK_MODELS}

# Trial keys: Rerank is limited to 10 calls/min. Production keys: set to 1000.
RERANK_CALLS_PER_MIN = 10
EMBED_INPUTS_PER_MIN = 2000   # same on trial and production keys
EMBED_BATCH = 96

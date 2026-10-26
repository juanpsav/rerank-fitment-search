"""Thin wrapper around cohere.ClientV2: env-only API key, disk cache, rate limit, retries, latency.

Every API response is cached in data/cache/calls.sqlite keyed on the exact request, so re-running
the experiment costs nothing and the trial key's monthly call budget is spent once.
"""
import hashlib
import json
import os
import sqlite3
import sys
import time

import cohere

import config as C


def _client() -> cohere.ClientV2:
    key = os.environ.get("COHERE_API_KEY")
    if not key:
        sys.exit("COHERE_API_KEY is not set. In your shell run:\n"
                 '  read -s "COHERE_API_KEY?Cohere key: " && export COHERE_API_KEY')
    return cohere.ClientV2(api_key=key, timeout=60)


class Cohere:
    def __init__(self):
        C.CACHE.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(C.CACHE / "calls.sqlite")
        self.db.execute("CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, response TEXT, latency REAL)")
        self._co = None
        self._last_rerank = 0.0
        self._last_embed = 0.0
        self.api_calls = 0

    @property
    def co(self):
        if self._co is None:
            self._co = _client()
        return self._co

    def _cached(self, endpoint: str, request: dict, call, before=None):
        key = hashlib.sha256(json.dumps([endpoint, request], sort_keys=True).encode()).hexdigest()
        row = self.db.execute("SELECT response, latency FROM calls WHERE key=?", (key,)).fetchone()
        if row:
            return json.loads(row[0]), row[1], True
        for attempt in range(6):
            try:
                if before:
                    before()
                t0 = time.perf_counter()
                resp = call(**request)
                latency = time.perf_counter() - t0
                break
            except cohere.errors.TooManyRequestsError:
                wait = 2 ** attempt * 5
                print(f"  429 from {endpoint}, retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
        else:
            raise RuntimeError(f"{endpoint}: still rate limited after retries")
        self.api_calls += 1
        data = resp.model_dump(mode="json")
        self.db.execute("INSERT INTO calls VALUES (?,?,?)", (key, json.dumps(data), latency))
        self.db.commit()
        return data, latency, False

    def embed(self, texts, input_type, model=C.EMBED_MODEL, embedding_types=("float",)):
        req = {"model": model, "texts": list(texts), "input_type": input_type,
               "embedding_types": list(embedding_types), "truncate": "END"}

        def pace():
            gap = 60.0 * len(req["texts"]) / C.EMBED_INPUTS_PER_MIN - (time.monotonic() - self._last_embed)
            if gap > 0:
                time.sleep(gap)
            self._last_embed = time.monotonic()

        return self._cached("embed", req, lambda **kw: self.co.embed(**kw), before=pace)

    def rerank(self, query, documents, model):
        req = {"model": model, "query": query, "documents": list(documents), "top_n": len(documents)}

        def pace():
            # Space out real calls to respect the per-minute limit. Cache hits skip this,
            # and the wait happens before the latency timer starts.
            gap = 60.0 / C.RERANK_CALLS_PER_MIN - (time.monotonic() - self._last_rerank)
            if gap > 0:
                time.sleep(gap)
            self._last_rerank = time.monotonic()

        return self._cached("rerank", req, lambda **kw: self.co.rerank(**kw), before=pace)

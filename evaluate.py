"""Score the saved runs: nDCG@10, MRR@10, Recall@100, paired bootstrap CIs, latency and usage.

Usage:  python evaluate.py [--run full|smoke]
Writes results/metrics.json, results/summary.md and results/ndcg.png.
"""
import argparse
import json
import math

import numpy as np

import config as C

BOOTSTRAP = 2000


def ndcg_at_k(ranked, rels, k=C.EVAL_K):
    dcg = sum(rels.get(d, 0.0) / math.log2(i + 2) for i, d in enumerate(ranked[:k]))
    ideal = sorted(rels.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def mrr_at_k(ranked, rels, k=C.EVAL_K):
    """Reciprocal rank of the first Exact match (gain 1.0)."""
    for i, d in enumerate(ranked[:k]):
        if rels.get(d, 0.0) >= 1.0:
            return 1.0 / (i + 1)
    return 0.0


def recall_at_k(ranked, rels, k=C.CANDIDATES):
    exact = {d for d, g in rels.items() if g >= 1.0}
    return len(exact & set(ranked[:k])) / len(exact) if exact else 0.0


def paired_ci(a, b, n=BOOTSTRAP, seed=C.SEED):
    """95% CI for mean(b - a) by resampling queries."""
    diff = np.asarray(b) - np.asarray(a)
    rng = np.random.default_rng(seed)
    means = diff[rng.integers(0, len(diff), (n, len(diff)))].mean(axis=1)
    return float(diff.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def per_query(runs, qrels, qids):
    out = {}
    for name, run in runs.items():
        out[name] = {
            "ndcg": [ndcg_at_k(run[q], qrels[q]) for q in qids],
            "mrr": [mrr_at_k(run[q], qrels[q]) for q in qids],
            "recall": [recall_at_k(run[q], qrels[q]) for q in qids],
            "rank": [next((i + 1 for i, d in enumerate(run[q]) if qrels[q].get(d, 0) >= 1), None)
                     for q in qids],
        }
    return out


def cost_rows(meta, n_queries):
    u = meta["usage"]
    rows = []
    q_tok = u["embed_query_tokens"] / n_queries * 1000
    p = C.PRICE_EMBED_PER_1M_TOKENS.get(meta["embed_model"])
    rows.append((f"{meta['embed_model']} (query)", f"{q_tok:,.0f} tokens",
                 f"${q_tok / 1e6 * p:.4f}" if p else "set price in config.py"))
    for m in meta["rerank_models"]:
        su = u["rerank_search_units"][m] / n_queries * 1000
        p = C.PRICE_RERANK_PER_1K_SEARCHES.get(m)
        rows.append((m, f"{su:,.0f} search units", f"${su / 1000 * p:.2f}" if p else "set price in config.py"))
    p = C.PRICE_EMBED_PER_1M_TOKENS.get(meta["embed_model"])
    rows.append((f"{meta['embed_model']} (index {meta['n_docs']:,} docs, one-off)",
                 f"{int(u['embed_corpus_tokens']):,} tokens",
                 f"${u['embed_corpus_tokens'] / 1e6 * p:.2f}" if p else "set price in config.py"))
    return rows


def chart(table, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = list(table)[::-1]
    vals = [table[n]["ndcg"] for n in names]
    err = np.array([[table[n]["ndcg"] - table[n]["ndcg_lo"], table[n]["ndcg_hi"] - table[n]["ndcg"]]
                    for n in names]).T
    ink, muted, grid, blue, base = "#0b0b0b", "#52514e", "#e6e5e0", "#2a78d6", "#a3a29c"
    colors = [blue if "rerank" in n else base for n in names]
    fig, ax = plt.subplots(figsize=(7.5, 3.2), dpi=160)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    from make_figures import LABELS
    ax.barh([LABELS.get(n, n) for n in names], vals, color=colors, height=0.55, xerr=err,
            error_kw={"ecolor": muted, "elinewidth": 1, "capsize": 0})
    for y, n in enumerate(names):
        ax.text(table[n]["ndcg_hi"] + 0.012, y, f"{table[n]['ndcg']:.3f}", va="center", fontsize=9, color=ink)
    ax.set_xlim(0, min(1.0, max(table[n]["ndcg_hi"] for n in names) + 0.1))
    ax.set_xlabel("nDCG@10 (ESCI fitment queries, 95% bootstrap CI)", color=muted, fontsize=9)
    ax.tick_params(colors=muted, labelsize=9, length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.xaxis.grid(True, color=grid, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="full")
    args = ap.parse_args()
    run_dir = C.RUNS / args.run
    runs = json.loads((run_dir / "runs.json").read_text())
    meta = json.loads((run_dir / "meta.json").read_text())
    qrels = json.loads((C.DATA / "qrels.json").read_text())
    queries = [json.loads(line) for line in open(C.DATA / "queries.jsonl")]
    done = set(runs["bm25"])
    slices = {s: [q["qid"] for q in queries if q["slice"] == s and q["qid"] in done] for s in ("esci", "own")}

    out = C.RESULTS if args.run == "full" else run_dir
    report = {"meta": meta, "slices": {}}
    for s, qids in slices.items():
        if not qids:
            continue
        pq = per_query(runs, qrels, qids)
        table = {}
        for name, m in pq.items():
            d, lo, hi = paired_ci(pq["bm25"]["ndcg"], m["ndcg"])
            _, lo_abs, hi_abs = paired_ci(np.zeros(len(qids)), m["ndcg"])
            dh, lo_h, hi_h = paired_ci(pq["hybrid"]["ndcg"], m["ndcg"])
            ranks = m["rank"]
            table[name] = {
                "ndcg": float(np.mean(m["ndcg"])), "ndcg_lo": lo_abs, "ndcg_hi": hi_abs,
                "mrr": float(np.mean(m["mrr"])), "recall100": float(np.mean(m["recall"])),
                "top10_hit": float(np.mean([r is not None and r <= 10 for r in ranks])),
                "delta_vs_bm25": [d, lo, hi], "delta_vs_hybrid": [dh, lo_h, hi_h],
                "ranks": ranks,
            }
        report["slices"][s] = {"n_queries": len(qids), "table": table}

    (out / "metrics.json").write_text(json.dumps(report, indent=2))

    lines = [f"# Results ({args.run} run)", "",
             f"Corpus: {meta['n_docs']:,} products. Embed: `{meta['embed_model']}`. "
             f"Rerank depth: top {meta['candidates']}.", ""]
    if "esci" in report["slices"]:
        t = report["slices"]["esci"]["table"]
        lines += [f"## ESCI fitment queries (n={report['slices']['esci']['n_queries']})", "",
                  "| Setup | nDCG@10 | MRR@10 | Recall@100 | Δ nDCG vs BM25 (95% CI) |",
                  "|---|---|---|---|---|"]
        for n, r in t.items():
            d, lo, hi = r["delta_vs_bm25"]
            lines.append(f"| {n} | {r['ndcg']:.3f} | {r['mrr']:.3f} | {r['recall100']:.3f} | "
                         f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}] |")
        lines.append("")
        chart(t, out / "ndcg.png")
    if "own" in report["slices"]:
        t = report["slices"]["own"]["table"]
        lines += [f"## Your catalog: fitment queries (n={report['slices']['own']['n_queries']})", "",
                  "Did *your* product make the top 10 among all products in the corpus?", "",
                  "| Setup | In top 10 | MRR@10 | Median rank (top 100) |", "|---|---|---|---|"]
        for n, r in t.items():
            found = [x for x in r["ranks"] if x is not None]
            med = f"{int(np.median(found))}" if found else "not in top 100"
            lines.append(f"| {n} | {r['top10_hit']:.0%} | {r['mrr']:.3f} | {med} |")
        lines.append("")
    lat = meta["latency_ms"]
    lines += ["## Latency (per query, measured from this machine)", "",
              "| Step | p50 ms | p95 ms | n |", "|---|---|---|---|"]
    for k, v in lat.items():
        lines.append(f"| {k} | {v['p50']:.0f} | {v['p95']:.0f} | {v['n']} |")
    lines += ["", "## Usage per 1,000 queries", "", "| Item | Units | Cost |", "|---|---|---|"]
    for row in cost_rows(meta, meta["n_queries"]):
        lines.append("| " + " | ".join(row) + " |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

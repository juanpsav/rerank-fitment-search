"""README figures from results/metrics.json. Run after evaluate.py:  python make_figures.py"""
import json

import matplotlib
import matplotlib.ticker
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import config as C  # noqa: E402

INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#a3a29c"
LABELS = {"bm25": "Keyword (BM25)", "embed": "Embed", "hybrid": "Hybrid",
          "hybrid+rerank-v4.0-fast": "Hybrid + Rerank fast", "hybrid+rerank-v4.0-pro": "Hybrid + Rerank pro"}


def axes(figsize):
    fig, ax = plt.subplots(figsize=figsize, dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_axisbelow(True)
    return fig, ax


def save(fig, name):
    fig.tight_layout()
    fig.savefig(C.RESULTS / name, facecolor=SURFACE)
    plt.close(fig)


def hbars(table, key, name, xlabel, fmt, xmax, pct=False):
    names = list(table)[::-1]
    vals = [table[n][key] for n in names]
    fig, ax = axes((7.5, 3.0))
    ax.barh([LABELS[n] for n in names], vals, height=0.55,
            color=[BLUE if "rerank" in n else GRAY for n in names])
    for y, v in enumerate(vals):
        ax.text(v + xmax * 0.012, y, fmt(v), va="center", fontsize=9, color=INK)
    ax.set_xlim(0, xmax)
    if pct:
        ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xlabel(xlabel, color=MUTED, fontsize=9)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    save(fig, name)


def quality_vs_latency(table, lat):
    """Approximate p50 per setup = sum of the medians of the steps it runs."""
    bm, em = lat["bm25"]["p50"], lat["embed_query"]["p50"]
    ms = {"bm25": bm, "embed": em, "hybrid": bm + em,
          "hybrid+rerank-v4.0-fast": bm + em + lat["rerank-v4.0-fast"]["p50"],
          "hybrid+rerank-v4.0-pro": bm + em + lat["rerank-v4.0-pro"]["p50"]}
    fig, ax = axes((7.5, 3.6))
    for n, x in ms.items():
        y = table[n]["ndcg"]
        ax.scatter(x, y, s=70, color=BLUE if "rerank" in n else GRAY, edgecolor=SURFACE, linewidth=2, zorder=3)
        ax.annotate(f"{LABELS[n]}  {y:.3f}", (x, y), xytext=(8, -3 if n != "hybrid" else -12),
                    textcoords="offset points", fontsize=9, color=INK)
    ax.set_xlim(0, max(ms.values()) * 1.45)
    ax.set_ylim(0.54, 0.72)
    ax.set_xlabel("Approx. median latency per query, ms (sum of step medians, from a laptop)", color=MUTED, fontsize=9)
    ax.set_ylabel("nDCG@10", color=MUTED, fontsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    save(fig, "quality_vs_latency.png")


def per_query_delta(runs_dir, qrels, esci_qids):
    from evaluate import ndcg_at_k
    runs = json.loads((runs_dir / "runs.json").read_text())
    d = np.array([ndcg_at_k(runs["hybrid+rerank-v4.0-pro"][q], qrels[q]) - ndcg_at_k(runs["bm25"][q], qrels[q])
                  for q in esci_qids])
    d = np.sort(d)[::-1]
    wins, losses = int((d > 0.001).sum()), int((d < -0.001).sum())
    fig, ax = axes((7.5, 3.0))
    ax.bar(np.arange(len(d)), d, width=0.8,
           color=[BLUE if v > 0.001 else ORANGE if v < -0.001 else GRAY for v in d])
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_xticks([])
    ax.set_ylabel("Δ nDCG@10 per query", color=MUTED, fontsize=9)
    ax.set_xlabel(f"{len(d)} queries, sorted.  Better: {wins}   Worse: {losses}   Same: {len(d) - wins - losses}",
                  color=MUTED, fontsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    save(fig, "per_query_delta.png")


def main():
    m = json.loads((C.RESULTS / "metrics.json").read_text())
    esci = m["slices"]["esci"]["table"]
    hbars({k: esci[k] for k in ["bm25", "embed", "hybrid"]}, "recall100", "recall_ceiling.png",
          "Recall@100: share of exact matches that reach the reranker", lambda v: f"{v:.0%}", 1.0, pct=True)
    hbars(m["slices"]["own"]["table"], "top10_hit", "store_top10.png",
          "Share of 25 fitment queries where the right product reached the top 10", lambda v: f"{v:.0%}", 1.1, pct=True)
    quality_vs_latency(esci, m["meta"]["latency_ms"])
    qrels = json.loads((C.DATA / "qrels.json").read_text())
    qids = [json.loads(line)["qid"] for line in open(C.DATA / "queries.jsonl") if '"esci"' in line]
    per_query_delta(C.RUNS / "full", qrels, qids)
    print("wrote", ", ".join(p.name for p in sorted(C.RESULTS.glob("*.png"))))


if __name__ == "__main__":
    main()

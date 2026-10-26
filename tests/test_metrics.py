import math

from evaluate import mrr_at_k, ndcg_at_k, paired_ci, recall_at_k

RELS = {"a": 1.0, "b": 0.1, "c": 0.0}


def test_ndcg_perfect_order_is_one():
    assert ndcg_at_k(["a", "b", "c"], RELS) == 1.0


def test_ndcg_swapped_order():
    dcg = 0.1 + 1.0 / math.log2(3)
    idcg = 1.0 + 0.1 / math.log2(3)
    assert math.isclose(ndcg_at_k(["b", "a"], RELS), dcg / idcg)


def test_unjudged_docs_score_zero():
    assert ndcg_at_k(["x", "y"], RELS) == 0.0


def test_mrr_uses_first_exact_only():
    assert mrr_at_k(["b", "x", "a"], RELS) == 1 / 3
    assert mrr_at_k(["b", "c"], RELS) == 0.0


def test_recall():
    assert recall_at_k(["x", "a"], RELS) == 1.0
    assert recall_at_k(["x"], RELS) == 0.0


def test_paired_ci_brackets_mean():
    d, lo, hi = paired_ci([0, 0, 0, 0], [0.1, 0.2, 0.3, 0.4])
    assert math.isclose(d, 0.25) and lo <= d <= hi

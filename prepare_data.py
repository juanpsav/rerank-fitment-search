"""Build the corpus, query set and relevance labels from ESCI (+ your own catalog).

Outputs (in data/):
  corpus.jsonl   {"id", "text", "source"}
  queries.jsonl  {"qid", "query", "slice"}   slice = "esci" | "own"
  qrels.json     {qid: {doc_id: gain}}

Run once:  python prepare_data.py
"""
import html
import json
import random
import re

import pandas as pd
import pyarrow.parquet as pq
import yaml

import config as C

# A query counts as "fitment" if it names a vehicle AND a part/accessory.
MAKES = (r"(?:toyota|tacoma|tundra|4runner|ford|f-?150|f-?250|f-?350|ranger|bronco|chevy|chevrolet|"
         r"silverado|colorado|gmc|sierra|dodge|ram [0-9]{4}|jeep|wrangler|gladiator|cherokee|nissan|"
         r"frontier|titan|honda|civic|accord|crv|cr-v|subaru|outback|forester|tesla|bmw|mercedes|audi|"
         r"vw|volkswagen|hyundai|kia|mazda|lexus|acura)")
PARTS = (r"(?:tonneau|bed cover|bed liner|leveling kit|lift kit|rock slider|mud flap|hitch|running board|"
         r"nerf bar|floor mat|floor liner|seat cover|headlight|tail ?light|fog light|light bar|wiper|bumper|"
         r"grille|grill|tailgate|mirror|brake|rotor|pad|air filter|oil filter|spark plug|alternator|battery|"
         r"radiator|exhaust|muffler|shock|strut|sway bar|control arm|tie rod|wheel|tire|lug nut|roof rack|"
         r"cargo|visor|dash|steering wheel|antenna|license plate|step|fender|hood|cabin filter|o2 sensor|"
         r"sensor|fuel pump|water pump|belt|hose|gasket|bulb|led)")
NOT_PARTS = (r"(?:toy|rc |remote control|kids|boy|girl|baby|t ?shirt|shirt|hat|mug|sticker|decal|lego|"
             r"hot wheels|car seat|stroller|costume|book|poster|ornament|keychain|laptop)")
# Broader net for distractors: anything vehicle-flavoured, so negatives are plausible, not random.
AUTO_ANY = r"\b(?:car|truck|jeep|auto|vehicle|suv|pickup|trailer|rv|motorcycle)\b|" + MAKES


def clean(s) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = html.unescape(re.sub(r"<[^>]+>", " ", str(s)))
    return re.sub(r"\s+", " ", s).strip()


def esci_doc_text(row) -> str:
    parts = [clean(row.product_title)]
    if clean(row.product_brand):
        parts.append(f"Brand: {clean(row.product_brand)}")
    parts += [clean(row.product_bullet_point), clean(row.product_description)]
    return "\n".join(p for p in parts if p)[: C.MAX_DOC_CHARS]


def load_esci():
    ex = pd.read_parquet(C.RAW / "shopping_queries_dataset_examples.parquet")
    ex = ex[ex.product_locale == "us"]
    q = ex["query"].str.lower()
    fit = (q.str.contains(rf"\b{MAKES}\b", regex=True)
           & q.str.contains(rf"\b{PARTS}", regex=True)
           & ~q.str.contains(NOT_PARTS, regex=True))
    labeled = ex[fit]
    rng = random.Random(C.SEED)
    others = ex[~fit & q.str.contains(AUTO_ANY, regex=True)]
    pool = sorted(set(others.product_id) - set(labeled.product_id))
    distractors = rng.sample(pool, min(C.N_DISTRACTORS, len(pool)))
    return labeled, distractors


def load_products(ids):
    t = pq.read_table(
        C.RAW / "shopping_queries_dataset_products.parquet",
        columns=["product_id", "product_title", "product_description", "product_bullet_point",
                 "product_brand", "product_locale"],
        filters=[("product_locale", "=", "us"), ("product_id", "in", list(ids))],
    )
    return t.to_pandas().drop_duplicates("product_id")


def load_own_catalog():
    """Your ~/catalog-optimizer products and their fitment-tier queries. Text fields only, as indexed."""
    docs, queries, qrels = [], [], {}
    for prod in sorted((C.CATALOG_DIR / "products").glob("*/current.json")):
        slug = prod.parent.name
        d = json.loads(prod.read_text())
        text = "\n".join(filter(None, [
            clean(d.get("title")), f"Brand: {d.get('vendor')}" if d.get("vendor") else "",
            clean(d.get("description_html")), " ".join(d.get("tags") or []), d.get("product_type") or "",
        ]))[: C.MAX_DOC_CHARS]
        doc_id = f"own:{slug}"
        docs.append({"id": doc_id, "text": text, "source": "own"})
        prompts = C.CATALOG_DIR / "prompts" / f"{slug}.yaml"
        if prompts.exists():
            for i, query in enumerate(yaml.safe_load(prompts.read_text())["tiers"].get("fitment", [])):
                qid = f"own:{slug}:{i}"
                queries.append({"qid": qid, "query": query, "slice": "own"})
                qrels[qid] = {doc_id: C.GAINS["E"]}
    return docs, queries, qrels


def main():
    C.DATA.mkdir(parents=True, exist_ok=True)
    labeled, distractors = load_esci()
    products = load_products(set(labeled.product_id) | set(distractors))
    have = set(products.product_id)

    corpus = [{"id": r.product_id, "text": esci_doc_text(r),
               "source": "labeled" if r.product_id in set(labeled.product_id) else "distractor"}
              for r in products.itertuples()]
    queries, qrels = [], {}
    for qid, g in labeled.groupby("query_id"):
        qrels[str(qid)] = {p: C.GAINS[l] for p, l in zip(g.product_id, g.esci_label) if p in have}
        queries.append({"qid": str(qid), "query": g["query"].iloc[0], "slice": "esci"})

    if C.CATALOG_DIR.exists():
        own_docs, own_q, own_qrels = load_own_catalog()
        corpus += own_docs
        queries += own_q
        qrels.update(own_qrels)

    with open(C.DATA / "corpus.jsonl", "w") as f:
        for d in corpus:
            f.write(json.dumps(d) + "\n")
    with open(C.DATA / "queries.jsonl", "w") as f:
        for q in queries:
            f.write(json.dumps(q) + "\n")
    (C.DATA / "qrels.json").write_text(json.dumps(qrels))

    by_src = pd.Series([d["source"] for d in corpus]).value_counts().to_dict()
    by_slice = pd.Series([q["slice"] for q in queries]).value_counts().to_dict()
    print(f"corpus: {len(corpus)} docs {by_src}")
    print(f"queries: {len(queries)} {by_slice}")


if __name__ == "__main__":
    main()

#!/bin/sh
# Downloads the Amazon Shopping Queries (ESCI) dataset, Apache-2.0. ~1.2 GB.
set -e
mkdir -p data/raw
base=https://github.com/amazon-science/esci-data/raw/main/shopping_queries_dataset
for f in examples products; do
  curl -fSL -o data/raw/shopping_queries_dataset_$f.parquet $base/shopping_queries_dataset_$f.parquet
done

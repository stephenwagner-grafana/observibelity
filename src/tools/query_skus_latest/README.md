# query_skus_latest

SQL endpoint for the multi-hop retrieval demo. Takes a regex pattern the
upstream LLM has constructed from a product.id (replacing version digits with
`.` wildcards) and returns the rows from `catalog_items` whose `sku` matches
under Postgres `~`, filtered to `is_latest_SKU_for_product = TRUE`.

Tool emits per-row span attributes (`retrieval.candidate.N`,
`retrieval.selected_year`, `retrieval.year_mismatch`, …) so Tempo renders the
4 near-identical SKU rows as a column the audience can eye-scan. See
[../README.md](../README.md).

# verify_inventory

LLM-using "inventory verify" tool. Sits between `search_products` and `nc-best-deals` in the cross-gen-retrieval-drift demo. Takes a full product SKU, asks the gateway to summarize it for forwarding (the system prompt deliberately tells the LLM to keep the payload under 32 characters + literal `"..."` — the planted bit-budget bug), then HTTP POSTs the truncated SKU to `nc-best-deals/v1/run` and surfaces its selected SKU + price.

The truncation step is real: the LLM produces a truncated string per the buggy system prompt; if it didn't (or hallucinated something else), the tool deterministically truncates so the demo is stable. The trace carries both the original SKU and the truncated form on this tool's span as `verify.original_sku` and `verify.truncated_sku` — that's how the audience reads the bit-budget bug.

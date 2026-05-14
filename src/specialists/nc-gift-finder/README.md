# nc-gift-finder

NeonCart's gift-recommendation specialist. Dedicated agent (separate from
`nc-chatbot`) so the demo surfaces a second `agent_name` in Sigil and a
clean per-specialist eval surface.

## Surfaces

* `POST /v1/run` — `SpecialistRequest`→`SpecialistResponse` (see `_base`).
* `GET /health`, `/readyz`, `/metrics` — standard.

## Tools used

* `search_products` — within-budget catalog search.
* `get_product` — pull a single SKU when the user names it specifically.
* `add_to_cart` — log the add-to-cart intent (the frontend cookie update
  happens client-side, this just makes it visible to Sigil/Grafana).

## Loadgen

Drive it with messages like:

    "find me a gift under $200 for someone who likes audio"
    "i need a keyboard for my dad, around $150"
    "what's a good gaming gift, budget about $300"

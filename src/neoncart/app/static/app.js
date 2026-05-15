// NeonCart chat widget — vanilla fetch + rich rendering.
//
// Replaces the previous HTMX-fragment flow with a JSON round-trip so the
// widget can show model + provider, tool calls, returned products as
// clickable cards, a deep-link into the Sigil conversation view, and
// applied navigation hints (the bot can route the catalog grid behind the
// open chat).
//
// Wire shape from POST /chat (mirrors neoncart.app.main.ChatResponse):
//   {
//     reply, tool_calls[], usecase,
//     model, provider, actions[], products[],
//     cost_usd, session_id, span_id, sigil_url
//   }
(function () {
  const root = document.getElementById("nc-chat");
  const toggleBtn = document.getElementById("nc-chat-toggle");
  const closeBtn = document.getElementById("nc-chat-close");
  const panel = document.getElementById("nc-chat-panel");
  const messages = document.getElementById("chat-messages");
  const form = document.getElementById("nc-chat-form");
  const input = document.getElementById("nc-chat-input");
  const suggestions = document.getElementById("nc-chat-suggestions");
  const sessionInput = document.getElementById("nc-chat-session");
  const personaInput = document.getElementById("nc-chat-persona");
  const emailInput = document.getElementById("nc-chat-email");

  // Mint one session_id per page load so every message in this visit shows
  // up as a single conversation in Sigil instead of N one-turn convos.
  function newSessionId() {
    if (window.crypto && window.crypto.randomUUID) {
      return window.crypto.randomUUID().replace(/-/g, "");
    }
    return (
      Date.now().toString(36) +
      Math.random().toString(36).slice(2, 10) +
      Math.random().toString(36).slice(2, 10)
    );
  }
  if (sessionInput && !sessionInput.value) sessionInput.value = newSessionId();

  function setOpen(open) {
    if (!root) return;
    root.dataset.open = open ? "true" : "false";
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", open ? "true" : "false");
    if (panel) panel.setAttribute("aria-hidden", open ? "false" : "true");
    if (open && input) setTimeout(() => input.focus(), 50);
    if (open) scrollToBottom();
  }

  function scrollToBottom() {
    if (messages) messages.scrollTop = messages.scrollHeight;
  }

  function escapeHTML(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Tiny markdown: bold, italic, bullets, line breaks. Anything richer (links,
  // code blocks) intentionally not handled — the LLM is told to stay concise.
  function renderMarkdown(s) {
    let out = escapeHTML(s);
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/(^|\W)\*([^*\n]+)\*(\W|$)/g, "$1<em>$2</em>$3");
    out = out.replace(/(^|\n)\s*[-*]\s+(.+?)(?=\n|$)/g, "$1<li>$2</li>");
    out = out.replace(/((?:<li>[^<]*<\/li>\s*)+)/g, "<ul class=\"chat-list\">$1</ul>");
    out = out.replace(/\n/g, "<br>");
    return out;
  }

  function appendUser(text) {
    const div = document.createElement("div");
    div.className = "chat-msg chat-msg--user";
    div.textContent = text;
    messages.appendChild(div);
    scrollToBottom();
    return div;
  }

  function appendBotShell() {
    const wrap = document.createElement("div");
    wrap.className = "chat-msg chat-msg--bot chat-msg--shell";
    const body = document.createElement("div");
    body.className = "chat-msg__body";
    body.innerHTML = '<span class="chat-typing"><span></span><span></span><span></span></span>';
    wrap.appendChild(body);
    messages.appendChild(wrap);
    scrollToBottom();
    return { wrap, body };
  }

  // Small dim header at the top of the bot bubble showing which agent +
  // model+provider answered. Empty `model` still renders the agent so the
  // demo audience sees which specialist took the turn (gift-finder vs.
  // chatbot routing decision).
  function renderBadges(data) {
    const agent = data && data.agent;
    const model = data && data.model;
    if (!agent && !model) return null;
    const parts = [];
    if (agent) {
      parts.push(agent === "gift-finder" ? "nc-gift-finder" : "nc-chatbot");
    }
    if (model) parts.push(model);
    if (data && data.provider) parts.push(data.provider);
    const row = document.createElement("div");
    row.className = "chat-msg__badge";
    if (agent === "gift-finder") row.classList.add("chat-msg__badge--gift");
    row.textContent = parts.join(" · ");
    return row;
  }

  function renderProducts(products) {
    if (!Array.isArray(products) || !products.length) return null;
    const rail = document.createElement("div");
    rail.className = "chat-products";
    products.slice(0, 6).forEach((p) => {
      const id = p.id || p.product_id;
      const name = p.name || p.title || "Product";
      const price = p.price_usd != null ? p.price_usd : p.price;
      const sku = p.sku || "";
      const img = p.image_url || "";
      const card = document.createElement("div");
      card.className = "chat-product";
      card.dataset.productId = id || "";
      const productLink = id ? `/products/${id}` : "#";
      card.innerHTML =
        `<a class="chat-product__link" href="${productLink}">`
        +   `<span class="chat-product__img"${img ? ` style="background-image:url('${escapeHTML(img)}')"` : ""}></span>`
        +   `<span class="chat-product__name">${escapeHTML(name)}</span>`
        +   `<span class="chat-product__row">`
        +     (price != null ? `<span class="chat-product__price">$${Number(price).toFixed(2)}</span>` : "")
        +     (sku ? `<span class="chat-product__sku">${escapeHTML(sku)}</span>` : "")
        +   `</span>`
        + `</a>`
        + (id ? `<button type="button" class="chat-product__add" data-product-id="${id}" data-sku="${escapeHTML(sku)}" aria-label="Add ${escapeHTML(name)} to cart">+ Add to cart</button>` : "");
      rail.appendChild(card);
    });
    return rail;
  }

  // Cart-add button click handler: POST /api/cart/add, animate the button to
  // confirm, bump the header cart counter, and broadcast a custom event so
  // any other listeners (e.g. analytics) can hook in.
  function addToCart(productId, sku) {
    if (!productId) return;
    return fetch("/api/cart/add", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ product_id: Number(productId), qty: 1 }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data && data.ok) {
          updateCartCounter(data.count);
          window.dispatchEvent(new CustomEvent("nc:cart:add", { detail: { productId, sku, count: data.count } }));
        }
        return data;
      });
  }

  function updateCartCounter(count) {
    const el = document.getElementById("nc-cart-count");
    if (!el) return;
    if (!count) {
      el.textContent = "";
      el.classList.remove("nc-cart-count--has");
      return;
    }
    el.textContent = String(count);
    el.classList.add("nc-cart-count--has");
    // Quick pop animation so the eye catches the count change.
    el.classList.remove("nc-cart-count--pop");
    // Force reflow so re-adding the class restarts the animation.
    void el.offsetWidth;
    el.classList.add("nc-cart-count--pop");
  }

  // Read the nc_cart cookie on load so the badge reflects pre-existing
  // state (e.g. user added items, refreshed the page).
  function initCartCounter() {
    fetch("/api/cart", { headers: { "Accept": "application/json" } })
      .then((r) => r.json())
      .then((data) => updateCartCounter((data && data.count) || 0))
      .catch(() => {});
  }

  // Render the first navigate action under the reply text.
  //
  // Two flavours:
  //   * auto:true   — the agent explicitly called the `navigate` tool. We
  //                   honour it: render a "Taking you to ..." pill AND
  //                   redirect after ~1.4s so the user gets to read the
  //                   reply before the page swaps.
  //   * auto:false  — keyword-fallback nav synthesised from search hits
  //                   (legacy behaviour). Click-to-go button only; the
  //                   page never moves until the user clicks.
  function renderNavigate(actions) {
    if (!Array.isArray(actions) || !actions.length) return null;
    const nav = actions.find((a) => a && a.type === "navigate");
    if (!nav) return null;
    // Prefer the URL the navigate tool returned (carries the canonical
    // shape including any future params we add). Fall back to building
    // from (target, value) for keyword-synth actions.
    let href = nav.url || null;
    let label = nav.label || null;
    if (!href) {
      if (nav.target === "category" && nav.value) {
        href = `/catalog?category=${encodeURIComponent(nav.value)}`;
        label = label || `Browse ${prettyCategorySlug(nav.value)}`;
      } else if (nav.target === "search" && nav.value) {
        href = `/catalog?q=${encodeURIComponent(nav.value)}`;
        label = label || `Search "${nav.value}"`;
      } else if (nav.target === "product" && nav.value) {
        href = `/products/${encodeURIComponent(nav.value)}`;
        label = label || "View product";
      } else if (nav.target === "cart") {
        href = `/cart`;
        label = label || "Go to cart";
      }
    }
    if (!href) return null;
    label = label || "Open";
    const a = document.createElement("a");
    a.className = "chat-nav-btn";
    a.href = href;
    if (nav.auto) {
      a.classList.add("chat-nav-btn--auto");
      a.innerHTML =
        `<span class="chat-nav-btn__spin" aria-hidden="true">↻</span> `
        + `Taking you to ${escapeHTML(label)}…`;
      // Defer the redirect so the bubble paints and the user reads the
      // reply text. setTimeout (not requestIdleCallback) so the delay is
      // predictable for a demo.
      setTimeout(() => {
        window.location.href = href;
      }, 1400);
    } else {
      a.innerHTML = `<span aria-hidden="true">&rarr;</span> ${escapeHTML(label)}`;
    }
    return a;
  }

  // "peripherals" -> "Peripherals"; "smart-home" -> "Smart Home".
  function prettyCategorySlug(slug) {
    return String(slug || "")
      .split("-")
      .map((s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s))
      .join(" ");
  }

  function renderSigilLink(data) {
    if (!data.sigil_url) return null;
    const row = document.createElement("div");
    row.className = "chat-msg__sigil";
    row.innerHTML =
      `<a href="${escapeHTML(data.sigil_url)}" target="_blank" rel="noopener" class="chat-sigil-link">`
      + `&#128279; Open conversation in Sigil`
      + `</a>`;
    return row;
  }

  function fillBotShell(shell, data) {
    // Reset the shell's contents so we can build the bubble top-to-bottom:
    // badge (model/provider) → reply text → product cards → navigate button
    // → "Open in Sigil" link.
    shell.wrap.innerHTML = "";

    // 1) badge — small dim model/provider header at the TOP of the bubble.
    const badge = renderBadges(data);
    if (badge) shell.wrap.appendChild(badge);

    // 2) reply body (markdown).
    const body = document.createElement("div");
    body.className = "chat-msg__body";
    body.innerHTML = renderMarkdown(data.reply || "");
    shell.wrap.appendChild(body);
    shell.body = body;

    // 3) product cards (if any).
    const prods = renderProducts(data.products);
    if (prods) shell.wrap.appendChild(prods);

    // 4) single navigate button surfaced from actions[].
    const nav = renderNavigate(data.actions);
    if (nav) shell.wrap.appendChild(nav);

    // 5) "Open in Sigil" deep-link, bottom-right of bubble.
    const sig = renderSigilLink(data);
    if (sig) shell.wrap.appendChild(sig);

    shell.wrap.classList.remove("chat-msg--shell");
    scrollToBottom();
  }

  function fillBotShellError(shell, text) {
    shell.wrap.classList.add("chat-msg--err");
    shell.wrap.classList.remove("chat-msg--shell");
    shell.body.innerHTML = escapeHTML(text);
    scrollToBottom();
  }

  function hideSuggestions() {
    if (suggestions) suggestions.classList.add("nc-chat__suggestions--hidden");
  }

  function sendMessage(text) {
    text = (text || "").trim();
    if (!text) return;
    appendUser(text);
    hideSuggestions();
    const shell = appendBotShell();
    if (input) input.value = "";
    const body = {
      message: text,
      persona_id: personaInput ? personaInput.value : "",
      email: emailInput ? emailInput.value : "",
      session_id: sessionInput ? sessionInput.value : "",
      provider_override: "anthropic",
      traffic_origin: "interactive",
    };
    fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json().catch(() => ({ reply: "(invalid response)", error: "parse" })))
      .then((data) => {
        if (!data || (data.error && !data.reply)) {
          fillBotShellError(shell, data && data.reply ? data.reply : "Chat failed.");
          return;
        }
        fillBotShell(shell, data);
      })
      .catch((err) => {
        fillBotShellError(shell, "Network error: " + (err && err.message || err));
      });
  }

  if (toggleBtn) toggleBtn.addEventListener("click", () => setOpen(root.dataset.open !== "true"));
  if (closeBtn) closeBtn.addEventListener("click", () => setOpen(false));

  if (suggestions) {
    suggestions.addEventListener("click", (evt) => {
      const btn = evt.target.closest("[data-suggestion]");
      if (!btn) return;
      sendMessage(btn.dataset.suggestion || btn.textContent.trim());
    });
  }

  if (form) {
    form.addEventListener("submit", (evt) => {
      evt.preventDefault();
      sendMessage(input ? input.value : "");
    });
  }

  // Hero gift-finder card on the homepage. Clicking any `[data-gift-prompt]`
  // chip opens the chat widget and immediately fires that prompt — the
  // gift-finder route picks it up via the keyword detector. The `[data-gift-open]`
  // CTA just opens the widget (no auto-send) so the user can compose freely.
  document.querySelectorAll("[data-gift-prompt], [data-gift-open]").forEach((btn) => {
    btn.addEventListener("click", (evt) => {
      evt.preventDefault();
      const prompt = btn.dataset.giftPrompt;
      setOpen(true);
      if (prompt) {
        // Give the panel layout a tick before submit so the typing
        // indicator + bubble animate cleanly.
        setTimeout(() => sendMessage(prompt), 120);
      } else if (input) {
        setTimeout(() => input.focus(), 200);
      }
    });
  });

  // Delegate Add-to-cart clicks anywhere inside the chat panel so the
  // handler survives every re-render of the bubble cards.
  if (messages) {
    messages.addEventListener("click", (evt) => {
      const btn = evt.target.closest(".chat-product__add");
      if (!btn) return;
      evt.preventDefault();
      const pid = btn.dataset.productId;
      const sku = btn.dataset.sku || "";
      if (!pid || btn.disabled) return;
      btn.disabled = true;
      btn.classList.add("chat-product__add--loading");
      addToCart(pid, sku)
        .then((data) => {
          if (data && data.ok) {
            btn.classList.remove("chat-product__add--loading");
            btn.classList.add("chat-product__add--added");
            btn.textContent = "✓ Added";
            setTimeout(() => {
              btn.classList.remove("chat-product__add--added");
              btn.textContent = "+ Add to cart";
              btn.disabled = false;
            }, 1800);
          } else {
            btn.disabled = false;
            btn.classList.remove("chat-product__add--loading");
          }
        })
        .catch(() => {
          btn.disabled = false;
          btn.classList.remove("chat-product__add--loading");
        });
    });
  }

  // Cart page clear-cart button.
  const clearBtn = document.getElementById("nc-cart-clear");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      fetch("/api/cart/clear", { method: "POST" })
        .then(() => { window.location.reload(); })
        .catch(() => {});
    });
  }

  initCartCounter();
})();

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

  // Small dim header at the top of the bot bubble showing which model+provider
  // answered. Empty `model` hides the whole row so demo turns that came back
  // without a model attribution don't show a half-empty badge.
  function renderBadges(data) {
    const model = data && data.model;
    if (!model) return null;
    const parts = ["nc-chatbot", model];
    if (data.provider) parts.push(data.provider);
    const row = document.createElement("div");
    row.className = "chat-msg__badge";
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
      const card = document.createElement("a");
      card.className = "chat-product";
      card.href = id ? `/products/${id}` : "#";
      card.innerHTML =
        `<span class="chat-product__img"${img ? ` style="background-image:url('${escapeHTML(img)}')"` : ""}></span>`
        + `<span class="chat-product__name">${escapeHTML(name)}</span>`
        + `<span class="chat-product__row">`
        + (price != null ? `<span class="chat-product__price">$${Number(price).toFixed(2)}</span>` : "")
        + (sku ? `<span class="chat-product__sku">${escapeHTML(sku)}</span>` : "")
        + `</span>`;
      rail.appendChild(card);
    });
    return rail;
  }

  // Render the first navigate action (target=category|search|product|cart) as
  // a clickable button under the reply text. Spec change: previously this
  // auto-redirected on a timer; now it surfaces a button the user can click,
  // which keeps the chat open and the choice visible to the demo audience.
  function renderNavigate(actions) {
    if (!Array.isArray(actions) || !actions.length) return null;
    const nav = actions.find((a) => a && a.type === "navigate" && a.value);
    if (!nav) return null;
    let href = null;
    let label = "Open";
    if (nav.target === "category") {
      href = `/catalog?category=${encodeURIComponent(nav.value)}`;
      label = `Browse ${prettyCategorySlug(nav.value)}`;
    } else if (nav.target === "search") {
      href = `/catalog?q=${encodeURIComponent(nav.value)}`;
      label = `Search "${nav.value}"`;
    } else if (nav.target === "product") {
      href = `/products/${encodeURIComponent(nav.value)}`;
      label = "View product";
    } else if (nav.target === "cart") {
      href = `/cart`;
      label = "Go to cart";
    }
    if (!href) return null;
    const a = document.createElement("a");
    a.className = "chat-nav-btn";
    a.href = href;
    a.innerHTML = `<span aria-hidden="true">&rarr;</span> ${escapeHTML(label)}`;
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
})();

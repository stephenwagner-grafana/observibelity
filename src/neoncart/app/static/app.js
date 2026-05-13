// NeonCart minimal client JS:
//   1) toggle the chat widget open/closed
//   2) echo the user's message into the panel BEFORE the server replies, so
//      Send never feels like "my text just disappeared" even if /chat errors
//   3) suggestion chips: click to send a canned question
//   4) auto-scroll #chat-messages to the bottom after every HTMX swap
//
// Anything richer (markdown rendering, streaming, etc.) is intentionally
// kept on the server side -- this keeps the demo's failure surface visible.
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

  // Generate a fresh session_id on every page load so each visit shows up as
  // a new conversation in Sigil. Format mirrors uuid4 without the dashes so
  // it's short enough for Loki label cardinality but still globally unique.
  function newSessionId() {
    if (window.crypto && window.crypto.randomUUID) {
      return window.crypto.randomUUID().replace(/-/g, "");
    }
    // Fallback for older browsers: time + random.
    return (
      Date.now().toString(36) +
      Math.random().toString(36).slice(2, 10) +
      Math.random().toString(36).slice(2, 10)
    );
  }
  if (sessionInput) sessionInput.value = newSessionId();

  function setOpen(open) {
    if (!root) return;
    root.dataset.open = open ? "true" : "false";
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", open ? "true" : "false");
    if (panel) panel.setAttribute("aria-hidden", open ? "false" : "true");
    if (open && input) {
      // small delay so the panel finishes laying out before focus
      setTimeout(() => input.focus(), 50);
    }
    if (open && messages) scrollToBottom();
  }

  function scrollToBottom() {
    if (!messages) return;
    messages.scrollTop = messages.scrollHeight;
  }

  function escapeHTML(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function echoUserMessage(text) {
    if (!messages || !text) return;
    const div = document.createElement("div");
    div.className = "chat-msg chat-msg--user";
    div.textContent = text;
    messages.appendChild(div);
    scrollToBottom();
  }

  function hideSuggestions() {
    if (suggestions) suggestions.classList.add("nc-chat__suggestions--hidden");
  }

  if (toggleBtn) toggleBtn.addEventListener("click", () => setOpen(root.dataset.open !== "true"));
  if (closeBtn) closeBtn.addEventListener("click", () => setOpen(false));

  // Suggestion chip click: fill input + submit. The chip text becomes the
  // user message so the loadgen-style demos can be reproduced one click in.
  if (suggestions) {
    suggestions.addEventListener("click", (evt) => {
      const btn = evt.target.closest("[data-suggestion]");
      if (!btn || !input || !form) return;
      input.value = btn.dataset.suggestion || btn.textContent.trim();
      // Submit via HTMX so the request goes through the configured swap target.
      if (window.htmx && typeof window.htmx.trigger === "function") {
        window.htmx.trigger(form, "submit");
      } else {
        form.requestSubmit();
      }
    });
  }

  // Echo user message before HTMX fires the request, so the chat panel
  // never goes blank between Send and the server reply (and never erases
  // what they typed even if the response is empty / errors).
  if (form) {
    form.addEventListener("htmx:configRequest", (evt) => {
      const text = (input && input.value || "").trim();
      if (!text) return;
      echoUserMessage(text);
      hideSuggestions();
    });
    // Clear the input only after the request kicks off (configRequest fires
    // before send). We do this here instead of via hx-on::after-request so
    // the input clears immediately on send, not after the server replies.
    form.addEventListener("htmx:beforeRequest", () => {
      if (input) input.value = "";
    });
    // If the server returns 4xx/5xx, swap anyway so the user sees the error
    // bubble instead of silence.
    form.addEventListener("htmx:beforeSwap", (evt) => {
      const status = evt.detail.xhr && evt.detail.xhr.status;
      if (status >= 400 && status < 600) {
        evt.detail.shouldSwap = true;
        evt.detail.isError = false;
      }
    });
  }

  // After every HTMX swap into chat-messages, pin to bottom.
  document.body.addEventListener("htmx:afterSwap", (evt) => {
    if (evt.target && evt.target.id === "chat-messages") scrollToBottom();
  });
})();

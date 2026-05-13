// NeonCart minimal client JS:
//   1) toggle the chat widget open/closed
//   2) auto-scroll #chat-messages to the bottom after every HTMX swap
//
// Anything richer (markdown rendering, streaming, etc.) is intentionally
// kept on the server side -- this keeps the demo's failure surface visible.
(function () {
  const root = document.getElementById("nc-chat");
  const toggleBtn = document.getElementById("nc-chat-toggle");
  const closeBtn = document.getElementById("nc-chat-close");
  const panel = document.getElementById("nc-chat-panel");
  const messages = document.getElementById("chat-messages");

  function setOpen(open) {
    if (!root) return;
    root.dataset.open = open ? "true" : "false";
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", open ? "true" : "false");
    if (panel) panel.setAttribute("aria-hidden", open ? "false" : "true");
    if (open && messages) scrollToBottom();
  }

  function scrollToBottom() {
    if (!messages) return;
    messages.scrollTop = messages.scrollHeight;
  }

  if (toggleBtn) toggleBtn.addEventListener("click", () => setOpen(root.dataset.open !== "true"));
  if (closeBtn) closeBtn.addEventListener("click", () => setOpen(false));

  // After every HTMX swap into chat-messages, pin to bottom.
  document.body.addEventListener("htmx:afterSwap", (evt) => {
    if (evt.target && evt.target.id === "chat-messages") scrollToBottom();
  });
})();

// Ask Acme — minimal client JS:
//   1) toggle the chat widget open/closed
//   2) auto-scroll #chat-messages to bottom after each HTMX swap
//   3) persona picker: fetches /api/personas, sets a cookie via /api/persona/select
(function () {
  // --- chat -----------------------------------------------------------
  const root = document.getElementById("ab-chat");
  const toggleBtn = document.getElementById("ab-chat-toggle");
  const closeBtn = document.getElementById("ab-chat-close");
  const panel = document.getElementById("ab-chat-panel");
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
  document.body.addEventListener("htmx:afterSwap", (evt) => {
    if (evt.target && evt.target.id === "chat-messages") scrollToBottom();
  });

  // --- persona picker -------------------------------------------------
  function getCookie(name) {
    return document.cookie
      .split("; ")
      .map((c) => c.split("="))
      .find(([k]) => k === name)?.[1];
  }
  function setCurrent(label, persona) {
    if (label) label.textContent = persona ? persona.name : "(none)";
  }

  const picker = document.querySelector("[data-persona-picker]");
  if (!picker) return;
  const pickerToggle = picker.querySelector(".ab-persona-picker__toggle");
  const menu = picker.querySelector("[data-persona-menu]");
  const currentLabel = picker.querySelector("[data-persona-current]");

  let personas = [];
  fetch("/api/personas")
    .then((r) => (r.ok ? r.json() : []))
    .then((rows) => {
      personas = rows || [];
      // Hydrate the menu
      menu.innerHTML = personas
        .map(
          (p) =>
            `<li role="option" data-persona-id="${p.id}">
               <strong>${p.name}</strong>
               <small>${p.department || p.role || ""}</small>
             </li>`
        )
        .join("");
      // Reflect current selection
      const cur = getCookie("supportbot_persona_id");
      const match = personas.find((p) => String(p.id) === String(cur));
      setCurrent(currentLabel, match);
    })
    .catch(() => {});

  pickerToggle.addEventListener("click", () => {
    const isHidden = menu.hasAttribute("hidden");
    if (isHidden) menu.removeAttribute("hidden");
    else menu.setAttribute("hidden", "");
  });

  menu.addEventListener("click", (evt) => {
    const li = evt.target.closest("li[data-persona-id]");
    if (!li) return;
    const id = li.dataset.personaId;
    fetch("/api/persona/select", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ persona_id: id }),
    })
      .then(() => {
        const match = personas.find((p) => String(p.id) === String(id));
        setCurrent(currentLabel, match);
        menu.setAttribute("hidden", "");
      })
      .catch(() => {});
  });

  document.addEventListener("click", (evt) => {
    if (!picker.contains(evt.target) && !menu.hasAttribute("hidden")) {
      menu.setAttribute("hidden", "");
    }
  });
})();

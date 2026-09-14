function togglePassword(inputId) {
  const el = document.getElementById(inputId);
  if (!el) return;
  el.type = el.type === "password" ? "text" : "password";
}

function openBlogModal(title, content) {
  const modal = document.getElementById("blogModal");
  if (!modal) return;
  const t = document.getElementById("blogModalTitle");
  const b = document.getElementById("blogModalBody");
  if (t) t.textContent = title || "Blog";
  if (b) {
    const safe = String(content || "");
    b.textContent = safe;
  }
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeBlogModal() {
  const modal = document.getElementById("blogModal");
  if (!modal) return;
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeBlogModal();
});

function initBlogModalButtons() {
  const buttons = document.querySelectorAll(".blog-open-btn");
  if (!buttons.length) return;
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      openBlogModal(btn.dataset.title || "Blog", btn.dataset.content || "");
    });
  });
}

function toLabelText(value) {
  const cleaned = String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return "Input";
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function ensureFormLabels() {
  // Adds missing labels for older forms without changing the template markup.
  const fields = document.querySelectorAll("form input, form textarea, form select");
  fields.forEach((field, idx) => {
    const tag = field.tagName.toLowerCase();
    const type = (field.getAttribute("type") || "").toLowerCase();
    if (type === "hidden" || type === "submit" || type === "button" || type === "reset" || tag === "button") return;
    if (field.closest(".password-wrap") && type !== "checkbox") {
      const parent = field.closest(".password-wrap");
      if (!parent || parent.previousElementSibling?.tagName?.toLowerCase() === "label") return;
      const label = document.createElement("label");
      if (!field.id) field.id = `${field.name || "field"}-${idx}`;
      label.setAttribute("for", field.id);
      label.textContent = toLabelText(field.getAttribute("placeholder") || field.name || "Input");
      parent.parentNode.insertBefore(label, parent);
      return;
    }
    if (field.closest("label")) return;
    if (!field.id) field.id = `${field.name || "field"}-${idx}`;
    const hasForLabel = field.form?.querySelector(`label[for="${field.id}"]`);
    if (hasForLabel) return;
    const prev = field.previousElementSibling;
    if (prev && prev.tagName.toLowerCase() === "label") return;
    const label = document.createElement("label");
    label.setAttribute("for", field.id);
    label.textContent = toLabelText(field.getAttribute("placeholder") || field.name || "Input");
    field.parentNode.insertBefore(label, field);
  });
}

function initDeleteConfirmations() {
  // Destructive admin actions get one browser confirmation.
  const deleteForms = document.querySelectorAll(
    "form[action*='/delete'], form button.btn-dark"
  );
  deleteForms.forEach((node) => {
    const form = node.tagName.toLowerCase() === "form" ? node : node.closest("form");
    if (!form || form.dataset.confirmBound === "1") return;
    form.dataset.confirmBound = "1";
    form.addEventListener("submit", (e) => {
      const ok = window.confirm("Are you sure you want to continue? This action cannot be undone.");
      if (!ok) e.preventDefault();
    });
  });
}

async function initHeroVideoStreams() {
  // Large hero videos are fetched once and then played from an object URL.
  const videos = document.querySelectorAll("video[data-stream-src]");
  if (!videos.length) return;
  for (const video of videos) {
    video.loop = true;
    video.muted = true;
    video.autoplay = true;
    video.playsInline = true;
    const src = video.getAttribute("data-stream-src");
    if (!src) continue;
    try {
      const response = await fetch(src, { cache: "force-cache" });
      if (!response.ok) throw new Error("video fetch failed");
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      video.src = objectUrl;
      video.dataset.objectUrl = objectUrl;
      video.play().catch(() => {});
    } catch (err) {
      video.src = src;
    }
    video.addEventListener("ended", () => {
      video.currentTime = 0;
      video.play().catch(() => {});
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initBlogModalButtons();
  ensureFormLabels();
  initDeleteConfirmations();
  initHeroVideoStreams();
});

window.addEventListener("beforeunload", () => {
  document.querySelectorAll("video[data-object-url]").forEach((video) => {
    try {
      URL.revokeObjectURL(video.dataset.objectUrl);
    } catch (e) {}
  });
});

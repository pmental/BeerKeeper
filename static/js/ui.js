const UI = (() => {
  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function toast(message, type = "info") {
    const wrap = document.getElementById("toast-wrap");
    const el = document.createElement("div");
    el.className = "toast" + (type === "error" ? " error" : "");
    el.textContent = message;
    wrap.appendChild(el);
    setTimeout(() => el.remove(), 4200);
  }

  function fmtDate(iso) {
    if (!iso) return "";
    // Dates already arrive as ISO (YYYY-MM-DD) from the API and from native
    // <input type=date> values, so this just guarantees zero-padding rather
    // than reformatting into a locale string.
    const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return `${m[1]}-${m[2]}-${m[3]}`;
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function fmtDateTime(iso) {
    // For any future timestamp (date + time) display: ISO date, 24h clock.
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return String(iso);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  // ---------- Units ----------

  const OZ_TO_ML = 29.5735295625;

  function volumeUnitLabel(unitSystem) {
    return unitSystem === "metric" ? "mL" : "oz";
  }

  // Canonical storage is always fluid ounces; convert only for display/entry.
  function ozToDisplay(oz, unitSystem) {
    if (oz === null || oz === undefined || oz === "") return "";
    const n = Number(oz);
    if (isNaN(n)) return "";
    if (unitSystem === "metric") return Math.round(n * OZ_TO_ML);
    return Math.round(n * 10) / 10;
  }

  function displayToOz(value, unitSystem) {
    if (value === null || value === undefined || value === "") return null;
    const n = Number(value);
    if (isNaN(n)) return null;
    const oz = unitSystem === "metric" ? n / OZ_TO_ML : n;
    return Math.round(oz * 1000) / 1000;
  }

  let modalStack = 0;

  function openModal(innerHtml, { onMount } = {}) {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `<div class="modal" role="dialog" aria-modal="true">${innerHtml}</div>`;
    document.body.appendChild(backdrop);
    modalStack++;

    const close = () => {
      backdrop.remove();
      modalStack--;
    };
    backdrop.addEventListener("mousedown", (e) => {
      if (e.target === backdrop) close();
    });
    document.addEventListener(
      "keydown",
      function esc(e) {
        if (e.key === "Escape") {
          close();
          document.removeEventListener("keydown", esc);
        }
      },
      { once: true }
    );
    const modalEl = backdrop.querySelector(".modal");
    if (onMount) onMount(modalEl, close);
    return close;
  }

  function tally(quantity, max = 12) {
    const shown = Math.min(quantity, max);
    let dots = "";
    for (let i = 0; i < shown; i++) dots += `<span class="cap"></span>`;
    let extra = "";
    if (quantity > max) extra = `<span class="count-label">+${quantity - max} more</span>`;
    else if (quantity === 0) dots = `<span class="cap dim"></span>`;
    return `<div class="tally">${dots}${extra}<span class="count-label">${quantity} on hand</span></div>`;
  }

  function starsReadonly(rating) {
    if (rating === null || rating === undefined) return "";
    let out = "";
    for (let i = 1; i <= 5; i++) {
      const full = rating >= i;
      const half = !full && rating >= i - 0.5;
      out += `<span style="color:${full || half ? "var(--accent)" : "var(--text-faint)"}">${
        full ? "\u2605" : half ? "\u2bea" : "\u2606"
      }</span>`;
    }
    return `<span class="stars" aria-label="${rating} out of 5">${out}</span>`;
  }

  function starPicker(name, initial = 0) {
    let html = `<div class="stars" data-star-picker="${name}">`;
    for (let i = 1; i <= 5; i++) {
      html += `<button type="button" data-val="${i}" class="${i <= initial ? "on" : ""}">\u2605</button>`;
    }
    html += `</div><input type="hidden" name="${name}" value="${initial}" />`;
    return html;
  }

  function wireStarPicker(container) {
    container.querySelectorAll("[data-star-picker]").forEach((wrap) => {
      const name = wrap.dataset.starPicker;
      const hidden = container.querySelector(`input[type=hidden][name="${name}"]`);
      wrap.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", () => {
          const val = Number(btn.dataset.val);
          hidden.value = String(val);
          wrap.querySelectorAll("button").forEach((b) => {
            b.classList.toggle("on", Number(b.dataset.val) <= val);
          });
        });
      });
    });
  }

  function debounce(fn, ms = 250) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  return {
    escapeHtml,
    toast,
    fmtDate,
    fmtDateTime,
    volumeUnitLabel,
    ozToDisplay,
    displayToOz,
    openModal,
    tally,
    starsReadonly,
    starPicker,
    wireStarPicker,
    debounce,
  };
})();

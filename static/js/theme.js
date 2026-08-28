const Theme = (() => {
  const KEY = "cellar_theme";

  function getPreference() {
    try {
      return localStorage.getItem(KEY) || "system";
    } catch (e) {
      return "system";
    }
  }

  function resolve(pref) {
    if (pref === "system") {
      return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    return pref;
  }

  function apply(pref) {
    document.documentElement.setAttribute("data-theme", resolve(pref));
  }

  function set(pref) {
    try {
      localStorage.setItem(KEY, pref);
    } catch (e) {
      /* localStorage unavailable (private browsing etc); theme just won't persist */
    }
    apply(pref);
  }

  function init() {
    const pref = getPreference();
    apply(pref); // the inline head script already did this pre-paint; this just syncs state

    const select = document.getElementById("theme-select");
    if (select) {
      select.value = pref;
      select.addEventListener("change", () => set(select.value));
    }

    if (window.matchMedia) {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        if (getPreference() === "system") apply("system");
      });
    }
  }

  return { init, set, getPreference };
})();

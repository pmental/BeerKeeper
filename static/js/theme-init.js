// Resolve and apply the theme before first paint, so there's no flash of
// the wrong theme. Kept tiny on purpose. Runs as an external, non-deferred
// <script> in <head> (same render-blocking timing an inline script would
// have had) specifically so it works under a strict script-src 'self' CSP.
(function () {
  try {
    var stored = localStorage.getItem("cellar_theme") || "system";
    var resolved =
      stored === "system"
        ? window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : stored;
    document.documentElement.setAttribute("data-theme", resolved);
  } catch (e) {
    document.documentElement.setAttribute("data-theme", "dark");
  }
})();

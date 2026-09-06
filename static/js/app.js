const App = (() => {
  const state = {
    user: null,
    displayName: null,
    account: null,
    singleUserMode: false,
    authConfig: { password_auth_enabled: true, oidc_enabled: false, oidc_button_label: "Continue with SSO" },
  };

  async function refreshAuthConfig() {
    // /api/app-config is always mounted, regardless of mode - has to be
    // checked first, since /api/auth/config (the multi-user endpoint)
    // isn't mounted at all in single-user desktop mode.
    try {
      const { single_user_mode } = await Api.appConfig();
      state.singleUserMode = !!single_user_mode;
    } catch (e) {
      state.singleUserMode = false;
    }
    if (state.singleUserMode) return;
    try {
      state.authConfig = await Api.authConfig();
    } catch (e) {
      // Fall back to the permissive default (password auth on, OIDC off) so a
      // transient network hiccup doesn't lock the login form away entirely.
    }
  }

  async function refreshVersionTag() {
    const tag = document.getElementById("app-version-tag");
    if (!tag) return;
    if (!state.user) {
      tag.textContent = "BeerKeeper";
      return;
    }
    try {
      const { name, version } = await Api.version();
      tag.textContent = `${name} v${version}`;
    } catch (e) {
      tag.textContent = "BeerKeeper";
    }
  }

  async function refreshUser() {
    // Single-user desktop mode has no login - every request is
    // automatically the one local user (see app/deps.py) - so there's no
    // token to gate on here, unlike the normal self-hosted app.
    if (!state.singleUserMode && !Api.getToken()) {
      state.user = null;
      state.displayName = null;
      state.account = null;
      await refreshVersionTag();
      return;
    }
    try {
      const account = await Api.me();
      state.user = account.username;
      state.displayName = UI.firstName(account.display_name) || account.username;
      state.account = account;
    } catch (e) {
      state.user = null;
      state.displayName = null;
      state.account = null;
      Api.setToken(null);
    }
    await refreshVersionTag();
  }

  function renderNav(activeHash) {
    const navLinks = document.getElementById("nav-links");
    const navRight = document.getElementById("nav-right");
    const navToggle = document.getElementById("nav-toggle");

    // A route change is also the natural point to close the mobile menu -
    // whatever the user tapped just navigated them away from it.
    navLinks.classList.remove("open");
    if (navToggle) navToggle.setAttribute("aria-expanded", "false");

    // Single-user desktop mode has nobody to browse (no other cellars
    // exist), nobody to log in as (there's only ever one user, already
    // "logged in"), and nothing to log out of.
    const links = state.singleUserMode
      ? [{ href: "#/cellar", label: "My cellar" }, { href: "#/consumed", label: "History" }]
      : [{ href: "#/", label: "Home" }, { href: "#/browse", label: "Browse" }];
    if (!state.singleUserMode && state.user) {
      links.push({ href: "#/cellar", label: "My cellar" });
      links.push({ href: "#/consumed", label: "History" });
    }
    if (state.account && state.account.is_admin) {
      links.push({ href: "#/admin", label: state.singleUserMode ? "Settings" : "Admin" });
    }
    navLinks.innerHTML = links
      .map(
        (l) =>
          `<a href="${l.href}" class="${activeHash === l.href ? "active" : ""}">${l.label}</a>`
      )
      .join("");

    if (state.singleUserMode) {
      // No login/logout concept - just a quiet link to Settings/Account.
      navRight.innerHTML = `<a class="user-chip" href="#/account" title="Account"><span class="user-chip-name">${UI.escapeHtml(
        state.displayName || state.user || "Cellar"
      )}</span></a>`;
      return;
    }

    if (state.user) {
      const initial = (state.displayName || state.user || "?").trim().charAt(0).toUpperCase();
      const avatarHtml = state.account && state.account.avatar_url
        ? `<img class="user-avatar" src="${UI.escapeHtml(state.account.avatar_url)}" alt="" width="24" height="24" />`
        : `<span class="user-avatar user-avatar-fallback">${UI.escapeHtml(initial)}</span>`;
      navRight.innerHTML = `
        <a class="user-chip" href="#/account" title="Account">
          ${avatarHtml}
          <span class="user-chip-name">Hi, <strong>${UI.escapeHtml(state.displayName || state.user)}</strong></span>
        </a>
        <button class="btn btn-ghost btn-sm" id="logout-btn">Log out</button>
      `;
      const logoutBtn = document.getElementById("logout-btn");
      if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
          Api.setToken(null);
          state.user = null;
          state.account = null;
          refreshVersionTag();
          UI.toast("Logged out.");
          location.hash = "#/";
          router();
        });
      }
    } else {
      navRight.innerHTML = `
        <a class="btn btn-ghost btn-sm" href="#/login">Log in</a>
        ${
          state.authConfig.password_auth_enabled && state.authConfig.registration_enabled
            ? `<a class="btn btn-primary btn-sm" href="#/register">Sign up</a>`
            : ""
        }
      `;
    }
  }

  const routes = [
    { pattern: /^#\/?$/, page: (main, ctx, query) => (ctx.singleUserMode ? (location.hash = "#/cellar") : Pages.home(main, ctx, query)) },
    { pattern: /^#\/login$/, page: (main, ctx) => (ctx.singleUserMode ? (location.hash = "#/cellar") : Pages.login(main, ctx)) },
    { pattern: /^#\/register$/, page: (main, ctx) => (ctx.singleUserMode ? (location.hash = "#/cellar") : Pages.register(main, ctx)) },
    { pattern: /^#\/forgot-password$/, page: (main, ctx) => (ctx.singleUserMode ? (location.hash = "#/cellar") : Pages.forgotPassword(main, ctx)) },
    { pattern: /^#\/reset-password$/, page: (main, ctx, query) => (ctx.singleUserMode ? (location.hash = "#/cellar") : Pages.resetPassword(main, ctx, query)) },
    { pattern: /^#\/cellar$/, page: Pages.cellar },
    { pattern: /^#\/account$/, page: Pages.account },
    { pattern: /^#\/admin$/, page: Pages.admin },
    { pattern: /^#\/browse$/, page: (main, ctx) => (ctx.singleUserMode ? (location.hash = "#/cellar") : Pages.browse(main, ctx)) },
    { pattern: /^#\/consumed$/, page: Pages.consumed },
    // Import/export moved into the account page - keep the old link
    // working for anyone with it bookmarked, rather than a dead route.
    { pattern: /^#\/import-export$/, page: () => { location.hash = "#/account"; } },
    { pattern: /^#\/u\/([^/]+)\/trades$/, page: (main, username, ctx) => (ctx.singleUserMode ? (location.hash = "#/cellar") : Pages.publicTrades(main, username, ctx)), param: true },
    { pattern: /^#\/u\/([^/]+)$/, page: (main, username, ctx) => (ctx.singleUserMode ? (location.hash = "#/cellar") : Pages.publicCellar(main, username, ctx)), param: true },
  ];

  const ctx = {
    get user() {
      return state.user;
    },
    get displayName() {
      return state.displayName;
    },
    get account() {
      return state.account;
    },
    get authConfig() {
      return state.authConfig;
    },
    get singleUserMode() {
      return state.singleUserMode;
    },
    refreshUser,
  };

  async function router() {
    const rawHash = location.hash || "#/";
    const [hash, queryString] = rawHash.split("?");
    const query = new URLSearchParams(queryString || "");
    const main = document.getElementById("main");

    // The OIDC callback lands here as #/oidc-callback?token=... - pull the
    // token out of the hash (it never reaches the server, by design), store
    // it, then hand off to the normal cellar view with a clean URL.
    if (hash.startsWith("#/oidc-callback")) {
      const token = query.get("token");
      const error = query.get("oidc_error");
      if (token) {
        Api.setToken(token);
        await refreshUser();
        UI.toast(`Welcome, ${state.displayName || state.user}.`);
        location.replace("#/cellar");
      } else {
        location.replace("#/login" + (error ? "?oidc_error=" + encodeURIComponent(error) : ""));
      }
      return;
    }

    renderNav(hash);

    for (const route of routes) {
      const match = hash.match(route.pattern);
      if (match) {
        try {
          if (route.param) {
            await route.page(main, decodeURIComponent(match[1]), ctx);
          } else {
            await route.page(main, ctx, query);
          }
        } catch (e) {
          main.innerHTML = `<div class="panel empty-note">Something went wrong: ${UI.escapeHtml(e.message)}</div>`;
        }
        window.scrollTo(0, 0);
        return;
      }
    }
    main.innerHTML = `<div class="page-head"><h1>Not found</h1></div><p><a href="#/">Go home</a></p>`;
  }

  async function init() {
    Theme.init();
    await Promise.all([refreshUser(), refreshAuthConfig()]);
    router();
    window.addEventListener("hashchange", router);

    const navToggle = document.getElementById("nav-toggle");
    const navLinks = document.getElementById("nav-links");
    if (navToggle && navLinks) {
      navToggle.addEventListener("click", () => {
        const open = navLinks.classList.toggle("open");
        navToggle.setAttribute("aria-expanded", open ? "true" : "false");
      });
      document.addEventListener("click", (e) => {
        if (!navLinks.classList.contains("open")) return;
        if (navLinks.contains(e.target) || navToggle.contains(e.target)) return;
        navLinks.classList.remove("open");
        navToggle.setAttribute("aria-expanded", "false");
      });
    }
  }

  return { init, router, state };
})();

document.addEventListener("DOMContentLoaded", App.init);

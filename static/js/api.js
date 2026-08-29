const Api = (() => {
  const TOKEN_KEY = "cellar_token";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }
  function setToken(t) {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  }

  async function request(method, path, { body, form, auth = true } = {}) {
    const headers = {};
    let payload = body;
    if (form) {
      headers["Content-Type"] = "application/x-www-form-urlencoded";
      payload = new URLSearchParams(body).toString();
    } else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    if (auth) {
      const token = getToken();
      if (token) headers["Authorization"] = "Bearer " + token;
    }
    const res = await fetch(path, { method, headers, body: payload });
    const isJson = (res.headers.get("content-type") || "").includes("application/json");
    const data = isJson ? await res.json().catch(() => null) : await res.text();

    if (!res.ok) {
      if (res.status === 401 && auth) {
        setToken(null);
      }
      const detail = isJson && data && data.detail;
      let message = "Something went wrong.";
      if (typeof detail === "string") message = detail;
      else if (Array.isArray(detail) && detail.length) {
        message = detail.map((d) => d.msg || JSON.stringify(d)).join(" ");
      }
      const err = new Error(message);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  return {
    getToken,
    setToken,
    get: (path, opts) => request("GET", path, opts),
    post: (path, body, opts) => request("POST", path, { ...opts, body }),
    patch: (path, body, opts) => request("PATCH", path, { ...opts, body }),
    del: (path, opts) => request("DELETE", path, opts),

    register: (username, email, password) =>
      request("POST", "/api/auth/register", { body: { username, email, password }, auth: false }),
    login: (username, password) =>
      request("POST", "/api/auth/login", { body: { username, password }, form: true, auth: false }),
    me: () => request("GET", "/api/auth/me"),
    authConfig: () => request("GET", "/api/auth/config", { auth: false }),
    version: () => request("GET", "/api/version", { auth: false }),
    changePassword: (current_password, new_password) =>
      request("POST", "/api/auth/change-password", { body: { current_password, new_password } }),
    forgotPassword: (email) => request("POST", "/api/auth/forgot-password", { body: { email }, auth: false }),
    resetPassword: (token, new_password) =>
      request("POST", "/api/auth/reset-password", { body: { token, new_password }, auth: false }),

    searchBeers: (q, breweryId) => {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (breweryId) params.set("brewery_id", breweryId);
      return request("GET", "/api/beers?" + params.toString());
    },
    searchBreweries: (q) => {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      return request("GET", "/api/breweries?" + params.toString());
    },
    beerStyles: () => request("GET", "/api/beer-styles", { auth: false }),

    listCellar: (sort, location) => {
      const params = new URLSearchParams();
      if (sort) params.set("sort", sort);
      if (location) params.set("location", location);
      const qs = params.toString();
      return request("GET", "/api/cellar" + (qs ? "?" + qs : ""));
    },
    addEntry: (payload) => request("POST", "/api/cellar", { body: payload }),
    patchEntry: (id, payload) => request("PATCH", `/api/cellar/${id}`, { body: payload }),
    deleteEntry: (id) => request("DELETE", `/api/cellar/${id}`),
    moveEntry: (id, location) => request("POST", `/api/cellar/${id}/move`, { body: { location } }),
    drinkEntry: (id, payload) => request("POST", `/api/cellar/${id}/drink`, { body: payload }),

    listConsumption: (beerId) => {
      const params = new URLSearchParams();
      if (beerId) params.set("beer_id", beerId);
      const qs = params.toString();
      return request("GET", "/api/consumption" + (qs ? "?" + qs : ""));
    },
    deleteConsumption: (id) => request("DELETE", `/api/consumption/${id}`),

    getAccount: () => request("GET", "/api/account"),
    patchAccount: (payload) => request("PATCH", "/api/account", { body: payload }),

    adminListUsers: () => request("GET", "/api/admin/users"),
    adminCreateUser: (payload) => request("POST", "/api/admin/users", { body: payload }),
    adminPatchUser: (id, payload) => request("PATCH", `/api/admin/users/${id}`, { body: payload }),
    adminResetPassword: (id, newPassword) =>
      request("POST", `/api/admin/users/${id}/reset-password`, { body: { new_password: newPassword } }),
    adminDeleteUser: (id) => request("DELETE", `/api/admin/users/${id}`),
    adminGetSettings: () => request("GET", "/api/admin/settings"),
    adminPatchSettings: (payload) => request("PATCH", "/api/admin/settings", { body: payload }),

    browseCellars: () => request("GET", "/api/public/cellars", { auth: false }),
    recentActivity: () => request("GET", "/api/public/recent"),
    publicCellar: (username) => request("GET", "/api/public/u/" + encodeURIComponent(username), { auth: false }),
    publicTrades: (username) =>
      request("GET", "/api/public/u/" + encodeURIComponent(username) + "/trades", { auth: false }),

    listWanted: () => request("GET", "/api/wanted"),
    addWanted: (payload) => request("POST", "/api/wanted", { body: payload }),
    deleteWanted: (id) => request("DELETE", `/api/wanted/${id}`),

    async exportCellar() {
      const token = getToken();
      const res = await fetch("/api/cellar/export", {
        headers: token ? { Authorization: "Bearer " + token } : {},
      });
      if (!res.ok) throw new Error("Couldn't export your cellar.");
      const blob = await res.blob();
      const disposition = res.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      return { blob, filename: match ? match[1] : "cellar-export.csv" };
    },

    async importCellar(file) {
      const token = getToken();
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/cellar/import", {
        method: "POST",
        headers: token ? { Authorization: "Bearer " + token } : {},
        body: fd,
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const err = new Error((data && data.detail) || "Import failed.");
        err.data = data;
        throw err;
      }
      return data;
    },
  };
})();

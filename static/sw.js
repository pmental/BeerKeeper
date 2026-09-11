/* BeerKeeper push service worker.
 *
 * Deliberately minimal: it handles push delivery and notification
 * clicks, and nothing else. There is no `fetch` handler here on purpose
 * - a worker that caches responses can serve stale JS or CSS from the
 * device after a deploy, which is invisible to any server-side fix and
 * sometimes needs the user to uninstall the app to clear. Since this
 * worker never intercepts requests, the app always loads from the
 * network exactly as it did before, and the worker exists purely so the
 * browser has somewhere to deliver a push message.
 *
 * It's also only ever registered from the opt-in toggle on the account
 * page - nothing registers it on page load.
 */

self.addEventListener("install", (event) => {
  // Take over immediately rather than waiting for existing tabs to
  // close; there's no cached state to migrate, so nothing to be careful
  // about here.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = {};
  }
  const title = data.title || "BeerKeeper";
  const options = {
    body: data.body || "",
    icon: "/assets/icons/icon-192.png",
    badge: "/assets/icons/icon-192.png",
    // Collapses repeat reminders into one notification rather than
    // stacking them up on the lock screen.
    tag: "beerkeeper-drinkby",
    data: { url: data.url || "/#/cellar" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  // Only ever navigate to a relative path on this origin. The payload is
  // written by this app's own server today, so this changes nothing now -
  // it's here so that a future bug which let an attacker influence the
  // notification body couldn't turn a tapped reminder into a redirect to
  // a site of their choosing. "//evil.example" is rejected too: it starts
  // with a slash but is a protocol-relative absolute URL.
  const raw = (event.notification.data && event.notification.data.url) || "/#/cellar";
  const target = raw.startsWith("/") && !raw.startsWith("//") ? raw : "/#/cellar";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      // Focus an already-open tab if there is one, rather than piling up
      // duplicates every time a reminder is tapped.
      for (const client of clients) {
        if ("focus" in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(target);
    })
  );
});

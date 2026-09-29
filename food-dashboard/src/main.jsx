import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

/* global __STAFF__ */
// The City staff site runs on shared City computers, so nothing of it is kept offline: at every start,
// unregister any service worker (an earlier build's, or the self-destroying one this build ships) and
// delete every Cache Storage cache. A browser that refuses either is left as it is; the server's
// no-store headers still apply.
if (typeof __STAFF__ !== "undefined" && __STAFF__ === true) {
  (async () => {
    try {
      const registrations = (await navigator.serviceWorker?.getRegistrations?.()) ?? [];
      await Promise.all(registrations.map((r) => r.unregister()));
    } catch {
      // no service worker support, or not allowed here
    }
    try {
      if (typeof caches !== "undefined") {
        for (const name of await caches.keys()) await caches.delete(name);
      }
    } catch {
      // no Cache Storage, or not allowed here
    }
  })();
}

// Page-view counting is opt-in per deployment: set VITE_ANALYTICS_SRC to the
// script URL of a cookie-free counter at build time. Unset, nothing loads and
// the privacy page says so.
const analytics = import.meta.env.VITE_ANALYTICS_SRC;
if (analytics) {
  const s = document.createElement("script");
  s.src = analytics;
  s.async = true;
  s.defer = true;
  const site = import.meta.env.VITE_ANALYTICS_SITE;
  if (site) s.dataset.goatcounter = site;
  document.head.appendChild(s);
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);

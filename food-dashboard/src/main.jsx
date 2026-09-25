import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

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

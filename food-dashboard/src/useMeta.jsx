import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { isExpired } from "./lib/expiry";
import { siteMode } from "./lib/framing";

/**
 * /data/meta.json describes the export: its mode (`record` or `bands`),
 * whether it is the invented sample, when inspections run through and when it
 * expires, and in `bands` mode the published rule, its bands and backtest.
 * The site renders nothing until it has loaded, so a page never shows one
 * mode and then another, and never shows a list it cannot date.
 */
const MetaContext = createContext(null);

export function useMetaFetch() {
  const [state, setState] = useState({ meta: null, status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, status: "loading" }));
    fetch("/data/meta.json", { headers: { Accept: "application/json" } })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((m) => { if (!cancelled) setState({ meta: m, status: "ok" }); })
      .catch((err) => {
        console.error("meta.json did not load:", err);
        if (!cancelled) setState({ meta: null, status: "error" });
      });
    return () => { cancelled = true; };
  }, [attempt]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, retry };
}

export function MetaProvider({ meta, children }) {
  return <MetaContext.Provider value={meta}>{children}</MetaContext.Provider>;
}

export function useMeta() {
  return useContext(MetaContext);
}

/** "record" or "bands". */
export function useMode() {
  return siteMode(useMeta());
}

export function useSample() {
  return Boolean(useMeta()?.sample);
}

/** True once meta.expires has passed: the site closes down to a notice and a search. */
export function useExpired() {
  return isExpired(useMeta());
}

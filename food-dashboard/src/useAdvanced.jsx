import { createContext, useContext, useState, useCallback, useMemo } from "react";
import { copyFor } from "./lib/copy";

const KEY = "food.advancedMode";
const SEEN_KEY = "food.seenWelcome";

const AdvancedContext = createContext(null);

// localStorage throws in private mode and some webviews; these preferences
// are a convenience, never load-bearing state.
function safeGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

export function AdvancedProvider({ children }) {
  const [advanced, setAdvanced] = useState(() => safeGet(KEY) === "1");
  const [seenWelcome, setSeenWelcome] = useState(() => safeGet(SEEN_KEY) === "1");

  const toggle = useCallback(() => {
    setAdvanced((prev) => {
      safeSet(KEY, prev ? "0" : "1");
      return !prev;
    });
  }, []);

  const dismissWelcome = useCallback(() => {
    safeSet(SEEN_KEY, "1");
    setSeenWelcome(true);
  }, []);

  const value = useMemo(
    () => ({ advanced, toggle, copy: copyFor(advanced), seenWelcome, dismissWelcome }),
    [advanced, toggle, seenWelcome, dismissWelcome]
  );

  return <AdvancedContext.Provider value={value}>{children}</AdvancedContext.Provider>;
}

export function useAdvanced() {
  const ctx = useContext(AdvancedContext);
  if (!ctx) throw new Error("useAdvanced must be used inside <AdvancedProvider>");
  return ctx;
}

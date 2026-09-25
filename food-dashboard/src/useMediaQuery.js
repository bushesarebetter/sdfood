import { useState, useEffect } from "react";

/**
 * Subscribe to a CSS media query.
 *
 * The phone layout is a structurally different shell, not the desktop layout
 * with things hidden -- so the decision has to be made in JS, once, at the top.
 * Reads synchronously on first render so there is no flash of the wrong shell.
 */
export default function useMediaQuery(query) {
  const read = () => typeof window !== "undefined" && window.matchMedia(query).matches;
  const [matches, setMatches] = useState(read);

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = (e) => setMatches(e.matches);
    mql.addEventListener("change", onChange);
    setMatches(mql.matches);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

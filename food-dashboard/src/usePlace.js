import { useCallback, useEffect, useState } from "react";
import { fetchPlace } from "./lib/placeData";

/**
 * One place's full record, loaded when the place is opened:
 * { status: "loading" | "ok" | "missing" | "error", detail, retry }.
 */
export default function usePlace(id) {
  const [state, setState] = useState({ status: id ? "loading" : "missing", detail: null, id });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!id) {
      setState({ status: "missing", detail: null, id });
      return undefined;
    }
    let cancelled = false;
    setState({ status: "loading", detail: null, id });
    fetchPlace(id).then((r) => {
      if (cancelled) return;
      if (r.status === "error") console.error(`place file for ${id} did not load:`, r.reason);
      setState({ status: r.status, detail: r.detail ?? null, id });
    });
    return () => { cancelled = true; };
  }, [id, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  // A state left over from another id reads as loading, never as that place's record.
  return state.id === id ? { ...state, retry } : { status: "loading", detail: null, retry };
}

import { useState, useEffect, useMemo, useCallback } from "react";

/**
 * The index (`data/facilities.geojson`), fetched once: what the map, the
 * list, the filters and the search need, and nothing more. Each place's full
 * record is its own file, loaded when the place is opened (usePlace).
 */
export default function useFacilities() {
  const [facilities, setFacilities] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const res = await fetch("/data/facilities.geojson");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const fc = await res.json();
        if (!Array.isArray(fc?.features)) throw new Error("the index has no features");
        if (!cancelled) setFacilities(fc);
      } catch (err) {
        console.error("facilities.geojson did not load:", err);
        if (!cancelled) setError("The list of places did not load. Check the connection and try again.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  // Counts by council district, for the district filter.
  const districts = useMemo(() => {
    if (!facilities) return null;
    const counts = {};
    for (const f of facilities.features) {
      const d = f.properties.council_district;
      if (d) counts[d] = (counts[d] || 0) + 1;
    }
    return counts;
  }, [facilities]);

  return { facilities, districts, loading, error, retry };
}

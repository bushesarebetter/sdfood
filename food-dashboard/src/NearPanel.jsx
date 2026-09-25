import { useState } from "react";
import { loadMaps, MAP_UNAVAILABLE } from "./useGoogleMap";
import AddressInput from "./AddressInput";
import { resolvePlace } from "./places";
import { metersBetween } from "./lib/geo";
import { passesFilters } from "./lib/filters";
import { gradeView } from "./lib/grades";
import { markFor } from "./lib/marks";
import { track } from "./lib/track";
import { useExpired, useMode } from "./useMeta";
import { SITE } from "./site";

const NEAR_M = 500;

/** What a visitor reads when an address lookup does not work; the reason goes to the console. */
export function explain(err) {
  const msg = typeof err === "string" ? err : err?.message || err?.code || String(err);
  if (/ZERO_RESULTS|NOT_FOUND/i.test(msg)) return `No match for that. Try a street address or a landmark in ${SITE.name}.`;
  if (/OVER_QUERY_LIMIT|RESOURCE_EXHAUSTED/i.test(msg)) return "Too many lookups right now. Try again in a minute.";
  if (msg !== MAP_UNAVAILABLE) console.error("Address lookup:", err);
  return "Address lookup is not available right now. Search for a place by name instead.";
}

/**
 * "Near an address": the listed places within 500 m of an address, nearest
 * first. Only the places currently shown are considered, so the answer
 * matches what is on the map. Addresses are suggested as you type; a chosen
 * suggestion is located directly and typed text goes to the geocoder.
 */
export default function NearPanel({ facilities, filters, onPoint, onSelect, compact = false }) {
  const [text, setText] = useState("");
  const [pick, setPick] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const mode = useMode();
  const expired = useExpired();

  async function run(e) {
    e.preventDefault();
    if (!text.trim() || !facilities) return;
    setBusy(true);
    setError(null);
    track("near-check");
    try {
      let point, label;
      if (pick) {
        ({ point, label } = await resolvePlace(pick));
      } else {
        const maps = await loadMaps();
        const { results } = await new maps.Geocoder().geocode({ address: text, bounds: SITE.bounds, region: "us" });
        if (!results?.length) throw new Error("ZERO_RESULTS");
        const loc = results[0].geometry.location;
        point = [loc.lng(), loc.lat()];
        label = results[0].formatted_address;
      }
      const shown = facilities.features.filter((f) => passesFilters(f.properties, filters, { mode }));
      const places = shown
        .map((feature) => ({ feature, meters: metersBetween(point, feature.geometry.coordinates) }))
        .filter((r) => r.meters <= NEAR_M)
        .sort((a, b) => a.meters - b.meters);
      setResult({ label, places });
      onPoint?.({ point });
    } catch (err) {
      setError(explain(err));
      setResult(null);
      onPoint?.(null);
    } finally {
      setBusy(false);
    }
  }

  function clear() {
    setText("");
    setPick(null);
    setResult(null);
    setError(null);
    onPoint?.(null);
  }

  const field = "w-full border border-rule-strong bg-paper-sunk px-3 py-2 text-[16px] text-ink placeholder:text-ink-3 focus:border-ink focus:bg-paper focus:outline-none md:text-[13px]";

  return (
    <div className={compact ? "" : "px-6 py-5"}>
      {!compact && (
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <p className="label">Near an address</p>
          <p className="text-[12px] text-ink-2">listed places within {NEAR_M} m</p>
        </div>
      )}

      <form onSubmit={run} className="space-y-2">
        <AddressInput
          id={compact ? "near-address-m" : "near-address"}
          value={text}
          onChange={setText}
          onPick={setPick}
          placeholder="An address, or a place"
          aria-label="Address"
          autoComplete="off"
          className={field}
        />
        <div className="flex items-center gap-4">
          <button
            type="submit"
            disabled={busy || !text.trim()}
            className="bg-ink px-4 py-2 text-[13px] font-semibold text-paper hover:bg-ink-2 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "Looking up" : "Check near here"}
          </button>
          {(result || error) && (
            <button type="button" onClick={clear} className="border-b border-ink/25 text-[12px] text-ink-3 hover:border-ink hover:text-ink">
              Clear
            </button>
          )}
        </div>
      </form>

      {error && <p role="alert" className="mt-3 text-[13px] leading-[1.5] text-band-1">{error}</p>}

      {result && (
        <div className="mt-4">
          <p className="text-[13px] leading-[1.5] text-ink-2" role="status">
            {result.places.length
              ? <>{result.places.length} listed {result.places.length === 1 ? "place" : "places"} within {NEAR_M} m of {result.label}.</>
              : <>No listed places within {NEAR_M} m of {result.label}.</>}
          </p>
          {result.places.length > 0 && (
            <ol className="mt-2">
              {result.places.map(({ feature, meters }) => {
                const p = feature.properties;
                const mark = markFor(p, { mode });
                const g = gradeView(p.grade);
                const where = [!expired ? mark.label : null, g.graded ? `grade ${g.short}` : g.text.toLowerCase()].filter(Boolean).join(", ");
                return (
                  <li key={p.facility_id} className="border-b border-rule last:border-b-0">
                    <button onClick={() => onSelect(feature)} className="flex w-full items-baseline gap-3 py-2 text-left hover:bg-paper-sunk">
                      <span className="tnum w-12 shrink-0 text-[12px] text-ink-2">{Math.round(meters / 10) * 10} m</span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-[13px] leading-snug text-ink">{p.name}</span>
                        {where && <span className="block text-[12px] text-ink-2">{where}</span>}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

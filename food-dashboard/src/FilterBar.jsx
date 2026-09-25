import { useMemo } from "react";
import { useAdvanced } from "./useAdvanced";
import { useMeta, useMode } from "./useMeta";
import { flagChips, typesFor, bandCounts } from "./lib/filters";
import { bandPoints } from "./lib/bands";
import { BAND_FILTERS, ALL_PLACES } from "./constants";
import AreaToggle from "./AreaToggle";

const chip = (on) =>
  `min-h-[32px] border px-2.5 py-1 text-[13px] leading-none ${
    on ? "border-ink bg-ink text-paper" : "border-rule-strong bg-transparent text-ink-2 hover:border-ink hover:text-ink"
  }`;

const places = (n) => `${Number(n || 0).toLocaleString("en-US")} ${n === 1 ? "place" : "places"}`;

/**
 * The filters, each a row of buttons: in `bands` mode which bands to show;
 * then the kind of place, and a fact from the last year of the record (our
 * reading, from the index's flags). Each button's accessible name says its
 * count apart from its label ("Band 1, 16 places").
 */
export default function FilterBar({ filters, onFiltersChange, facilities, hasCounty = false }) {
  const { copy } = useAdvanced();
  const meta = useMeta();
  const mode = useMode();
  const chips = useMemo(() => flagChips(facilities, filters, { mode }), [facilities, filters, mode]);
  const types = useMemo(() => typesFor(facilities, filters, { mode }), [facilities, filters, mode]);
  const counts = useMemo(() => bandCounts(facilities, { mode }), [facilities, mode]);

  const set = (patch) => onFiltersChange({ ...filters, ...patch });
  const toggleType = (key) => {
    const has = filters.types.includes(key);
    set({ types: has ? filters.types.filter((t) => t !== key) : [...filters.types, key] });
  };

  const bandChoices = BAND_FILTERS.filter((b) => counts[b.band] != null);
  const band = filters.band ?? ALL_PLACES;

  return (
    <div className="px-6 py-5">
      {hasCounty && (
        <div className="mb-6">
          <p className="label mb-3">Area</p>
          <AreaToggle county={Boolean(filters.county)} onChange={(county) => set({ county })} />
        </div>
      )}
      {mode === "bands" && bandChoices.length > 1 && (
        <>
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <p className="label" id="band-filter-label">{copy.bandTitle}</p>
            <p className="text-[12px] text-ink-2">{copy.bandUnit}</p>
          </div>
          <div role="group" aria-labelledby="band-filter-label" className="flex flex-wrap gap-1.5">
            {bandChoices.map((b) => (
              <button key={b.band} onClick={() => set({ band: b.band })} aria-pressed={band === b.band} aria-label={`${b.label}, ${places(counts[b.band])}`} className={chip(band === b.band)}>
                {b.label}
                <span className="tnum ml-1.5 opacity-70" aria-hidden="true">{counts[b.band].toLocaleString()}</span>
              </button>
            ))}
          </div>
          <p className="mt-2.5 text-[13px] leading-[1.45] text-ink-2">
            {["1", "2", "3"].filter((b) => band === ALL_PLACES || Number(b) <= Number(band)).map((b) => `Band ${b}: ${bandPoints(meta, b) ?? ""}`).join(". ")}.
            {band === ALL_PLACES && " Other places are drawn in grey."}
          </p>
        </>
      )}

      {types.length > 1 && (
        <>
          <div className={`mb-3 flex items-baseline justify-between gap-3 ${mode === "bands" ? "mt-6" : ""}`}>
            <p className="label" id="type-filter-label">{copy.typeTitle}</p>
            <p className="text-[12px] text-ink-2">any you pick</p>
          </div>
          <div role="group" aria-labelledby="type-filter-label" className="flex flex-wrap gap-1.5">
            {types.map((t) => (
              <button key={t.key} onClick={() => toggleType(t.key)} aria-pressed={filters.types.includes(t.key)} aria-label={`${t.label}, ${places(t.count)}`} className={chip(filters.types.includes(t.key))}>
                {t.label}
                <span className="tnum ml-1.5 opacity-70" aria-hidden="true">{t.count.toLocaleString()}</span>
              </button>
            ))}
          </div>
        </>
      )}

      {chips.length > 0 && (
        <>
          <div className="mb-3 mt-6 flex items-baseline justify-between gap-3">
            <p className="label" id="flag-filter-label">{copy.flagTitle}</p>
            <p className="text-[12px] text-ink-2">{copy.flagUnit}</p>
          </div>
          <div role="group" aria-labelledby="flag-filter-label" className="flex flex-wrap gap-1.5">
            <button onClick={() => set({ flag: null })} aria-pressed={filters.flag === null} className={chip(filters.flag === null)}>
              Any
            </button>
            {chips.map((c) => (
              <button key={c.key} onClick={() => set({ flag: filters.flag === c.key ? null : c.key })} aria-pressed={filters.flag === c.key} aria-label={`${c.label}, ${places(c.count)}`} className={chip(filters.flag === c.key)}>
                {c.label}
                <span className="tnum ml-1.5 opacity-70" aria-hidden="true">{c.count.toLocaleString()}</span>
              </button>
            ))}
          </div>
          <p className="mt-2.5 text-[13px] leading-[1.45] text-ink-2">Our reading of the 12 months before each place&rsquo;s last visit.</p>
        </>
      )}
    </div>
  );
}

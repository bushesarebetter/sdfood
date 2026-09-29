import { useMemo } from "react";
import { useAdvanced } from "./useAdvanced";
import { useMeta, useMode } from "./useMeta";
import { flagChips, typesFor, bandCounts } from "./lib/filters";
import { bandPoints } from "./lib/bands";
import { ESCALATION_FLAGS, ESCALATION_NOTE } from "./lib/inspections";
import { fmtDate } from "./lib/dates";
import { BAND_FILTERS, ALL_PLACES } from "./constants";
import AreaToggle, { outsideNote } from "./AreaToggle";

const chip = (on) =>
  `min-h-[32px] border px-2.5 py-1 text-[13px] leading-none ${
    on ? "border-ink bg-ink text-paper" : "border-rule-strong bg-transparent text-ink-2 hover:border-ink hover:text-ink"
  }`;

const places = (n) => `${Number(n || 0).toLocaleString("en-US")} ${n === 1 ? "place" : "places"}`;

/**
 * The filters, each a row of buttons: in `bands` mode which bands to show;
 * then the kind of place, and a fact from the year before the list date (our
 * reading, from the index's flags; the escalation facts read two years and are
 * our counts of the patterns the County's Operator's Guide names). Each button's accessible name says its
 * count apart from its label ("Band 1, 16 places"). `compact` is the staff site's filter rail: tighter,
 * with the notes on the facts one click away.
 */
export default function FilterBar({ filters, onFiltersChange, facilities, hasCounty = false, compact = false }) {
  const { copy } = useAdvanced();
  const meta = useMeta();
  const mode = useMode();
  const chips = useMemo(() => flagChips(facilities, filters, { mode }), [facilities, filters, mode]);
  const types = useMemo(() => typesFor(facilities, filters, { mode }), [facilities, filters, mode]);
  const counts = useMemo(() => bandCounts(facilities, { mode }), [facilities, mode]);
  const escalation = chips.some((c) => ESCALATION_FLAGS.includes(c.key));

  const set = (patch) => onFiltersChange({ ...filters, ...patch });
  const toggleType = (key) => {
    const has = filters.types.includes(key);
    set({ types: has ? filters.types.filter((t) => t !== key) : [...filters.types, key] });
  };

  // In the rail each heading's unit goes under it, and a long choice wraps from the left.
  const head = compact ? "flex-col gap-0.5" : "items-baseline justify-between gap-3";
  const chipOf = (on) => `${chip(on)}${compact ? " text-left leading-[1.25]" : ""}`;

  const bandChoices = BAND_FILTERS.filter((b) => counts[b.band] != null);
  const band = filters.band ?? ALL_PLACES;

  return (
    <div className={compact ? "px-5 py-4" : "px-6 py-5"}>
      {hasCounty && (
        <div className="mb-6">
          <p className="label mb-3">Area</p>
          <AreaToggle county={Boolean(filters.county)} onChange={(county) => set({ county })} note={mode === "bands" ? outsideNote(meta) : null} />
        </div>
      )}
      {mode === "bands" && bandChoices.length > 1 && (
        <>
          <div className={`mb-3 flex ${head}`}>
            <p className="label" id="band-filter-label">{copy.bandTitle}</p>
            <p className="text-[12px] text-ink-2">{copy.bandUnit}</p>
          </div>
          <div role="group" aria-labelledby="band-filter-label" className="flex flex-wrap gap-1.5">
            {bandChoices.map((b) => (
              <button key={b.band} onClick={() => set({ band: b.band })} aria-pressed={band === b.band} aria-label={`${b.label}, ${places(counts[b.band])}`} className={chipOf(band === b.band)}>
                {b.label}
                <span className="tnum ml-1.5 opacity-70" aria-hidden="true">{counts[b.band].toLocaleString()}</span>
              </button>
            ))}
          </div>
          <p className="mt-2.5 text-[13px] leading-[1.45] text-ink-2">
            {(meta?.card?.bands ?? []).map((r) => r.band).filter((b) => bandPoints(meta, b) && (band === ALL_PLACES || Number(b) <= Number(band))).map((b) => `Band ${b}: ${bandPoints(meta, b)}`).join(". ")}.
            {band === ALL_PLACES && !compact && " Other places are drawn in grey."}
          </p>
        </>
      )}

      {types.length > 1 && (
        <>
          <div className={`mb-3 flex ${head} ${mode === "bands" ? "mt-6" : ""}`}>
            <p className="label" id="type-filter-label">{copy.typeTitle}</p>
            <p className="text-[12px] text-ink-2">any you pick</p>
          </div>
          <div role="group" aria-labelledby="type-filter-label" className="flex flex-wrap gap-1.5">
            {types.map((t) => (
              <button key={t.key} onClick={() => toggleType(t.key)} aria-pressed={filters.types.includes(t.key)} aria-label={`${t.label}, ${places(t.count)}`} className={chipOf(filters.types.includes(t.key))}>
                {t.label}
                <span className="tnum ml-1.5 opacity-70" aria-hidden="true">{t.count.toLocaleString()}</span>
              </button>
            ))}
          </div>
        </>
      )}

      {chips.length > 0 && (
        <>
          <div className={`mb-3 mt-6 flex ${head}`}>
            <p className="label" id="flag-filter-label">{copy.flagTitle}</p>
            <p className="text-[12px] text-ink-2">{copy.flagUnit}</p>
          </div>
          <div role="group" aria-labelledby="flag-filter-label" className="flex flex-wrap gap-1.5">
            <button onClick={() => set({ flag: null })} aria-pressed={filters.flag === null} className={chipOf(filters.flag === null)}>
              Any
            </button>
            {chips.map((c) => (
              <button key={c.key} onClick={() => set({ flag: filters.flag === c.key ? null : c.key })} aria-pressed={filters.flag === c.key} aria-label={`${c.label}, ${places(c.count)}`} className={chipOf(filters.flag === c.key)}>
                {c.label}
                <span className="tnum ml-1.5 opacity-70" aria-hidden="true">{c.count.toLocaleString()}</span>
              </button>
            ))}
          </div>
          {compact ? (
            <details className="mt-2.5 text-[12.5px] leading-[1.45] text-ink-2">
              <summary className="cursor-pointer border-b border-ink/25 text-ink-2 hover:text-ink [display:inline] [list-style:none] [&::-webkit-details-marker]:hidden">What these facts are</summary>
              <FactsNote meta={meta} escalation={escalation} className="mt-1.5" />
            </details>
          ) : (
            <FactsNote meta={meta} escalation={escalation} className="mt-2.5 text-[13px] leading-[1.45] text-ink-2" />
          )}
        </>
      )}
    </div>
  );
}

/** What the facts are: our reading of the 12 months before the list date (24 for the escalation facts). */
function FactsNote({ meta, escalation, className = "" }) {
  return (
    <div className={className}>
      <p>
        Our reading of the 12 months before the list date{meta?.generated ? <>, {fmtDate(meta.generated)}</> : null}, and of the
        24 months before it for the four escalation facts.
      </p>
      {escalation && <p className="mt-1.5">{ESCALATION_NOTE}</p>}
    </div>
  );
}

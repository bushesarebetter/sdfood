import { useEffect, useMemo, useState } from "react";
import { useAdvanced } from "./useAdvanced";
import { useMeta, useMode } from "./useMeta";
import { flagChips, typesFor, bandCounts } from "./lib/filters";
import { bandPoints } from "./lib/bands";
import { ESCALATION_FLAGS, ESCALATION_NOTE, ESCALATION_TITLE, FLAG_SHORT, THEMES } from "./lib/inspections";
import { fmtDate } from "./lib/dates";
import { BAND_FILTERS, ALL_PLACES } from "./constants";
import AreaToggle, { outsideNote } from "./AreaToggle";

// A choice; `strong` is an escalation fact, in ink and semibold as the list marks it.
const chip = (on, strong = false) =>
  `min-h-[32px] border px-2.5 py-1 text-[13px] leading-none ${
    on ? "border-ink bg-ink text-paper" : `border-rule-strong bg-transparent hover:border-ink hover:text-ink ${strong ? "font-semibold text-ink" : "text-ink-2"}`
  }`;

// A chip's count: a solid colour, never a faded one, so it keeps 4.5:1 on paper and on ink.
const countCls = (on) => `tnum ml-1.5 ${on ? "text-paper/80" : "text-ink-3"}`;

const places = (n) => `${Number(n || 0).toLocaleString("en-US")} ${n === 1 ? "place" : "places"}`;

const lowerFirst = (s) => `${s.charAt(0).toLowerCase()}${s.slice(1)}`;

/**
 * The small open-and-close mark after a disclosure's summary, turned while its own disclosure is open
 * (a named group, so an open disclosure around the filters turns none of them).
 */
function Chevron({ className }) {
  return (
    <svg width="10" height="6" viewBox="0 0 10 6" aria-hidden="true" className={`shrink-0 ${className}`}>
      <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

/**
 * The filters, each a row of buttons: in `bands` mode which bands to show;
 * then the kind of place, and a fact from the year before the list date (our
 * reading, from the index's flags; the escalation facts read two years and are
 * our counts of the patterns the County's Operator's Guide names). Each button's accessible name says its
 * count apart from its label ("Band 1, 16 places"). `compact` is the staff site's filter rail: tighter,
 * the facts in the list's short words (the full wording in each button's name and tooltip), the
 * escalation facts under their own heading, the themes of the majors one click away, and the notes
 * on the facts one click away.
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
  const chipOf = (on, strong = false) => `${chip(on, strong)}${compact ? " text-left leading-[1.25]" : ""}`;

  const bandChoices = BAND_FILTERS.filter((b) => counts[b.band] != null);
  const band = filters.band ?? ALL_PLACES;

  // One fact's choice: its words on the button (the list's short words in the rail), the full
  // wording in its accessible name and, when the words differ, its tooltip; then its count.
  const flagChip = (c, text = c.label, strong = false) => {
    const on = filters.flag === c.key;
    return (
      <button
        key={c.key}
        onClick={() => set({ flag: on ? null : c.key })}
        aria-pressed={on}
        aria-label={`${c.label}, ${places(c.count)}`}
        title={text === c.label ? undefined : c.label}
        className={chipOf(on, strong)}
      >
        {text}
        <span className={countCls(on)} aria-hidden="true">{c.count.toLocaleString()}</span>
      </button>
    );
  };
  const anyChip = (
    <button onClick={() => set({ flag: null })} aria-pressed={filters.flag === null} className={chipOf(filters.flag === null)}>
      Any
    </button>
  );

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
                <span className={countCls(band === b.band)} aria-hidden="true">{counts[b.band].toLocaleString()}</span>
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
                <span className={countCls(filters.types.includes(t.key))} aria-hidden="true">{t.count.toLocaleString()}</span>
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
          {compact ? (
            <CompactFacts chips={chips} flag={filters.flag} anyChip={anyChip} flagChip={flagChip} />
          ) : (
            <div role="group" aria-labelledby="flag-filter-label" className="flex flex-wrap gap-1.5">
              {anyChip}
              {chips.map((c) => flagChip(c))}
            </div>
          )}
          {compact ? (
            <details className="group/facts mt-2.5 text-[12.5px] leading-[1.45] text-ink-2">
              <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 border-b border-ink/25 text-ink-2 hover:text-ink [&::-webkit-details-marker]:hidden">
                What these facts are
                <Chevron className="group-open/facts:rotate-180" />
              </summary>
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

/**
 * The facts in the rail, in three parts: Any and the record facts; the escalation facts under their
 * own heading, marked in ink as the list marks them; and the themes of the majors in a disclosure of
 * their own, open whenever the fact chosen is a theme, and naming it when closed. One fact at a time.
 */
function CompactFacts({ chips, flag, anyChip, flagChip }) {
  const record = chips.filter((c) => FLAG_SHORT[c.key] && !ESCALATION_FLAGS.includes(c.key));
  const escalation = chips.filter((c) => ESCALATION_FLAGS.includes(c.key));
  const themes = chips.filter((c) => THEMES[c.key]);
  const themeOn = themes.some((c) => c.key === flag);
  const [themesOpen, setThemesOpen] = useState(themeOn);
  useEffect(() => { if (themeOn) setThemesOpen(true); }, [themeOn]);

  return (
    <div role="group" aria-labelledby="flag-filter-label">
      <div className="flex flex-wrap gap-1.5">
        {anyChip}
        {record.map((c) => flagChip(c, FLAG_SHORT[c.key]))}
      </div>
      {escalation.length > 0 && (
        <div role="group" aria-labelledby="flag-escalation-label" className="mt-3">
          <p id="flag-escalation-label" className="mb-1.5 text-[12px] leading-[1.35] text-ink-2">
            <span className="font-semibold text-ink">Over two years</span> ({lowerFirst(ESCALATION_TITLE)})
          </p>
          <div className="flex flex-wrap gap-1.5">
            {escalation.map((c) => flagChip(c, FLAG_SHORT[c.key], true))}
          </div>
        </div>
      )}
      {themes.length > 0 && (
        <details open={themesOpen} onToggle={(e) => setThemesOpen(e.currentTarget.open)} className="group/themes mt-3">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 text-[12.5px] text-ink-2 hover:text-ink [&::-webkit-details-marker]:hidden">
            <span>
              By theme of the major violation
              {themeOn && <>: <span className="font-semibold text-ink">{THEMES[flag]}</span></>}
            </span>
            <Chevron className="group-open/themes:rotate-180" />
          </summary>
          <div role="group" aria-label="By theme of the major violation" className="mt-1.5 flex flex-wrap gap-1.5">
            {themes.map((c) => flagChip(c, THEMES[c.key]))}
          </div>
        </details>
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

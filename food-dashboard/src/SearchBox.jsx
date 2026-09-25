import { useState, useMemo, useRef, useEffect } from "react";
import { useAdvanced } from "./useAdvanced";
import { useExpired, useMode } from "./useMeta";
import { searchPlaces, noMatchText } from "./lib/search";
import { kindsPhrase } from "./lib/framing";
import { typeLabel } from "./lib/inspections";
import { gradeView } from "./lib/grades";
import { markFor } from "./lib/marks";
import { SITE } from "./site";

const MAX_RESULTS = 8;

/**
 * Find a listed place by name or street. Searches every listed place, not
 * the filtered map: "is this place listed?" is the first question, and "no"
 * is an answer too, said in a live region with the County's own search
 * beside it. Each result gives its kind and grade, and in `bands` mode its
 * band; never a position.
 */
export default function SearchBox({ facilities, onSelect, large = false }) {
  const { copy } = useAdvanced();
  const mode = useMode();
  const expired = useExpired();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const boxRef = useRef(null);
  const id = large ? "place-search-hero" : "place-search";
  const listId = `${id}-results`;

  const results = useMemo(() => {
    const q = query.trim();
    if (q.length < 2 || !facilities) return [];
    return searchPlaces(facilities.features, q, MAX_RESULTS);
  }, [query, facilities]);
  const kinds = useMemo(() => kindsPhrase(facilities?.features), [facilities]);

  useEffect(() => setCursor(0), [query]);

  useEffect(() => {
    function onDocClick(e) {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function choose(feature) {
    onSelect(feature);
    setQuery(feature.properties.name ?? "");
    setOpen(false);
  }

  function onKeyDown(e) {
    if (e.key === "Escape") {
      setOpen(false);
      return;
    }
    if (!open || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => (c + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => (c - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(results[cursor]);
    }
  }

  const typed = open && query.trim().length >= 2 && Boolean(facilities);
  const showResults = typed && results.length > 0;
  const showEmpty = typed && results.length === 0;

  const inputClass = large
    ? "h-[54px] w-full border border-ink/30 bg-paper pl-12 pr-4 text-[17px] text-ink placeholder:text-ink-3 focus:border-ink focus:outline-none"
    : "h-11 w-full border border-rule-strong bg-paper-sunk pl-9 pr-3 text-[16px] text-ink placeholder:text-ink-3 focus:border-ink focus:bg-paper focus:outline-none md:h-auto md:py-[7px] md:text-[14px]";
  const iconSize = large ? 18 : 14;
  const panel = "absolute left-0 right-0 top-full z-50 mt-1 border border-rule-strong bg-paper shadow-paper";

  return (
    <div ref={boxRef} className="relative w-full">
      <div className="relative">
        <svg className={`pointer-events-none absolute top-1/2 -translate-y-1/2 text-ink-3 ${large ? "left-4" : "left-3"}`} width={iconSize} height={iconSize} viewBox="0 0 14 14" fill="none" aria-hidden="true">
          <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.5" />
          <path d="M9.5 9.5L13 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <input
          type="search"
          name="place-search"
          id={id}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder={large ? `Search a ${SITE.name} restaurant or market` : copy.searchPlaceholder}
          aria-label={copy.searchPlaceholder}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={showResults}
          aria-controls={listId}
          aria-activedescendant={showResults ? `${listId}-${cursor}` : undefined}
          autoComplete="off"
          className={inputClass}
        />
      </div>

      {/* Always present, so a "no match" is announced when it appears. */}
      <div role="status" aria-live="polite">
        {showEmpty && (
          <div className={`${panel} px-3.5 py-3 text-[13px] leading-[1.5] text-ink-2`}>
            <p>{noMatchText(query, { count: facilities.features.length, kinds })}</p>
            <p className="mt-1.5">
              <a href={SITE.regulator.resultsUrl} target="_blank" rel="noopener noreferrer" className="border-b border-ink/25 text-ink hover:border-ink">
                Search the County&rsquo;s own record
              </a>
            </p>
          </div>
        )}
        {showResults && <span className="sr-only">{results.length} listed {results.length === 1 ? "place matches" : "places match"}.</span>}
      </div>

      {showResults && (
        <div className={panel}>
          <ul id={listId} role="listbox" aria-label="Listed places">
            {results.map((f, i) => {
              const p = f.properties;
              const mark = markFor(p, { mode });
              const g = gradeView(p.grade);
              return (
                <li
                  key={p.facility_id}
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === cursor}
                  onMouseEnter={() => setCursor(i)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(f)}
                  className={`flex min-h-[44px] w-full cursor-pointer items-center justify-between gap-3 border-b border-rule px-3.5 py-2 text-left last:border-b-0 ${i === cursor ? "bg-paper-edge" : "hover:bg-paper-sunk"}`}
                >
                  <span className="min-w-0 flex-1">
                    <span className={`block truncate text-ink ${large ? "text-[15px]" : "text-[13.5px]"}`}>{p.name}</span>
                    <span className="block truncate text-[12.5px] text-ink-2">
                      {p.address}, {typeLabel(p.facility_type)}, {g.graded ? `grade ${g.short}` : g.text.toLowerCase()}
                    </span>
                  </span>
                  {!expired && mark.label && (
                    <span className="tnum shrink-0 whitespace-nowrap px-1.5 py-0.5 text-[12px] font-semibold" style={{ color: mark.text ?? undefined }}>
                      {mark.label}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
          {mode === "bands" && <p className="border-t border-rule px-3.5 py-1.5 text-[12px] text-ink-2">Showing listed places only.</p>}
        </div>
      )}
    </div>
  );
}

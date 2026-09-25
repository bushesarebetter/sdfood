/**
 * The pieces every place view shares (the panel, the page and the phone
 * sheet), so the three say the same things in the same words: the lines under
 * the name, the per-place loading states, the County's disclaimer, what the
 * County's record shows, and the items by theme.
 */
import { useMeta, useExpired } from "./useMeta";
import { placeLines } from "./lib/framing";
import { PLACE_STATUS_TEXT } from "./lib/placeData";
import { themeCounts } from "./lib/inspections";
import { fmtMonth } from "./lib/dates";
import { SITE } from "./site";

const LINK = "border-b border-ink/25 text-ink hover:border-ink";

/** The grade, and in `bands` mode the band, its points and its backtest rate, under the place's name. */
export function PlaceLines({ place, large = false, withGrade = true }) {
  const meta = useMeta();
  const expired = useExpired();
  const lines = placeLines(place, meta, { expired, withGrade });
  if (!lines.length) return null;
  return (
    <div className={`space-y-1.5 leading-[1.5] text-ink-2 ${large ? "text-[15px]" : "text-[13.5px]"}`}>
      {lines.map((l, i) => (
        <p key={i} className={i === 0 && withGrade ? "text-ink" : undefined}>{l}</p>
      ))}
    </div>
  );
}

/** Loading, missing and error states for one place's record, with a way on in each. */
export function PlaceStatus({ status, id, onRetry, large = false }) {
  const text = large ? "text-[15px]" : "text-[13.5px]";
  if (status === "loading") {
    return (
      <div aria-busy="true" role="status" className="space-y-2.5">
        <p className="sr-only">{PLACE_STATUS_TEXT.loading}</p>
        <div className="h-3 w-2/3 animate-pulse bg-paper-edge" />
        <div className="h-3 w-5/6 animate-pulse bg-paper-edge" />
        <div className="h-24 w-full animate-pulse bg-paper-edge" />
      </div>
    );
  }
  return (
    <div role="alert" className={`border border-rule-strong bg-paper-sunk px-4 py-3 leading-[1.55] text-ink-2 ${text}`}>
      <p className="text-ink">{PLACE_STATUS_TEXT[status] ?? PLACE_STATUS_TEXT.error}</p>
      <p className="mt-2">
        The County&rsquo;s own <a href={SITE.regulator.resultsUrl} target="_blank" rel="noopener noreferrer" className={LINK}>inspection search</a>{" "}
        has this place&rsquo;s record{id ? <> under permit record <span className="font-mono text-[0.92em]">{id}</span></> : null}.
      </p>
      {onRetry && (
        <button onClick={onRetry} className="mt-3 bg-ink px-4 py-2 text-[13px] font-semibold text-paper hover:bg-ink-2">
          Try again
        </button>
      )}
    </div>
  );
}

/** The County's own disclaimer for SD Food Info, quoted as published, attributed and linked. */
export function CountyDisclaimer({ collapsed = false }) {
  const d = SITE.regulator.disclaimer;
  const body = (
    <>
      <blockquote className="space-y-2 border-l-0 font-serif text-[14px] leading-[1.55] text-ink-2">
        {d.paragraphs.map((p, i) => <p key={i}>&ldquo;{p}&rdquo;</p>)}
      </blockquote>
      <p className="mt-2 text-[13px] text-ink-2">
        From the County&rsquo;s <a href={d.url} target="_blank" rel="noopener noreferrer" className={LINK}>SD Food Info disclaimer</a>, as
        published on {d.retrieved}. &ldquo;This web site&rdquo; there means {SITE.regulator.resultsName}, the source of every record here.
      </p>
    </>
  );
  if (collapsed) {
    return (
      <details className="text-[13px] text-ink-2">
        <summary className="cursor-pointer text-ink">The County&rsquo;s disclaimer for {SITE.regulator.resultsName}</summary>
        <div className="mt-2">{body}</div>
      </details>
    );
  }
  return body;
}

/** "What the County's record shows": facts, each with the County's text and, where it applies, our reading. */
export function RecordFactList({ facts, large = false, empty }) {
  const text = large ? "text-[15px]" : "text-[13.5px]";
  if (!facts.length) return <p className={`${text} leading-[1.55] text-ink-2`}>{empty}</p>;
  return (
    <ul>
      {facts.map((f) => (
        <li key={f.key} className="border-b border-rule py-3 first:pt-0 last:border-b-0">
          <p className="label">{f.title}</p>
          {f.county.map((line, i) => (
            <p key={i} className={`mt-1 leading-[1.5] text-ink ${text}`}>{line}</p>
          ))}
          {f.reading && <p className={`mt-1 leading-[1.5] text-ink-2 ${large ? "text-[14px]" : "text-[13px]"}`}>{f.reading}</p>}
        </li>
      ))}
    </ul>
  );
}

/** Items cited in the three years before the last visit, by theme. */
export function ThemeList({ violations, advanced = false, large = false }) {
  const themes = themeCounts(violations);
  const text = large ? "text-[14.5px]" : "text-[13.5px]";
  if (!themes.length) return <p className={`${text} text-ink-2`}>No items cited in the three years before the last visit.</p>;
  return (
    <>
      <ul>
        {themes.map((t) => (
          <li key={t.theme} className={`flex items-baseline justify-between gap-3 border-b border-rule py-2 last:border-b-0 ${text}`}>
            <span className="text-ink">{t.label}</span>
            <span className="tnum shrink-0 text-right text-ink-2">
              {advanced ? (
                <>{t.major} / {t.minor} / {t.grp}</>
              ) : (
                <>{t.count} {t.count === 1 ? "item" : "items"}{t.major > 0 && <>, <span className="font-medium text-band-1">{t.major} major</span></>}</>
              )}
              {t.complaint > 0 && <span className="block text-[12.5px]">{t.complaint} found at a complaint visit</span>}
              <span className="block text-[12.5px]">latest {fmtMonth(t.last)}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[13px] leading-[1.5] text-ink-2">
        {advanced ? "Major / minor / good retail practice. " : ""}Our reading: each item is put under a theme from the County&rsquo;s item text.
      </p>
    </>
  );
}

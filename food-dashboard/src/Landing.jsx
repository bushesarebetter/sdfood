import { useState } from "react";
import SearchBox from "./SearchBox";
import AboutModal from "./AboutModal";
import SampleBanner from "./SampleBanner";
import { Footer } from "./PageFrame";
import { useMeta, useMode } from "./useMeta";
import { headline, subhead, gradeContextSentence } from "./lib/framing";
import { bandDefs, bandPoints, bandSummary } from "./lib/bands";
import { bandCounts } from "./lib/filters";
import { fmtDate } from "./lib/dates";
import { BAND_TEXT } from "./lib/marks";
import { SITE } from "./site";

/**
 * The front page: what the site holds, a search, how many places it lists
 * and how fresh the record is, and the way into the map and the list. It
 * names no place. In `bands` mode it states what each band has been worth.
 */
export default function Landing({ facilities, error, onRetry, onEnter, onNavigate, notice }) {
  const [aboutOpen, setAboutOpen] = useState(false);
  const meta = useMeta();
  const mode = useMode();
  const listed = facilities?.features.length ?? null;
  const counts = mode === "bands" && facilities ? bandCounts(facilities) : null;

  return (
    <div className="flex min-h-dvh flex-col bg-paper">
      <header className="border-b border-rule-strong">
        <div className="mx-auto flex min-h-[52px] max-w-[76rem] items-center justify-between px-5 py-3 md:px-8">
          <a href="/" className="font-serif text-[17px] font-semibold tracking-[-0.01em] text-ink">
            {SITE.shortTitle}
            <span className="ml-2 hidden text-[12px] font-normal text-ink-2 sm:inline">{SITE.name}</span>
          </a>
          <nav className="flex items-center gap-5 text-[13px]">
            <a href={SITE.regulator.resultsUrl} target="_blank" rel="noopener noreferrer" className="hidden border-b border-ink/25 pb-px text-ink-2 hover:border-ink hover:text-ink sm:inline">
              The County&rsquo;s inspection search
            </a>
            <button onClick={() => setAboutOpen(true)} className="border-b border-ink/25 pb-px text-ink-2 hover:border-ink hover:text-ink">
              About this site
            </button>
          </nav>
        </div>
      </header>
      <SampleBanner />

      {notice}

      <main className="mx-auto w-full max-w-[52rem] flex-1 px-5 pb-28 pt-12 md:px-8 md:pb-16 md:pt-20">
        <p className="label mb-4">{SITE.fullName}</p>
        <h1 className="font-serif text-[34px] font-medium leading-[1.08] tracking-[-0.025em] text-ink sm:text-[42px]">
          {headline(meta, facilities?.features)}
        </h1>
        <p className="mt-5 max-w-[60ch] font-serif text-[18px] leading-[1.5] text-ink-2">{subhead(meta)}</p>

        <div className="mt-8 max-w-[36rem]">
          <SearchBox large facilities={facilities} onSelect={(f) => onEnter(f)} />
          <p className="mt-2 text-[13px] text-ink-2">{SITE.searchHint}</p>
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-4">
          <button onClick={() => onEnter(null)} className="bg-ink px-6 py-3 text-[15px] font-semibold text-paper hover:bg-ink-2">
            Open the map
          </button>
          <button onClick={() => onEnter(null, { list: true })} className="border border-ink px-6 py-3 text-[15px] font-semibold text-ink hover:bg-paper-sunk">
            Open the list
          </button>
        </div>

        <div className="mt-8 text-[14px] leading-[1.55] text-ink-2" aria-live="polite">
          {error ? (
            <div role="alert" className="border border-rule-strong bg-paper-sunk px-4 py-3">
              <p className="text-ink">{error}</p>
              <p className="mt-1">
                The County&rsquo;s own <a href={SITE.regulator.resultsUrl} target="_blank" rel="noopener noreferrer" className="border-b border-ink/25 text-ink hover:border-ink">inspection search</a> has every record.
              </p>
              {onRetry && <button onClick={onRetry} className="mt-3 bg-ink px-4 py-2 text-[13px] font-semibold text-paper hover:bg-ink-2">Try again</button>}
            </div>
          ) : (
            <p>
              {listed != null ? <><b className="tnum font-semibold text-ink">{listed.toLocaleString()}</b> places listed. </> : "Loading the list. "}
              {meta?.inspections_through && <>Inspections through {fmtDate(meta.inspections_through)}. </>}
              {meta?.expires && <>Shown until {fmtDate(meta.expires)}.</>}
            </p>
          )}
        </div>

        {mode === "bands" && bandDefs(meta).length > 0 && (
          <div className="mt-10 border-t border-rule pt-6">
            <h2 className="label mb-3">The bands</h2>
            <ul className="space-y-3">
              {bandDefs(meta).map((d) => (
                <li key={d.band} className="text-[14px] leading-[1.5] text-ink-2">
                  <span className="font-semibold" style={{ color: BAND_TEXT[d.band] }}>Band {d.band}</span>
                  <span className="text-ink">: {bandPoints(meta, d.band) ?? ""}{counts?.[d.band] != null ? `, ${(counts[d.band] - (counts[String(Number(d.band) - 1)] ?? 0)).toLocaleString()} places` : ""}. </span>
                  {bandSummary(meta, d.band)}
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="mt-10 max-w-[64ch] border-t border-rule pt-6 text-[14px] leading-[1.55] text-ink-2">{gradeContextSentence(meta)}</p>
      </main>

      <Footer onNavigate={onNavigate} />

      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-rule-strong bg-paper px-4 pt-3 md:hidden" style={{ paddingBottom: "max(12px, env(safe-area-inset-bottom))" }}>
        <button onClick={() => onEnter(null)} className="block w-full bg-ink py-3 text-center text-[15px] font-semibold text-paper">
          Open the map
        </button>
      </div>

      {aboutOpen && <AboutModal onClose={() => setAboutOpen(false)} onNavigate={onNavigate} />}
    </div>
  );
}

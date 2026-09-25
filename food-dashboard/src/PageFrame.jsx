import { REPO_URL } from "./constants";
import { SITE, STUDENT_NOTE } from "./site";
import SampleBanner from "./SampleBanner";
import ExpiryBanner from "./ExpiryBanner";
import { useExpired } from "./useMeta";

const LINK = "border-b border-ink/25 text-ink-2 hover:border-ink hover:text-ink";

/**
 * The frame for text pages (a place as a page, privacy and terms, the
 * corrections log, the 404): the masthead, the sample and expiry notices,
 * one measure of text, and the footer.
 */
export default function PageFrame({ onNavigate, wide = false, children }) {
  const expired = useExpired();
  const go = (p) => (e) => {
    e.preventDefault();
    onNavigate(p);
  };

  return (
    <div className="flex min-h-dvh flex-col bg-paper">
      <header className="print-hide border-b border-rule-strong">
        <div className="mx-auto flex min-h-[52px] max-w-[76rem] items-center justify-between px-5 py-3 md:px-8">
          <a href="/" onClick={go("/")} className="font-serif text-[17px] font-semibold tracking-[-0.01em] text-ink">
            {SITE.shortTitle}
            <span className="ml-2 hidden text-[12px] font-normal text-ink-2 sm:inline">{SITE.name}</span>
          </a>
          {!expired && (
            <a href="/map" onClick={go("/map")} className={`pb-px text-[13px] ${LINK}`}>
              Open the map
            </a>
          )}
        </div>
      </header>
      <SampleBanner />
      <ExpiryBanner />

      <main className={`mx-auto w-full flex-1 px-5 pb-16 pt-12 md:px-8 md:pt-16 ${wide ? "max-w-[56rem]" : "max-w-[44rem]"}`}>{children}</main>

      <Footer onNavigate={onNavigate} />
    </div>
  );
}

export function Footer({ onNavigate }) {
  const go = (p) => (e) => {
    e.preventDefault();
    onNavigate(p);
  };
  return (
    <footer className="print-hide border-t border-rule">
      <div className="mx-auto max-w-[76rem] px-5 py-5 text-[13px] leading-[1.6] text-ink-2 md:px-8">
        <p className="text-ink">{STUDENT_NOTE}</p>
        <p className="mt-1">By {SITE.authors}. {SITE.attributions}</p>
        <p className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
          <a href={SITE.regulator.resultsUrl} target="_blank" rel="noopener noreferrer" className={LINK}>The County&rsquo;s inspection search</a>
          <a href="/privacy" onClick={go("/privacy")} className={LINK}>Privacy, terms and corrections</a>
          <a href="/corrections" onClick={go("/corrections")} className={LINK}>Corrections log</a>
          <a href={REPO_URL} target="_blank" rel="noopener noreferrer" className={LINK}>Code on GitHub</a>
        </p>
      </div>
    </footer>
  );
}

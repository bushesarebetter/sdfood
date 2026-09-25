import PageFrame from "./PageFrame";
import SearchBox from "./SearchBox";
import { useMeta } from "./useMeta";
import { fmtDate } from "./lib/dates";
import { placePath } from "./lib/links";
import { SITE } from "./site";

/**
 * What the site is once meta.expires has passed: a notice and a search of
 * the record it holds. No list, no map, no bands, no headline claim. A place
 * found here opens as a page, with its record and the expiry notice.
 */
export default function ExpiredView({ facilities, error, onNavigate }) {
  const meta = useMeta();
  return (
    <PageFrame onNavigate={onNavigate}>
      <p className="label mb-4">Out of date</p>
      <h1 className="font-serif text-[32px] font-medium leading-[1.1] tracking-[-0.02em] text-ink sm:text-[38px]">This export is out of date</h1>
      <p className="mt-5 max-w-[60ch] font-serif text-[17px] leading-[1.55] text-ink-2">
        Its inspections run through {meta?.inspections_through ? fmtDate(meta.inspections_through) : "an earlier date"}
        {meta?.expires ? <>, and it was shown until {fmtDate(meta.expires)}</> : null}. Search the record it holds below; the
        County&rsquo;s own search has current results.
      </p>
      <div className="mt-8 max-w-[36rem]">
        <SearchBox large facilities={facilities} onSelect={(f) => onNavigate(placePath(f.properties))} />
        {error && <p role="alert" className="mt-3 text-[14px] text-ink">{error}</p>}
      </div>
      <p className="mt-6 text-[15px]">
        <a href={SITE.regulator.resultsUrl} target="_blank" rel="noopener noreferrer" className="border-b border-ink/25 text-ink hover:border-ink">
          The County&rsquo;s own inspection search
        </a>
      </p>
    </PageFrame>
  );
}

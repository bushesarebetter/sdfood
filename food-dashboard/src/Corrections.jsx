import PageFrame from "./PageFrame";
import { useMeta } from "./useMeta";
import { findPlace, placePath } from "./lib/links";
import { fmtDate } from "./lib/dates";

/**
 * The corrections log: every correction made to this export
 * (`meta.corrections`, from docs/corrections.json), newest first, with what
 * changed and why.
 */
export default function Corrections({ facilities, onNavigate }) {
  const meta = useMeta();
  const list = Array.isArray(meta?.corrections) ? [...meta.corrections].sort((a, b) => String(b.date ?? "").localeCompare(String(a.date ?? ""))) : [];

  return (
    <PageFrame onNavigate={onNavigate}>
      <p className="label mb-4">Corrections</p>
      <h1 className="mb-8 font-serif text-[36px] font-medium leading-[1.08] tracking-[-0.02em] text-ink sm:text-[44px]">Corrections log</h1>
      {list.length === 0 ? (
        <p className="font-serif text-[17px] leading-[1.55] text-ink-2">No corrections have been made to this export.</p>
      ) : (
        <ol className="space-y-5">
          {list.map((c, i) => {
            const f = findPlace(facilities?.features, c.facility_id);
            return (
              <li key={`${c.date}-${c.facility_id}-${i}`} className="border-b border-rule pb-5 last:border-b-0">
                <p className="label">{fmtDate(c.date)}</p>
                <p className="mt-1 text-[15px] text-ink">
                  {f ? (
                    <a href={placePath(f.properties)} onClick={(e) => { e.preventDefault(); onNavigate(placePath(f.properties)); }} className="border-b border-ink/25 hover:border-ink">
                      {f.properties.name}
                    </a>
                  ) : (
                    <>Permit record <span className="font-mono text-[14px]">{c.facility_id}</span></>
                  )}
                </p>
                <p className="mt-1 text-[15px] leading-[1.55] text-ink-2"><b className="font-semibold text-ink">What changed:</b> {c.what}</p>
                {c.why && <p className="mt-1 text-[15px] leading-[1.55] text-ink-2"><b className="font-semibold text-ink">Why:</b> {c.why}</p>}
              </li>
            );
          })}
        </ol>
      )}
    </PageFrame>
  );
}

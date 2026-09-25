import { useMeta, useMode } from "./useMeta";
import FilterBar from "./FilterBar";
import NearPanel from "./NearPanel";
import DistrictSummary from "./DistrictSummary";
import { fmtDate } from "./lib/dates";
import { headline, subhead, gradeContextSentence } from "./lib/framing";
import { bandDefs, bandPoints, rateRatio } from "./lib/bands";
import { BAND_TEXT } from "./lib/marks";

const pct = (x) => (typeof x === "number" ? `${Math.round(x * 100)}%` : "");

/**
 * The column beside the map, read top to bottom: what this shows and how
 * fresh it is, which places to show, whether any are near an address, in
 * `bands` mode what each band has been worth, and where the places are.
 */
export default function Sidebar({ facilities, filters, onFiltersChange, onPoint, onSelect }) {
  const meta = useMeta();
  const mode = useMode();

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-paper">
      <div className="px-6 pb-6 pt-6">
        <p className="label mb-3">What this shows</p>
        <h2 className="font-serif text-[23px] font-medium leading-[1.16] tracking-[-0.015em] text-ink">{headline(meta, facilities?.features)}</h2>
        <p className="mt-3.5 text-[14px] leading-[1.55] text-ink-2">{subhead(meta)}</p>
        <p className="mt-2.5 text-[13px] leading-[1.5] text-ink-2">{gradeContextSentence(meta)}</p>
        <p className="mt-3 text-[13px] leading-[1.5] text-ink-2">
          {meta?.inspections_through && <>Inspections through {fmtDate(meta.inspections_through)}.</>}
          {meta?.generated && <> Drawn up {fmtDate(meta.generated)}.</>}
          {meta?.expires && <> Shown until {fmtDate(meta.expires)}.</>}
        </p>
      </div>

      <hr className="rule" />
      <FilterBar filters={filters} onFiltersChange={onFiltersChange} facilities={facilities} />

      <hr className="rule" />
      <NearPanel facilities={facilities} filters={filters} onPoint={onPoint} onSelect={onSelect} />

      {mode === "bands" && bandDefs(meta).length > 0 && (
        <>
          <hr className="rule-strong" />
          <BandTable meta={meta} />
        </>
      )}

      <hr className="rule-strong" />
      <DistrictSummary facilities={facilities} filters={filters} onFiltersChange={onFiltersChange} />
    </div>
  );
}

/** Each band's points, its places now, and its backtest rate beside the rate below the bands. */
function BandTable({ meta }) {
  const defs = bandDefs(meta);
  const rest = meta?.card?.rest?.rate;
  return (
    <div className="px-6 py-5">
      <p className="label mb-3" id="band-table-label">The bands in the backtest</p>
      <table className="w-full text-[13px]" aria-labelledby="band-table-label">
        <thead>
          <tr className="border-b border-rule-strong text-left">
            {["Band", "Points", "Had a major", "× below"].map((h, i) => (
              <th key={h} scope="col" className={`pb-1.5 text-[12px] font-semibold text-ink-2 ${i ? "text-right" : ""}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {defs.map((d) => (
            <tr key={d.band} className="border-b border-rule">
              <th scope="row" className="py-1.5 text-left font-semibold" style={{ color: BAND_TEXT[d.band] }}>Band {d.band}</th>
              <td className="tnum py-1.5 text-right text-ink-2">{bandPoints(meta, d.band)?.replace(" points", "") ?? ""}</td>
              <td className="tnum py-1.5 text-right text-ink">{pct(d.rate)}</td>
              <td className="tnum py-1.5 text-right text-ink">{rateRatio(meta, d.band) ?? ""}</td>
            </tr>
          ))}
          {typeof rest === "number" && (
            <tr>
              <th scope="row" className="py-1.5 text-left font-normal text-ink-2">Below the bands</th>
              <td />
              <td className="tnum py-1.5 text-right text-ink-2">{pct(rest)}</td>
              <td className="tnum py-1.5 text-right text-ink-2">1</td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="mt-2.5 text-[13px] leading-[1.45] text-ink-2">
        The share of each band&rsquo;s places that had a major violation at their next routine inspection, on the list drawn up the same way
        {meta?.catch_run?.as_of ? ` on ${fmtDate(meta.catch_run.as_of)}` : " for the backtest"}, and how many times the rate below the bands that is.
      </p>
    </div>
  );
}

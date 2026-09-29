import { useMemo } from "react";
import { useMeta, useMode } from "./useMeta";
import { passesFilters, sortPlaces } from "./lib/filters";
import { saveCsv } from "./lib/format";
import { districtGuidance } from "./lib/staff";
import { shownBand } from "./lib/marks";
import { SITE } from "./site";

const ACTION = "border-b border-ink/25 text-[12px] font-normal text-ink-2 hover:border-ink hover:text-ink";

/**
 * Listed places by council district, for the filters chosen other than district, with what the
 * County's record shows for each in the 12 months before the list date (our reading of the record's
 * flags): places with a major violation, places ordered closed for a health hazard, places with a B
 * or C, and in `bands` mode places in a band. On the staff site it opens with what to do. Select a
 * district to filter the map and list to it; select it again to clear. Each district can open its
 * list, or download its places as a CSV. `/map?district=N` opens a district directly, so an office
 * can bookmark its own.
 */
export default function DistrictSummary({ facilities, filters, onFiltersChange, onOpenList = null }) {
  const meta = useMeta();
  const mode = useMode();
  const guidance = districtGuidance(meta);

  const rows = useMemo(() => {
    if (!facilities) return [];
    const base = { ...filters, districts: [] };
    const by = new Map();
    for (const f of facilities.features) {
      const p = f.properties;
      if (!passesFilters(p, base, { mode })) continue;
      const d = p.council_district ?? null;
      const r = by.get(d) ?? { d, n: 0, major: 0, closed: 0, bc: 0, band: 0 };
      const flags = p.flags ?? [];
      r.n += 1;
      r.major += flags.includes("major") ? 1 : 0;
      r.closed += flags.includes("closed") ? 1 : 0;
      r.bc += flags.includes("bc") ? 1 : 0;
      r.band += mode === "bands" && shownBand(p, { mode }) ? 1 : 0;
      by.set(d, r);
    }
    return [...by.values()].sort((a, b) => (a.d ?? 99) - (b.d ?? 99));
  }, [facilities, filters, mode]);

  const toggle = (d) => {
    const on = filters.districts.length === 1 && filters.districts[0] === d;
    onFiltersChange({ ...filters, districts: on ? [] : [d] });
  };
  const openList = (d) => {
    if (onOpenList) onOpenList(d);
    else onFiltersChange({ ...filters, districts: [d] });
  };
  const download = (d) => {
    if (!facilities) return;
    const scope = { ...filters, districts: [d] };
    const places = sortPlaces(facilities.features.filter((f) => passesFilters(f.properties, scope, { mode })), { mode });
    saveCsv(places, { meta, mode, filters: scope });
  };
  const cols = [["Places", "n"], ["Major", "major"], ["Closed", "closed"], ["B or C", "bc"], ...(mode === "bands" ? [["In a band", "band"]] : [])];

  return (
    <div className="px-6 py-5">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <p className="label" id="district-label">By {SITE.districts.label.toLowerCase()}</p>
        <p className="text-[12px] text-ink-2">select to filter</p>
      </div>
      {guidance.length > 0 && (
        <div className="mb-4 border border-rule-strong bg-paper-sunk px-3 py-2.5 text-[12.5px] leading-[1.45] text-ink-2">
          <p className="label mb-1.5">What to do</p>
          <ul className="list-disc space-y-1 pl-4">
            {guidance.map((g) => <li key={g}>{g}</li>)}
          </ul>
        </div>
      )}
      <table className="w-full text-[13px]" aria-labelledby="district-label">
        <thead>
          <tr className="border-b border-rule-strong text-left">
            <th scope="col" className="pb-1.5 text-[12px] font-semibold text-ink-2">District</th>
            {cols.map(([h]) => <th key={h} scope="col" className="pb-1.5 text-right text-[12px] font-semibold text-ink-2">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const on = r.d != null && filters.districts.length === 1 && filters.districts[0] === r.d;
            const name = r.d != null ? `${SITE.districts.short} ${r.d}` : "Outside the City";
            return (
              <tr key={r.d ?? "outside"} className={`border-b border-rule align-top ${on ? "font-semibold text-ink" : "text-ink-2"}`}>
                <th scope="row" className="py-1.5 text-left font-normal">
                  {r.d != null ? (
                    <>
                      <button onClick={() => toggle(r.d)} aria-pressed={on} className={`text-left hover:text-ink ${on ? "font-semibold text-ink" : ""}`}>{name}</button>
                      <span className="mt-0.5 flex gap-2.5">
                        <button onClick={() => openList(r.d)} aria-label={`Open the list for ${name}`} className={ACTION}>list</button>
                        <button onClick={() => download(r.d)} aria-label={`Download ${name}'s places (CSV)`} className={ACTION}>CSV</button>
                      </span>
                    </>
                  ) : name}
                </th>
                {cols.map(([h, k]) => <td key={h} className="tnum py-1.5 text-right">{r[k].toLocaleString()}</td>)}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2.5 text-[12.5px] leading-[1.45] text-ink-2">
        Places with each fact in the 12 months before the list date (our reading of the County&rsquo;s record). Bookmark a
        district: {typeof window !== "undefined" ? window.location.origin : ""}/map?district=3.
      </p>
    </div>
  );
}

import { useMemo } from "react";
import { useMode } from "./useMeta";
import { passesFilters } from "./lib/filters";
import { SITE } from "./site";

/**
 * Listed places by council district, for the filters chosen other than
 * district. Select one to filter the map to it; select it again to clear.
 */
export default function DistrictSummary({ facilities, filters, onFiltersChange }) {
  const mode = useMode();

  const rows = useMemo(() => {
    if (!facilities) return [];
    const base = { ...filters, districts: [] };
    const counts = {};
    let outside = 0;
    for (const f of facilities.features) {
      if (!passesFilters(f.properties, base, { mode })) continue;
      const d = f.properties.council_district;
      if (d) counts[d] = (counts[d] || 0) + 1;
      else outside += 1;
    }
    const list = Object.entries(counts).map(([d, n]) => ({ d: Number(d), n })).sort((a, b) => a.d - b.d);
    return outside ? [...list, { d: null, n: outside }] : list;
  }, [facilities, filters, mode]);

  const toggle = (d) => {
    const on = filters.districts.length === 1 && filters.districts[0] === d;
    onFiltersChange({ ...filters, districts: on ? [] : [d] });
  };

  return (
    <div className="px-6 py-5">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <p className="label" id="district-label">By {SITE.districts.label.toLowerCase()}</p>
        <p className="text-[12px] text-ink-2">select to filter the map</p>
      </div>
      <ul aria-labelledby="district-label">
        {rows.map(({ d, n }) => {
          const on = d != null && filters.districts.length === 1 && filters.districts[0] === d;
          const name = d != null ? `${SITE.districts.short} ${d}` : "Outside the City";
          return (
            <li key={d ?? "outside"}>
              <button
                onClick={() => d != null && toggle(d)}
                aria-pressed={on}
                aria-label={`${name}, ${n.toLocaleString()} ${n === 1 ? "place" : "places"}`}
                disabled={d == null}
                className={`flex w-full items-baseline justify-between gap-3 border-b border-rule py-1.5 text-left text-[14px] ${on ? "font-semibold text-ink" : "text-ink-2 hover:text-ink"} disabled:cursor-default`}
              >
                <span>{name}</span>
                <span className="tnum" aria-hidden="true">{n.toLocaleString()}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

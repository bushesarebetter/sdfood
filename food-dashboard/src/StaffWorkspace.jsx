import { useEffect, useMemo, useState } from "react";
import Header from "./Header";
import MapView from "./MapView";
import PlaceTable from "./PlaceTable";
import PlacePanel from "./PlacePanel";
import FilterBar from "./FilterBar";
import NearPanel from "./NearPanel";
import DistrictSummary from "./DistrictSummary";
import Notice from "./Notice";
import StaffBanner from "./StaffBanner";
import ExpiryBanner from "./ExpiryBanner";
import { BandTable, DistrictPicker } from "./Sidebar";
import { useMeta, useMode } from "./useMeta";
import { passesFilters } from "./lib/filters";
import { fmtDate } from "./lib/dates";
import { headline, subhead, gradeContextSentence } from "./lib/framing";
import { bandDefs } from "./lib/bands";

/** The staff site's three views, each at its own address. */
export const STAFF_TABS = [
  { key: "list", label: "List", path: "/" },
  { key: "map", label: "Map", path: "/map" },
  { key: "summary", label: "Summary", path: "/summary" },
];

/**
 * The staff site on a screen 768px or wider: the masthead, the one-line staff notice, then three views
 * of the same filtered places, each at its own address. List (`/`, the default) is the whole list,
 * full width, with the name filter, sorting, the printout and the CSV. Map (`/map`) draws the same
 * places. Summary (`/summary`) holds what the list is, the bands in the backtest and the district
 * view with what to do. The filters sit in a rail on the left (a panel behind a button under 1280px)
 * and apply to every view. A place opens in the panel on the right from any view. The map loads the
 * first time it is shown and is kept after, so going back to it does not redraw it.
 */
export default function StaffWorkspace({
  facilities,
  filters,
  defaults,
  onFiltersChange,
  hasCounty,
  selected,
  onSelect,
  tab,
  onTab,
  pointOverlay,
  onPoint,
  onMapError,
  onHome,
  onNavigate,
}) {
  const meta = useMeta();
  const mode = useMode();
  const [mapSeen, setMapSeen] = useState(tab === "map");
  useEffect(() => { if (tab === "map") setMapSeen(true); }, [tab]);
  const [railOpen, setRailOpen] = useState(false);
  useEffect(() => { setRailOpen(false); }, [tab]);

  const count = useMemo(
    () => (facilities ? facilities.features.filter((f) => passesFilters(f.properties, filters, { mode })).length : 0),
    [facilities, filters, mode],
  );
  const changed = filterChanges(filters, defaults);
  const openDistrictList = (d) => {
    onFiltersChange({ ...filters, districts: d == null ? [] : [d] });
    onTab("list");
  };

  return (
    <div className="print-release flex h-dvh flex-col bg-paper">
      <a href="#workspace" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[90] focus:bg-ink focus:px-3 focus:py-2 focus:text-[13px] focus:text-paper">
        Skip to the {tab === "map" ? "map" : tab === "summary" ? "summary" : "list"}
      </a>

      <Header facilities={facilities} onSelect={onSelect} onHome={onHome} onNavigate={onNavigate} />
      <StaffBanner fixed />
      <ExpiryBanner fixed />

      <div className="print-hide flex shrink-0 flex-wrap items-end gap-x-5 border-b border-rule-strong bg-paper px-4 lg:px-5">
        <button
          type="button"
          onClick={() => setRailOpen((o) => !o)}
          aria-expanded={railOpen}
          aria-controls="filter-rail"
          className="my-1.5 self-center border border-rule-strong px-3 py-1.5 text-[13px] font-medium text-ink hover:border-ink xl:hidden"
        >
          Filters{changed > 0 && <span className="tnum ml-1.5 bg-ink px-1.5 text-[12px] text-paper">{changed}</span>}
        </button>
        <nav aria-label="Views" className="-mb-px flex">
          {STAFF_TABS.map((t) => {
            const on = t.key === tab;
            return (
              <a
                key={t.key}
                href={t.path}
                aria-current={on ? "page" : undefined}
                onClick={(e) => {
                  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                  e.preventDefault();
                  onTab(t.key);
                }}
                className={`flex items-center border-b-2 px-4 pb-2.5 pt-3 text-[14px] ${on ? "border-ink font-semibold text-ink" : "border-transparent text-ink-2 hover:border-rule-strong hover:text-ink"}`}
              >
                {t.label}
                {t.key === "list" && (
                  <span className="tnum ml-2 bg-paper-edge px-1.5 py-0.5 text-[12px] font-normal text-ink-2" aria-label={`${count.toLocaleString()} places`}>
                    {count.toLocaleString()}
                  </span>
                )}
              </a>
            );
          })}
        </nav>
        <p className="ml-auto self-center py-2 text-[12.5px] text-ink-2">
          {[
            meta?.inspections_through && `Inspections through ${fmtDate(meta.inspections_through)}`,
            meta?.generated && `list drawn up ${fmtDate(meta.generated)}`,
            meta?.expires && `shown until ${fmtDate(meta.expires)}`,
          ].filter(Boolean).join(" · ")}
        </p>
      </div>

      <main className="print-release relative flex min-h-0 flex-1 overflow-hidden">
        {railOpen && (
          <button type="button" aria-label="Close the filters" onClick={() => setRailOpen(false)} className="print-hide absolute inset-0 z-30 bg-ink/20 xl:hidden" />
        )}
        <aside
          id="filter-rail"
          aria-label="Filters"
          className={`print-hide w-[17rem] shrink-0 overflow-y-auto border-r border-rule-strong bg-paper ${railOpen ? "absolute inset-y-0 left-0 z-40 shadow-paper" : "hidden"} xl:static xl:z-auto xl:block xl:shadow-none`}
        >
          <FilterRail
            facilities={facilities}
            filters={filters}
            defaults={defaults}
            changed={changed}
            onFiltersChange={onFiltersChange}
            hasCounty={hasCounty}
            onPoint={onPoint}
            onSelect={onSelect}
          />
        </aside>

        <div id="workspace" tabIndex={-1} className="print-release relative min-w-0 flex-1 focus:outline-none">
          {tab === "list" && (
            <PlaceTable inline facilities={facilities} filters={filters} onSelect={onSelect} selectedId={selected?.properties?.facility_id ?? null} />
          )}
          {mapSeen && (
            <div className={tab === "map" ? "print-hide absolute inset-0" : "hidden"}>
              <MapView facilities={facilities} filters={filters} selected={selected} onSelect={onSelect} pointOverlay={pointOverlay} onError={onMapError} onShowList={() => onTab("list")} />
            </div>
          )}
          {tab === "summary" && <StaffSummary facilities={facilities} filters={filters} onFiltersChange={onFiltersChange} onOpenList={openDistrictList} />}
          <PlacePanel feature={selected} onClose={() => onSelect(null)} facilities={facilities} onSelect={onSelect} onNavigate={onNavigate} />
        </div>
      </main>

      <Notice placement="fixed" onNavigate={onNavigate} />
    </div>
  );
}

/** How many filters differ from the view's defaults (the area switch is not a filter here). */
export function filterChanges(filters, defaults) {
  if (!filters || !defaults) return 0;
  return (filters.band !== defaults.band ? 1 : 0)
    + (filters.districts?.length ? 1 : 0)
    + (filters.types?.length ? 1 : 0)
    + (filters.flag ? 1 : 0);
}

/** The filters for every view: the district, then the bands, kinds and facts, then an address. */
function FilterRail({ facilities, filters, defaults, changed, onFiltersChange, hasCounty, onPoint, onSelect }) {
  return (
    <div className="flex flex-col pb-6">
      <div className="flex items-baseline justify-between gap-3 px-5 pt-4">
        <h2 className="label">Filters</h2>
        {changed > 0 && (
          <button
            type="button"
            onClick={() => onFiltersChange({ ...defaults, county: filters.county })}
            className="border-b border-ink/25 text-[12.5px] text-ink-2 hover:border-ink hover:text-ink"
          >
            Clear {changed === 1 ? "the filter" : `all ${changed}`}
          </button>
        )}
      </div>
      <DistrictPicker rail filters={filters} onFiltersChange={onFiltersChange} />
      <hr className="rule" />
      <FilterBar compact filters={filters} onFiltersChange={onFiltersChange} facilities={facilities} hasCounty={hasCounty} />
      <hr className="rule" />
      <details className="group px-5 py-4">
        <summary className="label cursor-pointer list-none [&::-webkit-details-marker]:hidden">
          <span className="inline-flex items-center gap-1.5">
            Near an address
            <svg width="10" height="6" viewBox="0 0 10 6" aria-hidden="true" className="group-open:rotate-180">
              <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </span>
        </summary>
        <p className="mb-2 mt-2 text-[12px] text-ink-2">Listed places within 500 m, among those the filters leave.</p>
        <NearPanel compact facilities={facilities} filters={filters} onPoint={onPoint} onSelect={onSelect} />
      </details>
    </div>
  );
}

/**
 * What the list is and how fresh (the text the public site's sidebar opens with), the bands in the
 * backtest, and the district view with what to do: its "list" opens the List view for that district.
 */
function StaffSummary({ facilities, filters, onFiltersChange, onOpenList }) {
  const meta = useMeta();
  const mode = useMode();
  return (
    <div className="print-release h-full overflow-y-auto">
      <div className="mx-auto grid max-w-[80rem] gap-x-10 gap-y-2 px-1 py-2 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <section aria-label="By council district">
          <DistrictSummary facilities={facilities} filters={filters} onFiltersChange={onFiltersChange} onOpenList={onOpenList} />
        </section>
        <section aria-label="What this list is" className="px-6 py-5 lg:px-0">
          <p className="label mb-3">What this shows</p>
          <h2 className="font-serif text-[22px] font-medium leading-[1.2] tracking-[-0.01em] text-ink">{headline(meta, facilities?.features)}</h2>
          <p className="mt-3 text-[14px] leading-[1.55] text-ink-2">{subhead(meta)}</p>
          <p className="mt-2.5 text-[13px] leading-[1.5] text-ink-2">{gradeContextSentence(meta)}</p>
          {mode === "bands" && bandDefs(meta).length > 0 && (
            <div className="-mx-6 mt-3 lg:mx-0 [&>div]:lg:px-0">
              <BandTable meta={meta} />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

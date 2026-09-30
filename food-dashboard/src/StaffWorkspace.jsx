import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { CloseButton } from "./Dialog";
import { BandTable, DistrictPicker } from "./Sidebar";
import useMediaQuery from "./useMediaQuery";
import { useMeta, useMode } from "./useMeta";
import { passesFilters } from "./lib/filters";
import { fmtDate } from "./lib/dates";
import { headline, subhead, gradeContextSentence } from "./lib/framing";
import { bandDefs } from "./lib/bands";
import { placeKey } from "./lib/links";

/** The staff site's three views, each at its own address. */
export const STAFF_TABS = [
  { key: "list", label: "List", path: "/" },
  { key: "map", label: "Map", path: "/map" },
  { key: "summary", label: "Summary", path: "/summary" },
];

// From this width the filter rail stands beside the views; under it, it is an overlay behind "Filters".
const WIDE = "(min-width: 1280px)";

/** Each view's heading: read by screen readers, and where focus goes when a change of view leaves it nowhere. */
const VIEW_HEADING = { list: "List of places", map: "Map of places", summary: "Summary of the list" };

/**
 * The staff site on a screen 768px or wider: the masthead, the one-line staff notice, then three views
 * of the same filtered places, each at its own address. List (`/`, the default) is the whole list,
 * full width, with the name filter, sorting, the printout and the CSV; it stays mounted while another
 * view shows, so its search, sort, page and scroll are there on the way back. Map (`/map`) draws the
 * same places. Summary (`/summary`) holds what the list is, the bands in the backtest and the district
 * view with what to do. The filters sit in a rail on the left and apply to every view; under 1280px
 * the rail is an overlay behind a button, which holds focus (the rest of the page is inert) until
 * Escape, its close button or the backdrop closes it, and focus then goes back to the button. A place
 * opens in the panel on the right from any view: on the List from 1024px it stands beside the list,
 * which folds its last two columns; elsewhere it lies over the view. Each view has one heading (for
 * screen readers); a change of view is announced, and when it leaves focus nowhere (the control that
 * made it was in the view just hidden) focus goes to that heading. The map loads the first time it is
 * shown and is kept after, so going back to it does not redraw it. While the list loads (`loading`),
 * the rail and the view are grey bars under the real masthead and notice.
 */
export default function StaffWorkspace({
  facilities,
  loading = false,
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

  // The rail as an overlay (under 1280px only): open, it takes focus and the rest of the page is inert.
  const wide = useMediaQuery(WIDE);
  // From lg the place panel docks beside the list; under it the panel covers the list, which then sits
  // out of the tab order (inert) so focus never lands on a control hidden under the panel.
  const docks = useMediaQuery("(min-width: 1024px)");
  const [railOpen, setRailOpen] = useState(false);
  const overlay = railOpen && !wide;
  const filtersButton = useRef(null);
  const railHeading = useRef(null);
  const backToFilters = useRef(false);
  const closeRail = (refocus = true) => {
    backToFilters.current = refocus;
    setRailOpen(false);
  };
  useEffect(() => { setRailOpen(false); }, [tab]);
  useEffect(() => { if (wide) setRailOpen(false); }, [wide]);
  // Focus moves once the page's inert has been set or lifted: into the rail on open; on close, to
  // "Filters", unless a place chosen in the rail took it (its panel's heading) or the rail now stands
  // beside the views (the window widened) with focus still in it.
  const wasOverlay = useRef(false);
  useEffect(() => {
    const was = wasOverlay.current;
    wasOverlay.current = overlay;
    if (overlay) {
      railHeading.current?.focus({ preventScroll: true });
      return;
    }
    if (!was) return;
    const back = backToFilters.current;
    backToFilters.current = false;
    const a = document.activeElement;
    const lost = !a || a === document.body || !a.isConnected || a.getClientRects().length === 0;
    if (back || lost) filtersButton.current?.focus({ preventScroll: true });
  }, [overlay]);
  // Escape closes the overlay and only it: in the capture phase, before the open place's own Escape. An open
  // list of address suggestions closes first, on its own Escape (the rail stops that one going further).
  useEffect(() => {
    if (!overlay) return undefined;
    const onKey = (e) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      if (e.target?.closest?.('[role="combobox"][aria-expanded="true"]')) return;
      e.preventDefault();
      e.stopPropagation();
      closeRail();
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [overlay]);

  const count = useMemo(
    () => (facilities ? facilities.features.filter((f) => passesFilters(f.properties, filters, { mode })).length : 0),
    [facilities, filters, mode],
  );
  const changed = filterChanges(filters, defaults);
  const openDistrictList = (d) => {
    onFiltersChange({ ...filters, districts: d == null ? [] : [d] });
    onTab("list");
  };
  const closePlace = useCallback(() => onSelect(null), [onSelect]);
  // A place chosen in the overlay's address check closes the overlay, so the place's panel can take focus.
  const selectFromRail = (f) => {
    if (overlay) closeRail(false);
    onSelect(f);
  };

  // A change of view: announced, or, when it left focus nowhere, focus goes to the new view's heading.
  const viewHeading = useRef(null);
  const shownTab = useRef(tab);
  const [announce, setAnnounce] = useState("");
  useEffect(() => {
    if (shownTab.current === tab) return;
    shownTab.current = tab;
    const a = document.activeElement;
    const lost = !a || a === document.body || !a.isConnected || a.getClientRects().length === 0;
    if (lost) {
      viewHeading.current?.focus({ preventScroll: true });
      setAnnounce("");
    } else {
      const label = STAFF_TABS.find((t) => t.key === tab)?.label ?? "List";
      // The map shows the filtered places; the list's own count (its search included) speaks for the list.
      setAnnounce(tab === "map" ? `${label} view, ${count.toLocaleString()} ${count === 1 ? "place" : "places"}` : `${label} view`);
    }
  }, [tab]);

  // Each view's link carries the open place and the district, so opening it in a new tab keeps them.
  const query = new URLSearchParams();
  if (selected) query.set("place", placeKey(selected.properties));
  if (filters.districts?.length === 1) query.set("district", String(filters.districts[0]));
  const search = query.toString() ? `?${query}` : "";
  const inert = overlay ? "" : undefined;

  return (
    <div className="print-release flex h-dvh flex-col bg-paper">
      {/* Inert while the rail is an overlay, as #workspace and the footer are: Tab and a screen reader stay in the rail. */}
      <div className="contents" inert={inert}>
        <a
          href="#view-heading"
          onClick={(e) => { e.preventDefault(); viewHeading.current?.focus(); }}
          className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[90] focus:bg-ink focus:px-3 focus:py-2 focus:text-[13px] focus:text-paper">
          Skip to the {tab === "map" ? "map" : tab === "summary" ? "summary" : "list"}
        </a>

        <Header facilities={facilities} onSelect={onSelect} onHome={onHome} onNavigate={onNavigate} />
        <StaffBanner fixed />
        <ExpiryBanner fixed />

        <div className="print-hide flex shrink-0 flex-wrap items-end gap-x-5 border-b border-rule-strong bg-paper px-4 lg:px-5">
          <button
            ref={filtersButton}
            type="button"
            onClick={() => (railOpen ? closeRail() : setRailOpen(true))}
            disabled={loading}
            aria-expanded={overlay}
            aria-controls="filter-rail"
            className="group my-1.5 self-center border border-rule-strong px-3 py-1.5 text-[13px] font-medium text-ink hover:border-ink disabled:opacity-40 aria-expanded:border-ink aria-expanded:bg-ink aria-expanded:text-paper xl:hidden"
          >
            Filters
            {changed > 0 && (
              <>
                <span aria-hidden="true" className="tnum ml-1.5 bg-ink px-1.5 text-[12px] text-paper group-aria-expanded:bg-paper group-aria-expanded:text-ink">{changed}</span>
                <span className="sr-only">, {changed} changed</span>
              </>
            )}
          </button>
          <nav aria-label="Views" className="-mb-px flex">
            {STAFF_TABS.map((t) => {
              const on = t.key === tab;
              return (
                <a
                  key={t.key}
                  href={`${t.path}${search}`}
                  aria-current={on ? "page" : undefined}
                  onClick={(e) => {
                    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                    e.preventDefault();
                    onTab(t.key);
                  }}
                  className={`flex items-center border-b-2 px-4 pb-2.5 pt-3 text-[14px] ${on ? "border-ink font-semibold text-ink" : "border-transparent text-ink-2 hover:border-rule-strong hover:text-ink"}`}
                >
                  {t.label}
                  {t.key === "list" && (loading
                    ? <span aria-hidden="true" className="ml-2 inline-block h-3 w-10 animate-pulse bg-paper-edge" />
                    : (
                      <>
                        <span aria-hidden="true" className="tnum ml-2 bg-paper-edge px-1.5 py-0.5 text-[12px] font-normal text-ink-2">
                          {count.toLocaleString()}
                        </span>
                        <span className="sr-only">, {count.toLocaleString()} {count === 1 ? "place" : "places"}</span>
                      </>
                    ))}
                </a>
              );
            })}
          </nav>
          {/* Short, so it stays on the tabs' line where there is room, and wraps under them where there is not. */}
          <p className="ml-auto self-center py-2 text-[12.5px] text-ink-2">
            {[
              meta?.inspections_through && `Inspections through ${shortDay(meta.inspections_through)}`,
              meta?.generated && `drawn up ${shortDay(meta.generated)}`,
              meta?.expires && `shown until ${shortDay(meta.expires, true)}`,
            ].filter(Boolean).join(" · ")}
          </p>
        </div>
      </div>

      {/* Mounted from the first render and empty until a view changes, so the change is read out. */}
      <p className="sr-only" role="status">{announce}</p>

      <main className="print-release relative flex min-h-0 flex-1 overflow-hidden" aria-busy={loading || undefined}>
        {overlay && (
          // Not a tab stop: the rail's own close button and Escape are the keyboard's way out.
          <div aria-hidden="true" onMouseDown={(e) => { e.preventDefault(); closeRail(); }} className="print-hide fixed inset-0 z-[35] bg-ink/20" />
        )}
        <aside
          id="filter-rail"
          {...(overlay ? { role: "dialog", "aria-modal": "true", "aria-labelledby": "filter-rail-heading" } : { "aria-label": "Filters" })}
          onKeyDown={overlay ? (e) => { if (e.key === "Escape") e.stopPropagation(); } : undefined}
          className={`print-hide w-[17rem] shrink-0 overflow-y-auto border-r border-rule-strong bg-paper ${railOpen ? "absolute inset-y-0 left-0 z-40 shadow-paper" : "hidden"} xl:static xl:z-auto xl:block xl:shadow-none`}
        >
          {loading ? <RailSkeleton /> : (
            <FilterRail
              facilities={facilities}
              filters={filters}
              defaults={defaults}
              changed={changed}
              onFiltersChange={onFiltersChange}
              hasCounty={hasCounty}
              onPoint={onPoint}
              onSelect={selectFromRail}
              headingRef={railHeading}
              onClose={overlay ? () => closeRail() : null}
            />
          )}
        </aside>

        <div id="workspace" tabIndex={-1} inert={inert} className="print-release relative flex min-w-0 flex-1 focus:outline-none">
          {/* Seen while it has focus (after a view change or a skip), so a sighted keyboard user sees where focus is. */}
          <h1
            id="view-heading"
            ref={viewHeading}
            tabIndex={-1}
            className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-2 focus:z-40 focus:bg-paper focus:px-2 focus:py-1 focus:text-[13px] focus:font-semibold focus:text-ink focus:outline focus:outline-2 focus:outline-ink"
          >
            {VIEW_HEADING[tab] ?? VIEW_HEADING.list}
          </h1>
          {loading ? (
            <>
              <p className="sr-only" role="status">Loading the list</p>
              <ViewSkeleton tab={tab} />
            </>
          ) : (
            <>
              <div className={tab === "list" ? "print-release h-full min-w-0 flex-1" : "hidden"} inert={tab === "list" && selected && !docks ? "" : undefined}>
                <PlaceTable
                  inline
                  active={tab === "list"}
                  beside={tab === "list" && Boolean(selected)}
                  facilities={facilities}
                  filters={filters}
                  onSelect={onSelect}
                  selectedId={selected?.properties?.facility_id ?? null}
                  onShowSummary={() => onTab("summary")}
                />
              </div>
              {mapSeen && (
                <div className={tab === "map" ? "print-hide absolute inset-0" : "hidden"}>
                  <MapView facilities={facilities} filters={filters} selected={selected} onSelect={onSelect} pointOverlay={pointOverlay} onError={onMapError} onShowList={() => onTab("list")} />
                </div>
              )}
              {tab === "summary" && <StaffSummary facilities={facilities} filters={filters} onFiltersChange={onFiltersChange} onOpenList={openDistrictList} />}
              <PlacePanel
                feature={selected}
                docked={tab === "list"}
                returnFocusTo="view-heading"
                onClose={closePlace}
                facilities={facilities}
                onSelect={onSelect}
                onNavigate={onNavigate}
              />
            </>
          )}
        </div>
      </main>

      <div className="contents" inert={inert}>
        <Notice placement="footer" onNavigate={onNavigate} />
      </div>
    </div>
  );
}

/** "2026-09-29" -> "Sep 29", or with the year "Sep 29, 2026": the short dates beside the views. */
function shortDay(iso, withYear = false) {
  const m = /^([A-Z][a-z]{2})[a-z]* (\d{1,2}), (\d{4})$/.exec(fmtDate(iso));
  return m ? `${m[1]} ${m[2]}${withYear ? `, ${m[3]}` : ""}` : fmtDate(iso);
}

/** How many filters differ from the view's defaults (the area switch is not a filter here). */
export function filterChanges(filters, defaults) {
  if (!filters || !defaults) return 0;
  return (filters.band !== defaults.band ? 1 : 0)
    + (filters.districts?.length ? 1 : 0)
    + (filters.types?.length ? 1 : 0)
    + (filters.flag ? 1 : 0);
}

/**
 * The filters for every view: the district, then an address, then the bands, kinds and facts. Its
 * heading takes focus when the rail opens as an overlay, and `onClose` (the overlay only) adds a
 * close button beside it.
 */
function FilterRail({ facilities, filters, defaults, changed, onFiltersChange, hasCounty, onPoint, onSelect, headingRef, onClose }) {
  return (
    <div className="flex flex-col pb-6">
      <div className="flex min-h-[2.75rem] items-center justify-between gap-3 px-5 pt-4">
        <h2 id="filter-rail-heading" ref={headingRef} tabIndex={-1} className="label focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink">Filters</h2>
        <span className="flex items-center gap-3">
          {changed > 0 && (
            <button
              type="button"
              onClick={() => onFiltersChange({ ...defaults, county: filters.county })}
              className="border-b border-ink/25 text-[12.5px] text-ink-2 hover:border-ink hover:text-ink"
            >
              Clear {changed === 1 ? "the filter" : `all ${changed} filters`}
            </button>
          )}
          {onClose && <CloseButton onClose={onClose} label="Close the filters" />}
        </span>
      </div>
      <DistrictPicker rail filters={filters} onFiltersChange={onFiltersChange} />
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
      <hr className="rule" />
      <FilterBar compact filters={filters} onFiltersChange={onFiltersChange} facilities={facilities} hasCounty={hasCounty} />
    </div>
  );
}

/** A grey bar of a skeleton. */
const bar = (w, h = "h-3") => <div className={`${h} ${w} animate-pulse bg-paper-edge`} />;

/** The rail while the list loads: grey bars where the filters will be. */
export function RailSkeleton() {
  return (
    <div className="space-y-4 px-5 py-4" aria-hidden="true">
      {bar("w-16", "h-2.5")}
      <div className="pt-2">{bar("w-28", "h-2")}</div>
      {bar("w-full", "h-9")}
      <div className="pt-3">{bar("w-24", "h-2")}</div>
      {bar("w-5/6")}
      {bar("w-2/3")}
      <div className="pt-3">{bar("w-20", "h-2")}</div>
      {bar("w-full", "h-6")}
      {bar("w-11/12", "h-6")}
      {bar("w-3/4", "h-6")}
    </div>
  );
}

/** The view while the list loads: the list's toolbar and rows in grey, the map's ground, or the summary's two columns. */
export function ViewSkeleton({ tab }) {
  if (tab === "map") return <div className="h-full min-w-0 flex-1 bg-paper-sunk" aria-hidden="true" />;
  if (tab === "summary") {
    return (
      <div className="h-full min-w-0 flex-1" aria-hidden="true">
        <div className="mx-auto grid max-w-[80rem] gap-x-10 gap-y-6 px-7 py-7 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div className="space-y-3">
            {bar("w-40", "h-2.5")}
            {bar("w-full", "h-20")}
            {Array.from({ length: 9 }, (_, i) => <div key={i}>{bar("w-full", "h-5")}</div>)}
          </div>
          <div className="space-y-3">
            {bar("w-28", "h-2.5")}
            {bar("w-11/12", "h-6")}
            {bar("w-4/5", "h-6")}
            {bar("w-full")}
            {bar("w-5/6")}
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="flex h-full min-w-0 flex-1 flex-col" aria-hidden="true">
      <div className="flex shrink-0 items-center gap-3 border-b border-rule px-5 py-2.5">
        {bar("w-full max-w-md", "h-8")}
      </div>
      <div className="space-y-6 px-5 py-5">
        {Array.from({ length: 9 }, (_, i) => (
          <div key={i} className="flex items-start gap-6">
            {bar("w-10")}
            <div className="w-1/3 space-y-2">{bar("w-full")}{bar("w-2/3", "h-2")}</div>
            {bar("w-8")}
            {bar("w-14")}
          </div>
        ))}
      </div>
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
    <div className="print-release h-full min-w-0 flex-1 overflow-y-auto">
      <div className="mx-auto grid max-w-[80rem] gap-x-10 gap-y-2 px-1 py-2 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <section aria-label="By council district">
          <DistrictSummary facilities={facilities} filters={filters} onFiltersChange={onFiltersChange} onOpenList={onOpenList} />
        </section>
        {/* Its right padding is the left column's (DistrictSummary's px-6), so both outer gutters match. */}
        <section aria-label="What this list is" className="px-6 py-5 lg:pl-0">
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

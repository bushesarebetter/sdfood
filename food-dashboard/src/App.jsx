import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import Header from "./Header";
import Sidebar from "./Sidebar";
import MapView from "./MapView";
import PlaceTable from "./PlaceTable";
import PlacePanel from "./PlacePanel";
import PlaceCard from "./PlaceCard";
import WelcomeModal from "./WelcomeModal";
import MobileShell from "./MobileShell";
import Landing from "./Landing";
import ExpiredView from "./ExpiredView";
import Privacy from "./Privacy";
import Corrections from "./Corrections";
import NotFound from "./NotFound";
import Notice from "./Notice";
import SampleBanner from "./SampleBanner";
import StaffBanner, { PrintAudit } from "./StaffBanner";
import StaffWorkspace, { STAFF_TABS } from "./StaffWorkspace";
import ExpiryBanner from "./ExpiryBanner";
import { inArea, hasCountyPlaces } from "./AreaToggle";
import useFacilities from "./useFacilities";
import useMediaQuery from "./useMediaQuery";
import usePageMeta from "./usePageMeta";
import { readPlaceFromUrl, writePlaceToUrl, readDistrictFromUrl, writeDistrictToUrl } from "./useDeepLink";
import { AdvancedProvider, useAdvanced } from "./useAdvanced";
import { MetaProvider, useMetaFetch, useExpired, useMeta, useMode } from "./useMeta";
import { findPlace, parsePlacePath, placeKey } from "./lib/links";
import { siteDescription } from "./lib/framing";
import { shownBand } from "./lib/marks";
import { isStaff } from "./lib/staff";
import { DEFAULT_BAND, ALL_PLACES } from "./constants";
import { SITE } from "./site";

const PHONE = "(max-width: 767px)";
// The public site opens on the bands; the staff site on every listed place.
const defaultFilters = (mode, staff = false) => ({ band: mode === "bands" && !staff ? DEFAULT_BAND : ALL_PLACES, districts: [], types: [], flag: null, county: false });

/**
 * Six views, no router. `/` the front page, `/map` the map and list,
 * `/place/<facility_id>` one place as a page, `/privacy`, `/corrections`, and
 * anything else a 404. `/map?place=<facility_id>` opens that place on the map;
 * `?list` opens the list, whenever the address changes to it (the app's own
 * navigation or the back button), not only on the first load. On the staff
 * site the map view is three views of the same filtered places (`tab`,
 * StaffWorkspace): `/` the full list of every listed place (and `/map?list`),
 * `/map` the map, `/summary` the district view and the bands. Nothing
 * renders until meta.json has loaded, so no page shows one mode and then
 * another. Once the export has expired, the front page and the map are a
 * notice and a search.
 */
let locationSeq = 0;
function viewFromLocation(staff = false) {
  const key = ++locationSeq;          // a new key for every read, so asking for the list again opens it again
  if (typeof window === "undefined") return { view: "landing", place: null, list: false, key, tab: null };
  const { pathname, search } = window.location;
  const q = new URLSearchParams(search);
  const list = q.has("list");
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/map") return { view: "map", place: null, list, key, tab: staff ? (list ? "list" : "map") : null };
  if (path === "/") {
    if (staff) return { view: "map", place: null, list: true, key, tab: "list" };
    return { view: q.has("place") || q.has("district") || list ? "map" : "landing", place: null, list, key, tab: null };
  }
  if (staff && path === "/summary") return { view: "map", place: null, list: false, key, tab: "summary" };
  if (path === "/privacy") return { view: "privacy", place: null, list: false, key };
  if (path === "/corrections") return { view: "corrections", place: null, list: false, key };
  const placeKeyInPath = parsePlacePath(path);
  if (placeKeyInPath != null) return { view: "place", place: placeKeyInPath, list: false, key };
  return { view: "notfound", place: null, list: false, key };
}

export default function App() {
  const { meta, status, retry } = useMetaFetch();
  return (
    <AdvancedProvider>
      <MetaProvider meta={meta}>
        {/* The staff site's print log, once for every view and layout (the phone shell included). */}
        <PrintAudit />
        {status === "loading" ? <LoadingShell /> : status === "error" ? <MetaError onRetry={retry} /> : <Dashboard />}
      </MetaProvider>
    </AdvancedProvider>
  );
}

function Dashboard() {
  const { facilities, loading, error, retry } = useFacilities();
  const { dismissWelcome } = useAdvanced();
  const meta = useMeta();
  const mode = useMode();
  const expired = useExpired();
  const staff = isStaff(meta);
  const [selected, setSelected] = useState(null);
  const [filters, setFilters] = useState(() => {
    const d = readDistrictFromUrl();
    return { ...defaultFilters(mode, staff), ...(d ? { districts: [d] } : {}) };
  });
  const [loc, setLocation] = useState(() => viewFromLocation(staff));
  const { view, place } = loc;
  // Follows the address: a new key each time it asks for the list, so the list opens on every visit to ?list.
  const listKey = loc.list ? loc.key : null;
  const [pointOverlay, setPointOverlay] = useState(null);
  const [mapError, setMapError] = useState(null);
  const isPhone = useMediaQuery(PHONE);
  // The City by default; the rest of the county on request. A place page always reads the full list.
  const hasCounty = useMemo(() => hasCountyPlaces(facilities), [facilities]);
  const shown = useMemo(() => inArea(facilities, filters.county || !hasCounty), [facilities, filters.county, hasCounty]);
  const setCounty = useCallback((county) => setFilters((f) => ({ ...f, county })), []);

  // Deep link in, read once the index is here.
  const initialPlace = useRef(readPlaceFromUrl());
  useEffect(() => {
    if (!facilities || initialPlace.current == null) return;
    const wanted = initialPlace.current;
    initialPlace.current = null;
    const feature = findPlace(facilities.features, wanted);
    if (feature) setSelected(feature);
  }, [facilities]);

  // Deep link out: the address bar is the share link, keyed on facility_id.
  useEffect(() => {
    if (initialPlace.current != null || view !== "map") return;
    writePlaceToUrl(selected ? placeKey(selected.properties) : null);
  }, [selected, view]);

  useEffect(() => {
    if (view !== "map") return;
    writeDistrictToUrl(filters.districts.length === 1 ? filters.districts[0] : null);
  }, [filters.districts, view]);

  useEffect(() => {
    const onPop = () => {
      setLocation(viewFromLocation(staff));
      const d = readDistrictFromUrl();
      if (d) setFilters((f) => ({ ...f, districts: [d] }));
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [staff]);

  const navigate = useCallback((path, { place: wantedPlace = null, list = false } = {}) => {
    const url = new URL(path, window.location.origin);
    if (wantedPlace) url.searchParams.set("place", String(wantedPlace));
    if (list) url.searchParams.set("list", "1");
    window.history.pushState(null, "", url);
    window.scrollTo(0, 0);
    const next = viewFromLocation(staff);
    setLocation(next);
    const wanted = url.searchParams.get("place");
    if (next.view === "map" && wanted && facilities) {
      const feature = findPlace(facilities.features, wanted);
      if (feature) setSelected(feature);
    }
  }, [facilities, staff]);

  const enterMap = useCallback((feature = null, { list = false } = {}) => {
    navigate("/map", { place: feature ? placeKey(feature.properties) : null, list });
    if (feature) setSelected(feature);
    dismissWelcome();
  }, [navigate, dismissWelcome]);

  const goHome = useCallback(() => {
    setSelected(null);
    navigate("/");
  }, [navigate]);

  // The staff site's views: the same place and district in the address, another path.
  const goTab = useCallback((t) => {
    const target = STAFF_TABS.find((x) => x.key === t) ?? STAFF_TABS[0];
    const url = new URL(window.location.href);
    url.pathname = target.path;
    url.searchParams.delete("list");
    window.history.pushState(null, "", url);
    setLocation(viewFromLocation(staff));
  }, [staff]);

  // A district's "list" action: that district, and the list open.
  const openList = useCallback((d = null) => {
    setFilters((f) => ({ ...f, districts: d == null ? [] : [d] }));
    navigate("/map", { list: true, place: selected ? placeKey(selected.properties) : null });
  }, [navigate, selected]);
  const setDistricts = useCallback((districts) => setFilters((f) => ({ ...f, districts })), []);

  const sel = selected?.properties;
  const pageFeature = view === "place" ? findPlace(facilities?.features, place) : null;
  const selBand = sel && !expired ? shownBand(sel, { mode }) : null;
  usePageMeta({
    title:
      view === "map" ? (sel ? sel.name : staff ? STAFF_TABS.find((t) => t.key === loc.tab)?.label ?? "List" : "Map")
        : view === "privacy" ? "Privacy, terms and corrections"
        : view === "corrections" ? "Corrections log"
        : view === "place" ? pageFeature?.properties.name ?? "A place"
        : view === "notfound" ? "Page not found"
        : null,
    description:
      (view === "map" && sel) || (view === "place" && pageFeature)
        ? (() => {
            const p = sel && view === "map" ? sel : pageFeature.properties;
            const b = view === "map" ? selBand : !expired ? shownBand(p, { mode }) : null;
            return `${p.name}, ${p.address}${b ? `, band ${b} on the students' point rule` : ""}: its County inspection record, visit by visit.`;
          })()
        : siteDescription(meta),
    noindex: view === "place" || view === "notfound" || (view === "map" && Boolean(sel)),
  });

  if (view === "privacy") return <Privacy onNavigate={navigate} />;
  if (view === "corrections") return <Corrections facilities={facilities} onNavigate={navigate} />;
  if (view === "notfound") return <NotFound onNavigate={navigate} />;
  if (view === "place") return <PlaceCard placeKey={place} facilities={facilities} error={error} onRetry={retry} onNavigate={navigate} />;

  if (expired) return <ExpiredView facilities={facilities} error={error} onNavigate={navigate} />;

  if (view === "landing") {
    return (
      <Landing
        facilities={shown}
        error={error}
        onRetry={retry}
        onEnter={enterMap}
        onNavigate={navigate}
        notice={<Notice placement="inline" onNavigate={navigate} />}
      />
    );
  }

  if (loading) return <LoadingShell isPhone={isPhone} />;

  if (error) {
    return (
      <div className="flex h-dvh items-center justify-center bg-paper p-8">
        <div role="alert" className="max-w-sm border border-rule-strong bg-paper-sunk px-6 py-5">
          <p className="label mb-2">The list did not load</p>
          <p className="font-serif text-[15px] leading-relaxed text-ink-2">{error}</p>
          <p className="mt-4 flex flex-wrap gap-4 text-[14px]">
            <button onClick={retry} className="bg-ink px-4 py-2 font-semibold text-paper hover:bg-ink-2">Try again</button>
            <a href={SITE.regulator.resultsUrl} target="_blank" rel="noopener noreferrer" className="self-center border-b border-ink/25 text-ink hover:border-ink">The County&rsquo;s inspection search</a>
          </p>
        </div>
      </div>
    );
  }

  if (isPhone) {
    return (
      <>
        {/* On the staff site the notice opens by itself instead (StaffBanner). */}
        {!staff && <WelcomeModal />}
        <MobileShell
          facilities={shown}
          filters={{ ...defaultFilters(mode, staff), county: filters.county, districts: filters.districts }}
          hasCounty={hasCounty}
          onCountyChange={setCounty}
          onDistrictsChange={staff ? setDistricts : null}
          listKey={listKey}
          selected={selected}
          onSelect={setSelected}
          pointOverlay={pointOverlay}
          onPoint={setPointOverlay}
          onNavigate={navigate}
        />
        <Notice placement="fixed" onNavigate={navigate} />
      </>
    );
  }

  if (staff) {
    return (
      <StaffWorkspace
        facilities={shown}
        filters={filters}
        defaults={{ ...defaultFilters(mode, staff), county: filters.county }}
        onFiltersChange={setFilters}
        hasCounty={hasCounty}
        selected={selected}
        onSelect={setSelected}
        tab={loc.tab ?? "list"}
        onTab={goTab}
        pointOverlay={pointOverlay}
        onPoint={setPointOverlay}
        onMapError={setMapError}
        onHome={goHome}
        onNavigate={navigate}
      />
    );
  }

  // In print the page is released from the screen's one-viewport frame (print-release, index.css), so
  // the list's printout or a place's sheet flows across pages; the map and the sidebar never print.
  return (
    <div className="print-release flex h-dvh flex-col bg-paper">
      <WelcomeModal />

      <a href="#map-area" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[90] focus:bg-ink focus:px-3 focus:py-2 focus:text-[13px] focus:text-paper">
        Skip to the map and list
      </a>

      <Header facilities={shown} onSelect={setSelected} onHome={goHome} onNavigate={navigate} />
      <SampleBanner fixed />
      <StaffBanner fixed />
      <ExpiryBanner fixed />

      <main className="print-release relative flex flex-1 overflow-hidden">
        <aside aria-label="Filters and summary" className="print-hide w-[20.5rem] shrink-0 border-r border-rule-strong">
          <Sidebar facilities={shown} hasCounty={hasCounty} filters={filters} onFiltersChange={setFilters} onPoint={setPointOverlay} onSelect={setSelected} onOpenList={openList} />
        </aside>

        <div id="map-area" tabIndex={-1} className="print-hide relative min-w-0 flex-1 focus:outline-none">
          <MapView facilities={shown} filters={filters} selected={selected} onSelect={setSelected} pointOverlay={pointOverlay} onError={setMapError} />
        </div>

        {/* Outside the map's print-hide (the drawer is fixed, so where it sits in the tree does not move it):
            its "Print this list" prints every listed row. */}
        <PlaceTable facilities={shown} filters={filters} onSelect={setSelected} openKey={listKey} openWhen={Boolean(mapError)} />

        <PlacePanel feature={selected} onClose={() => setSelected(null)} facilities={shown} onSelect={setSelected} onNavigate={navigate} />
      </main>

      <Notice placement="fixed" onNavigate={navigate} />
    </div>
  );
}

function MetaError({ onRetry }) {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-paper p-8">
      <div role="alert" className="max-w-md border border-rule-strong bg-paper-sunk px-6 py-5">
        <p className="label mb-2">{SITE.siteTitle}</p>
        <p className="font-serif text-[16px] leading-relaxed text-ink">This site&rsquo;s data did not load. Check the connection and try again.</p>
        <p className="mt-4 flex flex-wrap gap-4 text-[14px]">
          <button onClick={onRetry} className="bg-ink px-4 py-2 font-semibold text-paper hover:bg-ink-2">Try again</button>
          <a href={SITE.regulator.resultsUrl} target="_blank" rel="noopener noreferrer" className="self-center border-b border-ink/25 text-ink hover:border-ink">The County&rsquo;s inspection search</a>
        </p>
      </div>
    </div>
  );
}

function LoadingShell({ isPhone = false }) {
  const bar = (w, h = "h-3") => <div className={`${h} ${w} animate-pulse bg-paper-edge`} />;
  return (
    <div className="flex h-dvh flex-col bg-paper" aria-busy="true">
      <p className="sr-only" role="status">Loading</p>
      <div className="flex min-h-[56px] shrink-0 items-center border-b border-rule-strong px-5">{bar("w-36", "h-4")}</div>
      <div className="flex flex-1 overflow-hidden">
        {!isPhone && (
          <div className="hidden w-[20.5rem] shrink-0 space-y-4 border-r border-rule-strong p-6 md:block">
            {bar("w-24", "h-2")}
            {bar("w-full", "h-6")}
            {bar("w-5/6", "h-6")}
            <div className="pt-4">{bar("w-2/3")}</div>
            {bar("w-1/2")}
            <div className="pt-6">{bar("w-1/3", "h-2")}</div>
            {bar("w-full")}
            {bar("w-11/12")}
          </div>
        )}
        <div className="relative flex-1 bg-paper-sunk">
          <p className="label absolute left-5 top-5">Loading</p>
        </div>
      </div>
    </div>
  );
}

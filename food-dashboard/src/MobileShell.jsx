import { useMemo, useState } from "react";
import MapView from "./MapView";
import SearchBox from "./SearchBox";
import MobileSheet from "./MobileSheet";
import AboutModal from "./AboutModal";
import NearPanel from "./NearPanel";
import SampleBanner from "./SampleBanner";
import Dialog, { CloseButton } from "./Dialog";
import { useMode, useExpired } from "./useMeta";
import { passesFilters, sortPlaces } from "./lib/filters";
import { gradeView } from "./lib/grades";
import { typeLabel } from "./lib/inspections";
import { markFor } from "./lib/marks";
import { MAP_UNAVAILABLE } from "./useGoogleMap";

// The sheet occupies the lower half of the screen; push the map so a
// selected dot sits in the visible upper half.
const SHEET_OFFSET_PX = 140;
const LIST_PAGE = 50;

/**
 * Phone layout: the map or the list, a search field, an address check, and
 * a detail sheet on tap. When the map cannot load, the list takes its place.
 */
export default function MobileShell({ facilities, filters, selected, onSelect, pointOverlay, onPoint, onNavigate }) {
  const [aboutOpen, setAboutOpen] = useState(false);
  const [nearOpen, setNearOpen] = useState(false);
  const [view, setView] = useState("map");
  const [mapError, setMapError] = useState(null);
  const showList = view === "list" || Boolean(mapError);

  return (
    <div className="relative h-dvh w-full overflow-hidden bg-paper">
      {!mapError && (
        <div className={showList ? "invisible absolute inset-0" : "absolute inset-0"} aria-hidden={showList}>
          <MapView
            facilities={facilities}
            filters={filters}
            selected={selected}
            onSelect={onSelect}
            showLegend={false}
            selectionOffsetY={SHEET_OFFSET_PX}
            pointOverlay={pointOverlay}
            onError={setMapError}
          />
        </div>
      )}

      <div className="absolute inset-x-3 z-10 space-y-2" style={{ top: "max(12px, env(safe-area-inset-top))" }}>
        <div className="flex items-stretch gap-2">
          <div className="min-w-0 flex-1 shadow-paper">
            <SearchBox facilities={facilities} onSelect={onSelect} />
          </div>
          <IconButton label="Near an address" onClick={() => setNearOpen(true)} active={Boolean(pointOverlay)}>
            <circle cx="9" cy="8" r="3" stroke="currentColor" strokeWidth="1.4" />
            <path d="M9 16c3.5-4 5.5-6.5 5.5-8.5a5.5 5.5 0 0 0-11 0C3.5 9.5 5.5 12 9 16z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
          </IconButton>
          <IconButton label="About this site" onClick={() => setAboutOpen(true)}>
            <circle cx="9" cy="9" r="7.5" stroke="currentColor" strokeWidth="1.4" />
            <path d="M9 8v5M9 5.5h.01" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </IconButton>
        </div>
        <SampleBanner compact />
        {!mapError && (
          <div role="group" aria-label="Show" className="inline-flex border border-rule-strong bg-paper shadow-paper">
            {["map", "list"].map((v) => (
              <button key={v} onClick={() => setView(v)} aria-pressed={view === v} className={`min-h-[36px] px-3 text-[13px] font-medium ${view === v ? "bg-ink text-paper" : "text-ink-2"}`}>
                {v === "map" ? "Map" : "List"}
              </button>
            ))}
          </div>
        )}
      </div>

      {showList && <PlaceList facilities={facilities} filters={filters} onSelect={onSelect} note={mapError ? MAP_UNAVAILABLE : null} />}

      <MobileSheet feature={selected} onClose={() => onSelect(null)} onNavigate={onNavigate} />

      {nearOpen && (
        <Dialog titleId="near-title" onClose={() => setNearOpen(false)} overlayClassName="!p-0" className="min-h-dvh max-w-none border-0" z={60}>
          <div className="flex items-center justify-between border-b border-rule-strong px-5 py-1" style={{ paddingTop: "max(4px, env(safe-area-inset-top))" }}>
            <h2 id="near-title" className="label focus:outline-none">Near an address</h2>
            <CloseButton onClose={() => setNearOpen(false)} />
          </div>
          <div className="px-5 py-4">
            <p className="mb-4 text-[14px] leading-[1.5] text-ink-2">The listed places within 500 m of an address, nearest first.</p>
            <NearPanel compact facilities={facilities} filters={filters} onPoint={onPoint} onSelect={(f) => { onSelect(f); setNearOpen(false); }} />
            {pointOverlay && !mapError && (
              <button onClick={() => { setView("map"); setNearOpen(false); }} className="mt-5 block w-full bg-ink py-3 text-center text-[15px] font-semibold text-paper">
                Show on the map
              </button>
            )}
          </div>
        </Dialog>
      )}

      {aboutOpen && <AboutModal onClose={() => setAboutOpen(false)} onNavigate={onNavigate} />}
    </div>
  );
}

function IconButton({ label, onClick, active = false, children }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`flex h-11 w-11 shrink-0 items-center justify-center border shadow-paper active:bg-paper-edge ${active ? "border-ink bg-ink text-paper" : "border-rule-strong bg-paper text-ink"}`}
    >
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">{children}</svg>
    </button>
  );
}

/** The listed places as a list, in the site's order, for phones and for when the map is not available. */
function PlaceList({ facilities, filters, onSelect, note }) {
  const mode = useMode();
  const expired = useExpired();
  const [shown, setShown] = useState(LIST_PAGE);
  const places = useMemo(
    () => sortPlaces((facilities?.features ?? []).filter((f) => passesFilters(f.properties, filters, { mode })), { mode }),
    [facilities, filters, mode]
  );
  return (
    <div className="absolute inset-0 overflow-y-auto bg-paper px-4 pb-24" style={{ paddingTop: "calc(max(12px, env(safe-area-inset-top)) + 7.5rem)" }}>
      {note && <p role="status" className="mb-3 border border-rule-strong bg-paper-sunk px-3 py-2 text-[14px] text-ink">{note}</p>}
      <p className="mb-2 text-[13px] text-ink-2">{places.length.toLocaleString()} listed {places.length === 1 ? "place" : "places"}{mode === "bands" ? ", by band, then points, then name" : ", by name"}.</p>
      <ul>
        {places.slice(0, shown).map((f) => {
          const p = f.properties;
          const g = gradeView(p.grade);
          const m = markFor(p, { mode });
          return (
            <li key={p.facility_id} className="border-b border-rule">
              <button onClick={() => onSelect(f)} className="block min-h-[48px] w-full py-2.5 text-left active:bg-paper-edge">
                <span className="block text-[15px] leading-snug text-ink">{p.name}</span>
                <span className="block text-[13px] text-ink-2">
                  {!expired && m.label && <span className="font-semibold" style={{ color: m.text ?? undefined }}>{m.label}, </span>}
                  {typeLabel(p.facility_type)}, {g.graded ? `grade ${g.short}` : g.text.toLowerCase()}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {shown < places.length && (
        <button onClick={() => setShown((n) => n + LIST_PAGE)} className="mt-4 w-full border border-ink py-3 text-[14px] font-semibold text-ink">
          Show {Math.min(LIST_PAGE, places.length - shown)} more
        </button>
      )}
    </div>
  );
}

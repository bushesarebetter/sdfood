import { useEffect, useMemo, useRef, useState } from "react";
import { PlaceLines, PlaceStatus, CountyDisclaimer, RecordFactList } from "./PlaceParts";
import usePlace from "./usePlace";
import { useMode, useExpired, useSample } from "./useMeta";
import { typeLabel } from "./lib/inspections";
import { gradeView } from "./lib/grades";
import { recordFacts } from "./lib/recordFacts";
import { mergePlace } from "./lib/placeData";
import { placePath } from "./lib/links";
import { markFor } from "./lib/marks";
import { SITE } from "./site";

// A finger must travel this far downward before a drag counts as a dismiss.
const DISMISS_PX = 64;

/**
 * Phone detail sheet: what the place is, its grade (and band, in `bands`
 * mode), the first facts from the County's record, and a way to the full
 * record. Under half the viewport so the map stays visible above it.
 */
export default function MobileSheet({ feature, onClose, onNavigate }) {
  const [dragY, setDragY] = useState(0);
  const dragging = useRef(false);
  const startY = useRef(0);
  const headingRef = useRef(null);
  const mode = useMode();
  const expired = useExpired();
  const sample = useSample();

  const open = feature !== null;
  const p = feature?.properties ?? {};
  const [lon, lat] = feature?.geometry?.coordinates ?? [0, 0];
  const mark = markFor(p, { mode });
  const g = gradeView(p.grade);
  const loaded = usePlace(open ? p.facility_id : null);
  const place = useMemo(() => (feature && loaded.status === "ok" ? mergePlace(feature, loaded.detail) : null), [feature, loaded.status, loaded.detail]);
  const facts = useMemo(() => (place ? recordFacts(place).slice(0, 2) : []), [place]);

  useEffect(() => {
    if (open) headingRef.current?.focus({ preventScroll: true });
  }, [open, feature]);

  const onTouchStart = (e) => { startY.current = e.touches[0].clientY; dragging.current = true; };
  const onTouchMove = (e) => {
    if (!dragging.current) return;
    const dy = e.touches[0].clientY - startY.current;
    if (dy > 0) setDragY(dy);
  };
  const onTouchEnd = () => {
    dragging.current = false;
    if (dragY > DISMISS_PX) onClose();
    setDragY(0);
  };

  return (
    <section
      aria-hidden={!open}
      aria-label={open ? `${p.name}, place detail` : undefined}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      className={`fixed inset-x-0 bottom-0 z-40 max-h-[52dvh] overflow-y-auto border-t border-rule-strong bg-paper shadow-paper ${dragging.current ? "" : "transition-transform duration-200 ease-out"}`}
      style={{ transform: open ? `translateY(${dragY}px)` : "translateY(100%)", paddingBottom: "max(16px, env(safe-area-inset-bottom))" }}
    >
      {open && (
        <>
          <div className="flex justify-center pt-2.5" aria-hidden="true">
            <span className="h-[3px] w-9 bg-rule-strong" />
          </div>

          <div className="flex items-start justify-between gap-3 px-5 pt-2">
            <div className="min-w-0 flex-1">
              <p className="text-[13px] text-ink-2">
                {!expired && mark.label && (
                  <>
                    <span className="font-semibold" style={{ color: mark.text ?? undefined }}>{mark.label}</span>
                    <span className="mx-1.5 text-rule-strong">/</span>
                  </>
                )}
                {typeLabel(p.facility_type)}
              </p>
              <h2 ref={headingRef} tabIndex={-1} className="mt-1 font-serif text-[21px] font-medium leading-[1.2] text-ink focus:outline-none">{p.name}</h2>
              <p className="mt-0.5 text-[13px] text-ink-2">{p.address}</p>
              <span
                className="mt-2 inline-block border border-rule-strong px-2 py-[3px] text-[12px] font-semibold text-ink"
                style={g.textColor ? { color: g.textColor, borderColor: g.textColor } : undefined}
              >
                {g.graded ? `Grade ${g.short}` : g.text}
              </span>
            </div>
            <button onClick={onClose} aria-label="Close place detail" className="-mr-2 -mt-1 flex h-11 w-11 shrink-0 items-center justify-center text-ink-3 active:bg-paper-edge">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          <div className="mx-5 mt-3 border-t border-rule pt-3">
            <PlaceLines place={p} />
          </div>

          <div className="mx-5 mt-3 border-t border-rule pt-3">
            {place ? (
              <>
                <p className="label mb-2">What the County&rsquo;s record shows</p>
                <RecordFactList facts={facts} empty="No closure, major violation, B or C grade, repeat reinspection or complaint visit in the 12 months before the last visit." />
              </>
            ) : (
              <PlaceStatus status={loaded.status} id={p.facility_id} onRetry={loaded.retry} />
            )}
          </div>

          <div className="mx-5 mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-rule pt-3 text-[14px]">
            <a href={placePath(p)} onClick={(e) => { e.preventDefault(); onNavigate(placePath(p)); }} className="min-h-[44px] bg-ink px-4 py-3 font-semibold text-paper active:opacity-80">
              The full record
            </a>
            <a href={SITE.regulator.resultsUrl} target="_blank" rel="noopener noreferrer" className="border-b border-ink/30 text-[14px] text-ink-2">
              The County&rsquo;s record
            </a>
          </div>

          {!sample && (
            <a
              href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat},${lon}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mx-5 mt-3 block min-h-[44px] border-t border-rule pt-3 text-[15px] font-medium text-ink active:opacity-70"
            >
              <span className="border-b border-ink/30">Street View</span>
            </a>
          )}

          <div className="mx-5 mt-3 border-t border-rule pt-3">
            <CountyDisclaimer collapsed />
          </div>
        </>
      )}
    </section>
  );
}

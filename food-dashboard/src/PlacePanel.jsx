import { useEffect, useMemo, useRef, useState } from "react";
import MessageBox from "./MessageBox";
import InspectionChart from "./InspectionChart";
import ScoreCard from "./ScoreCard";
import RecordSummary from "./RecordSummary";
import VisitList from "./VisitList";
import StreetViewPanel from "./StreetViewPanel";
import { PlaceLines, PlaceStatus, CountyDisclaimer, RecordFactList, ThemeList } from "./PlaceParts";
import usePlace from "./usePlace";
import { useAdvanced } from "./useAdvanced";
import { useExpired, useMeta, useMode, useSample } from "./useMeta";
import { typeLabel } from "./lib/inspections";
import { gradeView } from "./lib/grades";
import { recordFacts } from "./lib/recordFacts";
import { mergePlace } from "./lib/placeData";
import { citation, recordText } from "./lib/ask";
import { nearbySites } from "./lib/geo";
import { placePath, mapPlacePath } from "./lib/links";
import { markFor } from "./lib/marks";
import { track } from "./lib/track";
import { SITE } from "./site";

/**
 * The detail panel beside the map: the place's name and grade, and in
 * `bands` mode its band, from the index at once; then its full record, loaded
 * from its own file. Prints as a one-page sheet.
 */
export default function PlacePanel({ feature, onClose, facilities = null, onSelect = () => {}, onNavigate = null }) {
  const { advanced, copy } = useAdvanced();
  const meta = useMeta();
  const mode = useMode();
  const expired = useExpired();
  const sample = useSample();
  const [copied, setCopied] = useState(false);
  const [message, setMessage] = useState(null);
  const [status, setStatus] = useState("");
  const headingRef = useRef(null);

  const p = feature?.properties;
  const id = p?.facility_id ?? null;
  const loaded = usePlace(id);
  const place = useMemo(() => (feature && loaded.status === "ok" ? mergePlace(feature, loaded.detail) : null), [feature, loaded.status, loaded.detail]);
  const facts = useMemo(() => (place ? recordFacts(place) : []), [place]);
  const nearby = useMemo(() => (feature && facilities ? nearbySites(feature, facilities, 600, 3) : []), [feature, facilities]);

  useEffect(() => {
    setCopied(false);
    setStatus("");
    headingRef.current?.focus({ preventScroll: true });
  }, [feature]);

  useEffect(() => {
    if (!feature) return undefined;
    const onKey = (e) => e.key === "Escape" && !message && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [feature, onClose, message]);

  if (!feature) return null;

  const [lon, lat] = feature.geometry.coordinates;
  const mark = markFor(p, { mode });
  const g = gradeView(p.grade);
  const pageUrl = `${window.location.origin}${placePath(p)}`;
  const hasCard = mode === "bands" && !expired && !p.on_hold && Array.isArray(place?.score_card) && place.score_card.length > 0;

  async function copyLink() {
    const url = `${window.location.origin}${mapPlacePath(p)}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setStatus("Link copied.");
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setMessage({ title: "Link to this place", text: url, copied: false });
    }
  }

  function showText(title, text) {
    track(title === "Citation" ? "copy-citation" : "copy-record");
    navigator.clipboard?.writeText(text).then(
      () => setMessage({ title, text, copied: true }),
      () => setMessage({ title, text, copied: false })
    );
  }

  const askArgs = place ? { place, url: pageUrl, meta, mode, expired } : null;

  return (
    <aside aria-label={`${p.name}, place detail`} className="print-sheet absolute inset-y-0 right-0 z-30 flex w-full max-w-[27rem] flex-col border-l border-rule-strong bg-paper shadow-paper">
      {message && <MessageBox title={message.title} text={message.text} copied={message.copied} onClose={() => setMessage(null)} />}

      <header className="shrink-0 border-b border-rule-strong px-6 pb-4 pt-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[13px] text-ink-2">
            {!expired && mark.label ? <span className="font-semibold" style={{ color: mark.text ?? undefined }}>{mark.label}</span> : typeLabel(p.facility_type)}
          </p>
          <div className="print-hide flex shrink-0 items-center gap-3 text-[13px]">
            <button onClick={() => window.print()} className="border-b border-ink/25 text-ink-2 hover:border-ink hover:text-ink">Print</button>
            <button onClick={copyLink} className="border-b border-ink/25 text-ink-2 hover:border-ink hover:text-ink">{copied ? "Copied" : "Copy link"}</button>
            <button onClick={onClose} aria-label="Close place detail" className="-mr-2 flex h-9 w-9 items-center justify-center text-[20px] leading-none text-ink-3 hover:text-ink">×</button>
          </div>
        </div>
        <h2 ref={headingRef} tabIndex={-1} className="mt-1 font-serif text-[23px] font-medium leading-[1.2] text-ink focus:outline-none">
          {p.name}
        </h2>
        <p className="mt-1 text-[13px] text-ink-2">{p.address}</p>
        <span className="sr-only" role="status">{status}</span>
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Tag>{typeLabel(p.facility_type)}</Tag>
          {p.council_district && <Tag>{SITE.districts.short} {p.council_district}</Tag>}
          <Tag color={g.textColor}>{g.graded ? `Grade ${g.short}` : g.text}</Tag>
        </div>
        <div className="mt-3 empty:hidden">
          <PlaceLines place={p} withGrade={loaded.status !== "ok"} />
        </div>
      </header>

      <div className="print-scroll flex-1 overflow-y-auto">
        {!place ? (
          <div className="px-6 py-5">
            <PlaceStatus status={loaded.status} id={id} onRetry={loaded.status === "error" || loaded.status === "missing" ? loaded.retry : null} />
          </div>
        ) : (
          <>
            <Block heading={copy.detailHistory} note={copy.detailHistoryNote}>
              <InspectionChart inspections={place.inspections} />
              <div className="mt-3">
                <RecordSummary place={place} meta={meta} />
              </div>
              <VisitList inspections={place.inspections} heading={copy.detailVisits} />
            </Block>

            <Block heading={copy.detailFacts} note={copy.detailFactsNote}>
              <RecordFactList facts={facts} empty={copy.detailNoFacts} />
            </Block>

            <Block heading={copy.detailFindings} note={copy.detailFindingsNote}>
              <ThemeList violations={place.violations} advanced={advanced} />
            </Block>

            {hasCard && (
              <Block heading={copy.detailCard} note={copy.detailCardNote}>
                <ScoreCard p={place} meta={meta} advanced={advanced} />
              </Block>
            )}
          </>
        )}

        {nearby.length > 0 && (
          <Block heading={copy.detailNearby}>
            <ul>
              {nearby.map(({ feature: f, meters }) => {
                const q = f.properties;
                const m = markFor(q, { mode });
                const qg = gradeView(q.grade);
                return (
                  <li key={q.facility_id} className="border-b border-rule last:border-b-0">
                    <button onClick={() => onSelect(f)} className="flex w-full items-baseline gap-3 py-2.5 text-left hover:bg-paper-sunk">
                      <span className="min-w-0 flex-1">
                        <span className="block text-[13.5px] leading-snug text-ink">{q.name}</span>
                        <span className="block text-[12.5px] text-ink-2">
                          {Math.round(meters / 10) * 10} m away, {qg.graded ? `grade ${qg.short}` : qg.text.toLowerCase()}
                          {!expired && m.label ? `, ${m.label.toLowerCase()}` : ""}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </Block>
        )}

        <Block heading={sample ? copy.detailRecord : copy.detailStreetView} last>
          {!sample && <div className="print-hide"><StreetViewPanel lat={lat} lon={lon} /></div>}
          <nav aria-label="Links for this place" className={`${sample ? "" : "mt-3 "}flex flex-wrap gap-x-4 gap-y-1.5 text-[13px]`}>
            <ExternalLink href={SITE.regulator.resultsUrl}>{copy.detailRecord}</ExternalLink>
            {!sample && <ExternalLink href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${p.name} ${p.address}`)}`}>Google Maps</ExternalLink>}
            {!sample && <ExternalLink href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat},${lon}`}>Street View, full screen</ExternalLink>}
            {onNavigate && (
              <a href={placePath(p)} onClick={(e) => { e.preventDefault(); onNavigate(placePath(p)); }} className="border-b border-ink/25 text-ink-2 hover:border-ink hover:text-ink">
                This place as a page
              </a>
            )}
          </nav>
          {askArgs && (
            <div className="print-hide mt-4 flex flex-wrap gap-x-4 gap-y-2 text-[13px]">
              <button onClick={() => showText("The record", recordText(askArgs))} className="bg-ink px-3.5 py-2 text-[13px] font-semibold text-paper hover:bg-ink-2">
                Copy the record
              </button>
              <button onClick={() => showText("Citation", citation(askArgs))} className="border-b border-ink/25 text-ink-2 hover:border-ink hover:text-ink">
                Copy a citation
              </button>
            </div>
          )}
          <div className="mt-4">
            <CountyDisclaimer collapsed />
          </div>
          <p className="mt-3 font-mono text-[12px] text-ink-3">
            County permit record {p.facility_id}; {lat.toFixed(6)}, {lon.toFixed(6)}
          </p>
        </Block>
      </div>
    </aside>
  );
}

function Tag({ children, color }) {
  return (
    <span className="border border-rule-strong px-2 py-[3px] text-[12px] font-semibold text-ink" style={color ? { color, borderColor: color } : undefined}>
      {children}
    </span>
  );
}

function Block({ heading, note, children, last = false }) {
  return (
    <section className={`px-6 py-5 ${last ? "" : "border-b border-rule"}`}>
      <h3 className="label">{heading}</h3>
      {note ? <p className="mb-3 mt-1 text-[13px] text-ink-2">{note}</p> : <div className="mb-3" />}
      {children}
    </section>
  );
}

function ExternalLink({ href, children }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="border-b border-ink/25 text-ink-2 hover:border-ink hover:text-ink">
      {children}
    </a>
  );
}

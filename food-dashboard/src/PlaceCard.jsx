import { useMemo } from "react";
import PageFrame from "./PageFrame";
import InspectionChart from "./InspectionChart";
import ScoreCard from "./ScoreCard";
import RecordSummary from "./RecordSummary";
import VisitList from "./VisitList";
import { PlaceLines, PlaceStatus, CountyDisclaimer, RecordFactList, ThemeList } from "./PlaceParts";
import usePlace from "./usePlace";
import { useAdvanced } from "./useAdvanced";
import { useExpired, useMeta, useMode, useSample } from "./useMeta";
import { typeLabel } from "./lib/inspections";
import { gradeView } from "./lib/grades";
import { recordFacts } from "./lib/recordFacts";
import { mergePlace } from "./lib/placeData";
import { citation } from "./lib/ask";
import { findPlace, placePath, mapPlacePath } from "./lib/links";
import { markFor } from "./lib/marks";
import { SITE } from "./site";

const LINK = "border-b border-ink/25 text-ink hover:border-ink";

/**
 * One place as a page, for printing and for a link in a memo: everything the
 * panel shows, without the map. The page is keyed on the County's permit
 * record id; a key that names no listed place is a page that is not found.
 * The index gives the name, the grade and the band at once; the full record
 * comes from the place's own file.
 */
export default function PlaceCard({ placeKey, facilities, error = null, onRetry = null, onNavigate }) {
  const meta = useMeta();
  const mode = useMode();
  const expired = useExpired();
  const sample = useSample();
  const { advanced, copy } = useAdvanced();
  const feature = useMemo(() => findPlace(facilities?.features, placeKey), [facilities, placeKey]);
  const loaded = usePlace(feature ? feature.properties.facility_id : null);
  const place = useMemo(() => (feature && loaded.status === "ok" ? mergePlace(feature, loaded.detail) : null), [feature, loaded.status, loaded.detail]);
  const facts = useMemo(() => (place ? recordFacts(place) : []), [place]);
  const go = (p) => (e) => { e.preventDefault(); onNavigate(p); };

  if (error && !facilities) {
    return (
      <PageFrame onNavigate={onNavigate}>
        <p className="label mb-4">The list did not load</p>
        <PlaceStatus status="error" id={placeKey} onRetry={onRetry} large />
      </PageFrame>
    );
  }
  if (!facilities) {
    return (
      <PageFrame onNavigate={onNavigate}>
        <PlaceStatus status="loading" large />
      </PageFrame>
    );
  }
  if (!feature) {
    return (
      <PageFrame onNavigate={onNavigate}>
        <p className="label mb-4">Not listed</p>
        <h1 className="font-serif text-[32px] font-medium leading-[1.1] text-ink">
          No listed place has the permit record <span className="break-all font-mono text-[0.7em] font-normal">{placeKey}</span>.
        </h1>
        <p className="mt-4 max-w-[52ch] text-[15px] leading-[1.55] text-ink-2">
          A place can leave the list when the export is drawn up again. The County&rsquo;s own{" "}
          <a href={SITE.regulator.resultsUrl} target="_blank" rel="noopener noreferrer" className={LINK}>inspection search</a> has every place it
          inspects. A place that is not listed is not rated safe or unsafe.
        </p>
        {!expired && <p className="mt-4 text-[15px]"><a href="/map" onClick={go("/map")} className={LINK}>Open the map</a></p>}
      </PageFrame>
    );
  }

  const p = feature.properties;
  const mark = markFor(p, { mode });
  const g = gradeView(p.grade);
  const hasCard = mode === "bands" && !expired && !p.on_hold && Array.isArray(place?.score_card) && place.score_card.length > 0;

  return (
    <PageFrame onNavigate={onNavigate}>
      <p className="label mb-3">
        {SITE.name}, {typeLabel(p.facility_type)}
        {p.council_district && <>, {SITE.districts.short} {p.council_district}</>}
        {!expired && mark.label && <>, <span style={{ color: mark.text ?? undefined }}>{mark.label}</span></>}
      </p>
      <h1 className="font-serif text-[34px] font-medium leading-[1.08] tracking-[-0.02em] text-ink sm:text-[42px]">{p.name}</h1>
      <p className="mt-2 text-[15px] text-ink-2">{p.address}</p>
      {g.graded && (
        <p className="mt-3 inline-block border px-2 py-[3px] text-[13px] font-semibold" style={{ color: g.textColor ?? undefined, borderColor: g.textColor ?? "#B8AF9C" }}>
          Grade {g.short}
        </p>
      )}
      <div className="mt-3 max-w-[62ch]">
        <PlaceLines place={p} large withGrade={!place} />
      </div>

      <p className="print-hide mt-5 flex flex-wrap gap-x-5 gap-y-2 text-[14px]">
        {!expired && <a href={mapPlacePath(p)} onClick={go(mapPlacePath(p))} className={LINK}>Open on the map</a>}
        <button onClick={() => window.print()} className={LINK}>Print this page</button>
        <a href={SITE.regulator.resultsUrl} target="_blank" rel="noopener noreferrer" className={LINK}>The County&rsquo;s record</a>
        {!sample && (
          <a href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${p.name} ${p.address}`)}`} target="_blank" rel="noopener noreferrer" className={LINK}>
            Google Maps
          </a>
        )}
      </p>

      {!place ? (
        <div className="mt-9">
          <PlaceStatus status={loaded.status} id={p.facility_id} onRetry={loaded.retry} large />
        </div>
      ) : (
        <>
          <Section heading="The County's record">
            <InspectionChart inspections={place.inspections} />
            <div className="mt-3">
              <RecordSummary place={place} meta={meta} large />
            </div>
          </Section>

          <Section heading={copy.detailVisits}>
            <VisitList inspections={place.inspections} open heading={copy.detailVisits} />
          </Section>

          <Section heading={copy.detailFacts}>
            <p className="mb-3 text-[13.5px] text-ink-2">{copy.detailFactsNote}.</p>
            <RecordFactList facts={facts} large empty={copy.detailNoFacts} />
          </Section>

          <Section heading={copy.detailFindings}>
            <ThemeList violations={place.violations} advanced={advanced} large />
          </Section>

          {hasCard && (
            <Section heading={copy.detailCard}>
              <p className="mb-3 text-[13.5px] text-ink-2">{copy.detailCardNote}.</p>
              <ScoreCard p={place} meta={meta} advanced={advanced} large />
            </Section>
          )}
        </>
      )}

      <Section heading="The County's disclaimer">
        <CountyDisclaimer />
      </Section>

      <Section heading="Cite this place">
        <p className="font-mono text-[13px] leading-[1.6] text-ink-2">
          {citation({ place: p, url: `${SITE.siteUrl}${placePath(p)}`, meta, mode, expired })}
        </p>
        <p className="mt-2 font-mono text-[12px] text-ink-3">County permit record {p.facility_id}</p>
      </Section>
    </PageFrame>
  );
}

function Section({ heading, children }) {
  return (
    <section className="mt-9">
      <h2 className="label mb-3">{heading}</h2>
      {children}
    </section>
  );
}

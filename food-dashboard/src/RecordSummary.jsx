import { inspectionStats, visitLabel, OUR_READING } from "./lib/inspections";
import { gradeView } from "./lib/grades";
import { gradeContextSentence } from "./lib/framing";
import { fmtDate, fmtMonth } from "./lib/dates";

const plural = (n, one, many = `${one}s`) => (n === 1 ? one : many);

/**
 * The record in sentences. The first is the grade, from the index through
 * lib/grades.js, the same text every view shows; then the County records
 * since the record starts, the last with the County's own status text, the
 * three kinds of item cited, and closures as the County recorded them, with
 * our reading of the reason marked as ours.
 */
export default function RecordSummary({ place, meta, large = false }) {
  const text = large ? "text-[15px]" : "text-[13.5px]";
  const stats = inspectionStats(place);
  const g = gradeView(place?.grade);
  const n = (x) => <b className="tnum font-semibold text-ink">{x}</b>;
  const closures = stats ? stats.closures + stats.permitClosures + stats.otherClosures : 0;

  return (
    <div className={`space-y-2 leading-[1.55] text-ink-2 ${text}`}>
      <p className="text-ink">
        {g.sentence}
        {g.replacedSentence && <span className="text-ink-2"> {g.replacedSentence}</span>}
      </p>
      {stats ? (
        <>
          <p>
            {n(stats.count)} County {plural(stats.count, "record")} since {fmtMonth(stats.first.date)}, the last on {fmtDate(stats.last.date)}: a{" "}
            {visitLabel(stats.last.type)}{stats.last.status && <>, status &ldquo;{stats.last.status}&rdquo;</>}
            {stats.lastScore != null && <>, score {n(stats.lastScore)}</>}.
          </p>
          <p>
            In the three years before the last visit: {n(stats.majors36)} major {plural(stats.majors36, "violation")},{" "}
            {n(stats.minors36)} minor {plural(stats.minors36, "violation")} and {n(stats.grp36)} good-retail-practice{" "}
            {plural(stats.grp36, "item")}
            {stats.reinspections > 0 && <>; {n(stats.reinspections)} {plural(stats.reinspections, "reinspection")}</>}
            {closures > 0 && <>; {n(closures)} &ldquo;Ordered Closed&rdquo; {plural(closures, "record")}</>}.
          </p>
          {closures > 0 && (
            <p className="text-[13px]">
              Our reading of the closures: {stats.closures} on a day a major violation was cited
              {stats.permitClosures > 0 && <>, {stats.permitClosures} over a permit ({OUR_READING.permit.replace(/\.$/, "")})</>}
              {stats.otherClosures > 0 && <>, {stats.otherClosures} for a reason the record does not give</>}.
            </p>
          )}
        </>
      ) : (
        <p>No County records in this export for this place.</p>
      )}
      <p className="text-[13px] leading-[1.5]">{gradeContextSentence(meta)}</p>
    </div>
  );
}

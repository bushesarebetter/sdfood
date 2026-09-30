import { inspectionStats, visitPhrase, countyType, OUR_READING, SAME_CLOSURE } from "./lib/inspections";
import { gradeView } from "./lib/grades";
import { gradeContextSentence } from "./lib/framing";
import { fmtDate, fmtMonth } from "./lib/dates";

const plural = (n, one, many = `${one}s`) => (n === 1 ? one : many);

/**
 * The record in sentences. The first is the grade, from the index through
 * lib/grades.js, the same text every view shows (a closure with no reopening
 * on record leads it); then the County records since the record starts, the
 * last with the County's own status text and type, the three kinds of item
 * cited in the three years before the last visit, and, over the whole record,
 * reinspections and closures: our count of closures beside the County's own
 * count of "Ordered Closed" records, with our reading of each marked as ours.
 * When there are more "Ordered Closed" records than closures that start at
 * one, it says by what rule a further order joins a closure (SAME_CLOSURE).
 */
export default function RecordSummary({ place, meta, large = false }) {
  const text = large ? "text-[15px]" : "text-[13.5px]";
  const stats = inspectionStats(place);
  const g = gradeView(place?.grade);
  const n = (x) => <b className="tnum font-semibold text-ink">{x}</b>;
  const closures = stats?.closureEpisodes ?? 0;
  const orders = stats?.orderedClosedRecords ?? 0;
  const joined = orders > (stats?.orderClosures ?? 0);
  const ct = stats ? countyType(stats.last) : null;

  return (
    <div className={`space-y-2 leading-[1.55] text-ink-2 ${text}`}>
      <p className="text-ink" style={g.closedOpen && g.textColor ? { color: g.textColor } : undefined}>
        {g.sentence}
        {g.replacedSentence && <span className="text-ink-2"> {g.replacedSentence}</span>}
      </p>
      {stats ? (
        <>
          <p>
            {n(stats.count)} County {plural(stats.count, "record")} since {fmtMonth(stats.first.date)}, the last on {fmtDate(stats.last.date)}: a{" "}
            {visitPhrase(stats.last)}
            {ct && stats.last.type !== "followup" && stats.last.type !== "complaint" && <>, County type &ldquo;{ct}&rdquo;</>}
            {stats.last.status && <>, status &ldquo;{stats.last.status}&rdquo;</>}
            {stats.lastScore != null && <>, score {n(stats.lastScore)}</>}.
          </p>
          <p>
            In the three years before the last visit: {n(stats.majors36)} major {plural(stats.majors36, "violation")},{" "}
            {n(stats.minors36)} minor {plural(stats.minors36, "violation")} and {n(stats.grp36)} good-retail-practice{" "}
            {plural(stats.grp36, "item")}.
          </p>
          {(stats.reinspections > 0 || closures > 0 || orders > 0 || stats.reopenedWithoutClosure > 0) && (
            <p>
              Since {fmtMonth(stats.first.date)}: {n(stats.reinspections)} {plural(stats.reinspections, "reinspection")}
              {(closures > 0 || orders > 0) && (
                <>
                  ; {n(orders)} &ldquo;Ordered Closed&rdquo; {plural(orders, "record")}
                  {closures > 0 && (
                    <>
                      {" "}and {n(closures)} {plural(closures, "closure")} in our reading
                      {joined && <> ({SAME_CLOSURE})</>}
                    </>
                  )}
                </>
              )}
              {stats.selfClosures > 0 && <>; {n(stats.selfClosures)} of the closures &ldquo;Self Closed&rdquo;</>}
              {stats.inferredClosures > 0 && (
                <>; {n(stats.inferredClosures)} {plural(stats.inferredClosures, "closure")} shown only by a later &ldquo;Approved to Reopen&rdquo;, with no closure order on the published record</>
              )}
              {stats.reopenedWithoutClosure > 0 && (
                <>; {n(stats.reopenedWithoutClosure)} &ldquo;Approved to Reopen&rdquo; {plural(stats.reopenedWithoutClosure, "record")} no closure could be placed before</>
              )}
              .
            </p>
          )}
          {closures > 0 && (
            <p className="text-[13px]">
              Our reading of the closures: {stats.closures} on a day a major violation was cited
              {stats.permitClosures > 0 && <>; {stats.permitClosures} where {OUR_READING.permit.replace(/\.$/, "")}</>}
              {stats.otherClosures > 0 && <>; {stats.otherClosures} on a day no major violation was cited and no County note mentioned a permit</>}
              {stats.selfClosures > 0 && <>; a &ldquo;Self Closed&rdquo; record is read as the operator&rsquo;s own closure</>}.
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

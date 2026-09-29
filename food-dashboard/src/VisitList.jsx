import { visitLabel, recordGradeText, reopenedText, OUR_READING, CLOSURE_LABELS, CLOSURES } from "./lib/inspections";
import { fmtDate } from "./lib/dates";

const sentence = (s) => `${s.charAt(0).toUpperCase()}${s.slice(1)}`;

/**
 * Every County record for a place, one row per record, oldest first, with
 * the County's status text verbatim. A visit we read as a re-grade or
 * reopening visit, and the reason for a closure, are marked as our reading.
 * A closure the County's "Approved to Reopen" record ended shows that date.
 * The page shows it open; the panel keeps it folded.
 */
export default function VisitList({ inspections, open = false, heading = "Every County record" }) {
  const list = inspections ?? [];
  if (!list.length) return null;
  const retyped = list.some((i) => i.type === "followup");
  const reasons = CLOSURES.filter((c) => list.some((i) => i.closed && i.closure === c));
  const table = (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px] leading-[1.4]">
        <caption className="sr-only">{heading}, oldest first</caption>
        <thead>
          <tr className="border-b border-rule-strong text-left">
            {["Date", "Visit", "County status", "Score", "Grade", "Major / minor / GRP"].map((h, i) => (
              <th key={h} scope="col" className={`label py-1.5 pr-3 ${i >= 3 ? "text-right" : ""}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {list.map((i, k) => (
            <tr key={`${i.date}-${k}`} className="border-b border-rule align-baseline">
              <td className="tnum whitespace-nowrap py-1.5 pr-3 text-ink">{fmtDate(i.date)}</td>
              <td className="py-1.5 pr-3 text-ink-2">
                {visitLabel(i.type)}
                {i.type === "followup" && <span className="text-ink-3"> (our reading)</span>}
              </td>
              <td className="py-1.5 pr-3 text-ink">
                {i.status || ""}
                {i.closed && i.closure && <span className="block text-[12px] text-ink-3">our reading: {CLOSURE_LABELS[i.closure] ?? i.closure}</span>}
                {reopenedText(i) && <span className="block text-[12px] text-ink-2">{reopenedText(i)}</span>}
              </td>
              <td className="tnum py-1.5 pr-3 text-right">{typeof i.score === "number" ? i.score : ""}</td>
              <td className="tnum py-1.5 pr-3 text-right">{recordGradeText(i) ? i.grade : ""}</td>
              <td className="tnum whitespace-nowrap py-1.5 text-right">{i.major ?? 0} / {i.minor ?? 0} / {i.grp ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(retyped || reasons.length > 0) && (
        <p className="mt-2 text-[13px] leading-[1.5] text-ink-2">
          {retyped && <>Our reading: {OUR_READING.followup} </>}
          {reasons.length > 0 && <>A closure&rsquo;s reason is our reading.</>}
          {reasons.map((c) => <span key={c}> {sentence(CLOSURE_LABELS[c])}: {OUR_READING[c]}</span>)}
        </p>
      )}
    </div>
  );
  if (open) return table;
  return (
    <details className="mt-3">
      <summary className="cursor-pointer text-[13.5px] text-ink">{heading} ({list.length})</summary>
      <div className="mt-2">{table}</div>
    </details>
  );
}

import {
  visitLabel, recordGradeText, reopenedText, closureWords, closureEnd, countyNotes, countyType,
  OUR_READING, CLOSURE_LABELS, CLOSURES, READ_VISIT_TYPES, KEPT_NOTE,
} from "./lib/inspections";
import { fmtDate } from "./lib/dates";

const sentence = (s) => `${s.charAt(0).toUpperCase()}${s.slice(1)}`;

/**
 * The County records the export keeps for a place, one row per record,
 * oldest first, with the County's status text, its inspection type and its
 * notes verbatim; under them, which records are left out (KEPT_NOTE). A
 * visit we read as a re-grade or reopening visit, or as a complaint or other
 * field visit, and the reason for a closure are marked as our reading; so are
 * a closure that only a later "Approved to Reopen" shows and an "Approved to
 * Reopen" no closure could be placed before. A closure the County's "Approved
 * to Reopen" record ended shows that date; one with no "Approved to Reopen"
 * and no graded visit after it says so. The page shows it open; the panel
 * keeps it folded.
 */
export default function VisitList({ inspections, open = false, heading = "The County records we keep" }) {
  const list = (inspections ?? []).filter((i) => i?.date);
  if (!list.length) return null;
  const has = (pred) => list.some(pred);
  const reasons = CLOSURES.filter((c) => has((i) => i.closed && i.closure === c));
  const kinds = new Set(list.filter((i) => i.closed).map((i) => closureWords(i).kind));
  const readTypes = READ_VISIT_TYPES.filter((t) => has((i) => i.type === t));
  const reopenOnly = has((i) => i.reopen_without_closure === true);
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
          {list.map((i, k) => {
            const ct = countyType(i);
            const read = READ_VISIT_TYPES.includes(i.type);
            const w = i.closed ? closureWords(i) : null;
            const end = i.closed && i.reopened === false ? closureEnd(list, k) : null;
            return (
              <tr key={`${i.date}-${k}`} className="border-b border-rule align-baseline">
                <td className="tnum whitespace-nowrap py-1.5 pr-3 text-ink">{fmtDate(i.date)}</td>
                <td className="py-1.5 pr-3 text-ink-2">
                  {ct ?? visitLabel(i.type)}
                  {read && !ct && <span className="text-ink-3"> (our reading)</span>}
                  {read && ct && <span className="block text-[12px] text-ink-3">our reading: {visitLabel(i.type)}</span>}
                </td>
                <td className="py-1.5 pr-3 text-ink">
                  {i.status || ""}
                  {countyNotes(i).map((note, n) => (
                    <span key={`${n}-${note}`} className="block text-[12px] text-ink-2">County note: {note}</span>
                  ))}
                  {w && <span className="block text-[12px] text-ink-3">our reading: {w.short}</span>}
                  {reopenedText(i) && <span className="block text-[12px] text-ink-2">{reopenedText(i)}</span>}
                  {end?.open && <span className="block text-[12px] text-ink-2">No &ldquo;Approved to Reopen&rdquo; and no graded visit after it on record</span>}
                  {i.reopen_without_closure === true && <span className="block text-[12px] text-ink-3">our reading: no closure placed before it</span>}
                </td>
                <td className="tnum py-1.5 pr-3 text-right">{typeof i.score === "number" ? i.score : ""}</td>
                <td className="tnum py-1.5 pr-3 text-right">{recordGradeText(i) ? i.grade : ""}</td>
                <td className="tnum whitespace-nowrap py-1.5 text-right">{i.major ?? 0} / {i.minor ?? 0} / {i.grp ?? 0}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {(readTypes.length > 0 || reasons.length > 0 || reopenOnly) && (
        <p className="mt-2 text-[13px] leading-[1.5] text-ink-2">
          {readTypes.map((t) => <span key={t}>Our reading: {OUR_READING[t]} </span>)}
          {reasons.length > 0 && <>A closure&rsquo;s reason is our reading.</>}
          {reasons.map((c) => <span key={c}> {sentence(CLOSURE_LABELS[c])}: {OUR_READING[c]}</span>)}
          {kinds.has("self") && <span> Self Closed: {OUR_READING.selfClosed}</span>}
          {kinds.has("inferred") && <span> A closure from an &ldquo;Approved to Reopen&rdquo;: {OUR_READING.inferred}</span>}
          {reopenOnly && <span> No closure placed: {OUR_READING.reopenOnly}</span>}
        </p>
      )}
      <p className="mt-2 text-[13px] leading-[1.5] text-ink-2">{KEPT_NOTE}</p>
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

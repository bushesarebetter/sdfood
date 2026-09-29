import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ReferenceLine } from "recharts";
import { useAdvanced } from "./useAdvanced";
import { fmtShort, fmtDate } from "./lib/dates";
import { visitPhrase, isGraded, countyNotes, countyType, visitLabel } from "./lib/inspections";
import { GRADE_SWATCH, OPEN_CLOSURE_COLOR } from "./lib/grades";

const AXIS = { fontSize: 11, fill: "#6B6457", fontFamily: "ui-monospace, Consolas, monospace" };
const FLOOR = 50;
// A visit with no score still happened: it is drawn as a short stub.
const STUB = 53;
const LIGHT = 0.5;
const NO_SCORE = "#B8AF9C";
const SCORED_UNGRADED = "#8A8272";
const CLOSED = OPEN_CLOSURE_COLOR;

function PaperTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const items = [d.major ? `${d.major} major` : "", d.minor ? `${d.minor} minor` : "", d.grp ? `${d.grp} good-retail-practice` : ""].filter(Boolean);
  const notes = countyNotes(d);
  return (
    <div style={{ background: "#FBF9F5", border: "1px solid #B8AF9C", padding: "8px 10px", fontSize: 12, color: "#17150F", maxWidth: 240 }}>
      <div style={{ fontWeight: 600 }}>{fmtDate(d.date)}</div>
      <div style={{ color: "#55503F" }}>
        {countyType(d) ? `${countyType(d)} (County type)` : visitPhrase(d)}
        {d.status ? `, "${d.status}"` : ""}
        {d.score != null ? `, score ${d.score}` : ", no score"}
        {isGraded(d) ? `, grade ${d.grade}` : ""}
        {items.length ? `; ${items.join(", ")}` : ""}
        {notes.length ? `; County ${notes.length === 1 ? "note" : "notes"}: ${notes.join(", ")}` : ""}
        {countyType(d) && (d.type === "followup" || d.type === "complaint") ? `; our reading: ${visitLabel(d.type)}` : ""}
        {d.closed ? `; start of a closure (our reading)` : ""}
      </div>
    </div>
  );
}

const fillFor = (d) => {
  if (d.closed) return CLOSED;
  if (typeof d.score !== "number") return NO_SCORE;
  return isGraded(d) ? GRADE_SWATCH[d.grade] : SCORED_UNGRADED;
};

/**
 * Score by County record, oldest to newest, coloured by the County's grade.
 * Re-grade or reopening visits, reinspections, complaint or other field
 * visits and status verifications are drawn lighter than routine ones; a
 * record with no score is a short stub, and the record that starts a closure
 * (our reading: an "Ordered Closed", a "Self Closed" with a major, or a
 * closure only a later "Approved to Reopen" shows) is drawn in the closure
 * colour. The same records are in a table for screen readers.
 */
export default function InspectionChart({ inspections }) {
  const { advanced } = useAdvanced();
  const list = inspections ?? [];
  const data = list.map((i) => ({ ...i, plotted: typeof i.score === "number" ? Math.max(i.score, STUB) : STUB }));
  const has = (pred) => list.some(pred);
  const lighter = has((i) => (i.type ?? "routine") !== "routine");

  return (
    <figure>
      <div aria-hidden="true">
        <ResponsiveContainer width="100%" height={140}>
          <BarChart data={data} margin={{ top: 4, right: 2, left: -22, bottom: 0 }}>
            <XAxis dataKey="date" tickFormatter={fmtShort} tick={AXIS} tickLine={false} axisLine={{ stroke: "#DCD5C7" }} interval="preserveStartEnd" minTickGap={24} />
            <YAxis domain={[FLOOR, 100]} ticks={[FLOOR, 80, 90, 100]} tick={AXIS} tickLine={false} axisLine={false} width={26} allowDataOverflow />
            <ReferenceLine y={90} stroke="#DCD5C7" strokeDasharray="2 3" />
            <Tooltip content={<PaperTooltip />} cursor={{ fill: "rgba(23,21,15,0.05)" }} />
            <Bar dataKey="plotted" isAnimationActive={false}>
              {data.map((d, i) => (
                <Cell key={i} fill={fillFor(d)} fillOpacity={(d.type ?? "routine") === "routine" ? 1 : LIGHT} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <table className="sr-only">
        <caption>Inspection scores by County record, oldest first</caption>
        <thead>
          <tr><th scope="col">Date</th><th scope="col">Visit</th><th scope="col">Score</th><th scope="col">Grade</th><th scope="col">Major violations</th></tr>
        </thead>
        <tbody>
          {list.map((i, k) => (
            <tr key={k}>
              <td>{fmtDate(i.date)}</td>
              <td>{visitPhrase(i)}{countyType(i) && i.type !== "followup" && i.type !== "complaint" ? ` (County type: ${countyType(i)})` : ""}{i.status ? `, ${i.status}` : ""}{i.closed ? ", start of a closure (our reading)" : ""}</td>
              <td>{typeof i.score === "number" ? i.score : "no score"}</td>
              <td>{isGraded(i) ? i.grade : "not graded"}</td>
              <td>{i.major ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <ul className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1" aria-hidden="true">
        {[["A", "A, 90 or more"], ["B", "B, 80 to 89"], ["C", "C, 79 or less"]].map(([g, label]) => (
          <Key key={g} color={GRADE_SWATCH[g]}>{advanced ? g : label}</Key>
        ))}
        {lighter && <Key color="#55503F" opacity={LIGHT}>lighter: re-grade or reopening visit, reinspection, complaint or other field visit, status verification</Key>}
        {has((i) => typeof i.score !== "number" && !i.closed) && <Key color={NO_SCORE} short>no score</Key>}
        {has((i) => i.closed) && <Key color={CLOSED} short>start of a closure (our reading)</Key>}
        {has((i) => typeof i.score === "number" && !isGraded(i) && !i.closed) && <Key color={SCORED_UNGRADED}>scored, not graded</Key>}
      </ul>
    </figure>
  );
}

function Key({ color, opacity = 1, short = false, children }) {
  return (
    <li className="flex items-center gap-1.5 text-[12px] text-ink-2">
      <span className={`inline-block w-2 ${short ? "h-1" : "h-2"}`} style={{ backgroundColor: color, opacity }} />
      {children}
    </li>
  );
}

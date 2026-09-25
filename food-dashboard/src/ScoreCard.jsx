import { worksheet, rowText } from "./lib/card";
import { bandDefs, bandPoints, bandSummary, ruleSentence, stabilitySentence } from "./lib/bands";
import { shownBand } from "./lib/marks";

/**
 * "How the points add up" (`bands` mode): the published rule in one
 * sentence, each count from the record times its weight, the total, and
 * where that total falls: the band's range of points and what the band has
 * been worth in the backtest, or, for a place in no band, where band 3 starts.
 * Plain mode lists the rows that add points and counts the rest; technical
 * mode shows every row as value × weight.
 */
export default function ScoreCard({ p, meta, advanced = false, large = false }) {
  const w = worksheet(p, meta);
  if (!w) return null;
  const shown = advanced ? w.rows : w.met;
  const text = large ? "text-[15px]" : "text-[13.5px]";
  const band = shownBand(p, { mode: "bands" });
  const lowest = bandDefs(meta).at(-1);
  const stability = advanced ? stabilitySentence(p) : null;

  return (
    <div>
      <p className={`mb-3 leading-[1.5] text-ink-2 ${text}`}>{ruleSentence(meta)}</p>
      <table className={`w-full ${text}`}>
        <caption className="sr-only">How this place&rsquo;s points add up</caption>
        <tbody>
          {shown.map((r) => (
            <tr key={r.item} className="border-b border-rule align-baseline">
              <td className={`py-2 pr-4 leading-[1.4] ${r.met ? "text-ink" : "text-ink-2"}`}>
                {rowText(r, { advanced })}
                {advanced && r.unit && <span className="ml-1.5 text-[12px] text-ink-3">({r.unit})</span>}
              </td>
              <td className="tnum whitespace-nowrap py-2 text-right font-semibold text-ink">+{r.points}</td>
            </tr>
          ))}
          {!shown.length && (
            <tr className="border-b border-rule">
              <td className="py-2 text-ink-2" colSpan={2}>No count on the rule adds points for this place.</td>
            </tr>
          )}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" className="pt-2.5 text-left font-semibold text-ink">Total</th>
            <td className="tnum whitespace-nowrap pt-2.5 text-right font-semibold text-ink">{w.total} {w.total === 1 ? "point" : "points"}</td>
          </tr>
        </tfoot>
      </table>
      {!advanced && w.unmet.length > 0 && (
        <p className="mt-2 text-[13px] text-ink-2">
          {w.unmet.length} other {w.unmet.length === 1 ? "count is" : "counts are"} zero for this place.
        </p>
      )}
      <div className={`mt-3 space-y-2 leading-[1.5] text-ink-2 ${large ? "text-[14.5px]" : "text-[13px]"}`}>
        {band ? (
          <>
            <p>Band {band} is {bandPoints(meta, band) ?? "a range of points"}.</p>
            <p>{bandSummary(meta, band)}</p>
          </>
        ) : (
          <p>In no band{typeof lowest?.min_points === "number" ? `: band ${lowest.band} starts at ${lowest.min_points} points` : ""}.</p>
        )}
        {stability && <p>{stability}</p>}
      </div>
    </div>
  );
}

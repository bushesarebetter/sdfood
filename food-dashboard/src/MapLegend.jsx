import { useState } from "react";
import { useMeta, useMode } from "./useMeta";
import { bandDefs, bandPoints, bandRatePhrase } from "./lib/bands";
import { legendNote } from "./lib/framing";
import { BAND_COLORS, RECORD_DOT, UNBANDED_DOT } from "./lib/marks";

/**
 * The map key. `record` mode: one colour for every place. `bands` mode: each
 * band's colour, its range of points and its backtest rate, with a note that
 * says in words which way darker goes.
 */
export default function MapLegend({ bandsShown = ["1", "2", "3"], showUnbanded = false }) {
  const meta = useMeta();
  const mode = useMode();
  const [open, setOpen] = useState(() => typeof window === "undefined" || window.innerWidth >= 768);

  let rows;
  if (mode === "bands") {
    const defs = bandDefs(meta);
    const keys = defs.length ? defs.map((d) => d.band) : ["1", "2", "3"];
    rows = keys
      .filter((b) => bandsShown.includes(b))
      .map((b) => ({ key: b, hex: BAND_COLORS[b] ?? UNBANDED_DOT, r: 7 - Number(b) * 0.5, label: `Band ${b}`, sub: bandPoints(meta, b), right: bandRatePhrase(meta, b) ?? "" }));
    if (showUnbanded) rows.push({ key: "none", hex: UNBANDED_DOT, r: 4.5, label: "In no band, or under review", sub: null, right: "" });
  } else {
    rows = [{ key: "all", hex: RECORD_DOT, r: 5.5, label: "A listed place", sub: null, right: "" }];
  }

  return (
    <div className="absolute bottom-16 left-4 z-10 max-w-[20rem] border border-rule-strong bg-paper shadow-paper">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex w-full items-center justify-between gap-8 px-4 py-2.5 text-left hover:bg-paper-edge">
        <span className="label">Map key</span>
        <span aria-hidden="true" className={`text-ink-3 ${open ? "" : "rotate-180"}`}>
          <svg width="9" height="9" viewBox="0 0 10 10" fill="none">
            <path d="M2 6.5l3-3 3 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          </svg>
        </span>
      </button>

      {open && (
        <div className="min-w-[240px] border-t border-rule px-4 pb-4 pt-3">
          <ul className="space-y-2">
            {rows.map((t) => (
              <li key={t.key} className="flex items-center gap-3">
                <svg width="16" height="16" className="shrink-0" aria-hidden="true">
                  <circle cx="8" cy="8" r={t.r} fill={t.hex} />
                </svg>
                <span className="flex-1 leading-tight">
                  <span className="block text-[13px] text-ink">{t.label}</span>
                  {t.sub && <span className="block text-[12px] text-ink-2">{t.sub}</span>}
                </span>
                <span className="tnum text-right text-[12px] leading-none text-ink-2">{t.right}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3.5 border-t border-rule pt-2.5 text-[13px] leading-[1.45] text-ink-2">{legendNote(meta)}</p>
        </div>
      )}
    </div>
  );
}

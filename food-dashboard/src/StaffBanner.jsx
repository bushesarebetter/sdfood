import { useEffect, useId, useState } from "react";
import { useMeta } from "./useMeta";
import { isStaff, staffBar, PUBLIC_RECORD_NOTE, USE_NOTE, watchPrints } from "./lib/staff";

// The notice opens by itself on the first page of each browser session (a shared City computer starts a
// new one), until it is acknowledged for this export's run.
const SEEN_KEY = "food.staffNoticeSeen";

function seenFor(run) {
  try {
    return window.sessionStorage.getItem(SEEN_KEY) === String(run ?? "");
  } catch {
    return false;
  }
}

function markSeen(run) {
  try {
    window.sessionStorage.setItem(SEEN_KEY, String(run ?? ""));
  } catch {
    /* the notice then opens again on the next page, which is the safe side */
  }
}

/**
 * On every page of the City staff site: one line that keeps each rule in view in a few words ("For City
 * of San Diego staff · Downloads are likely public records · A student analysis, not a City or County
 * finding · A demonstration, not a City tool · 17 open checks"), a button that opens the whole notice, and
 * sign-out. The notice (lib/staff.js staffBar, the same words compactBanner holds) is the public-record
 * note, the full use rule, whom to write to, the open checks and every instruction, the "demonstration"
 * one first while the City has recorded no request or TRUST Ordinance determination. It opens by itself
 * on the first page of each browser session until acknowledged, and it cannot be dismissed for good. On
 * paper the whole notice always prints, open or not. `compact` is the phone layout: the same line, the
 * points wrapping, the panel scrolling within half the screen.
 */
export default function StaffBanner({ fixed = false, compact = false }) {
  const meta = useMeta();
  const staff = isStaff(meta);
  const run = meta?.run;
  const [open, setOpen] = useState(() => staff && !seenFor(run));
  const panelId = useId();
  useEffect(() => {
    if (staff && !seenFor(run)) setOpen(true);
  }, [staff, run]);
  if (!staff) return null;
  const b = staffBar(meta);
  const acknowledge = () => {
    markSeen(run);
    setOpen(false);
  };
  // A POST from this page: the server signs out only on a same-site POST, so no link elsewhere can do it.
  const signOut = (
    <form method="post" action="/logout" className="inline">
      <button type="submit" className="whitespace-nowrap border-b border-ink/40 font-semibold text-ink hover:border-ink">Sign out</button>
    </form>
  );
  const pad = compact ? "px-3" : "px-4 lg:px-5";

  return (
    <div role="note" aria-label="Notice for City staff" className={`border-b border-ink bg-paper-edge text-ink ${fixed ? "shrink-0" : ""}`}>
      <div className={`print-hide flex flex-wrap items-center gap-x-4 gap-y-1 py-1.5 text-[13px] leading-[1.4] ${pad}`}>
        {/* The points take the line; the buttons follow them, or wrap under them on a narrow screen. */}
        <p className={compact ? "basis-full" : "min-w-[18rem] flex-1"}>
          {b.points.map((pt, i) => (
            <span key={pt} className={i === 0 ? "font-semibold" : ""}>
              {i > 0 && <span aria-hidden="true" className="px-1.5 text-ink-3">&middot;</span>}
              {pt}
            </span>
          ))}
        </p>
        <span className="flex shrink-0 items-center gap-4">
          <button
            type="button"
            onClick={() => (open ? acknowledge() : setOpen(true))}
            aria-expanded={open}
            aria-controls={panelId}
            className="inline-flex items-center gap-1 whitespace-nowrap border-b border-ink/40 text-ink hover:border-ink"
          >
            {open ? "Hide the notice" : b.toggle}
            <svg width="10" height="6" viewBox="0 0 10 6" aria-hidden="true" className={open ? "rotate-180" : ""}>
              <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </button>
          {signOut}
        </span>
      </div>

      {open && (
        <div id={panelId} className={`print-hide border-t border-ink/20 bg-paper-sunk py-3 text-[13px] leading-[1.5] ${pad}`}>
          <div className={`overflow-y-auto ${compact ? "max-h-[45vh]" : "max-h-[40vh]"}`}>
            <div className={compact ? "space-y-2" : "grid gap-x-8 gap-y-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]"}>
              <div className="space-y-2">
                <p><span className="font-semibold">Public records.</span> {PUBLIC_RECORD_NOTE}</p>
                <p><span className="font-semibold">Use rule.</span> {USE_NOTE}</p>
                {b.contact && <p>{b.contact}</p>}
              </div>
              <div>
                {b.open && <p className="font-semibold">{b.open}</p>}
                {b.guidance.length > 0 && (
                  <ul className="mt-1 list-disc space-y-1 pl-5">
                    {b.guidance.map((g) => <li key={g}>{g}</li>)}
                  </ul>
                )}
              </div>
            </div>
          </div>
          <p className="mt-3">
            <button type="button" onClick={acknowledge} className="bg-ink px-4 py-1.5 text-[13px] font-semibold text-paper hover:bg-ink-2">
              I have read this
            </button>
            <span className="ml-3 text-ink-2">It stays one click away, at the top of every page.</span>
          </p>
        </div>
      )}

      {/* On paper, always the whole notice. */}
      <div className="print-only px-1 py-1 text-[10.5px] leading-[1.4]">
        <p><span className="font-semibold">For City of San Diego staff.</span> {PUBLIC_RECORD_NOTE} {USE_NOTE}{b.contact && ` ${b.contact}`}</p>
        {b.open && <p>{b.open}</p>}
        {b.guidance.length > 0 && (
          <ul className="list-disc pl-4">
            {b.guidance.map((g) => <li key={g}>{g}</li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

/**
 * Logs every print on the staff site with the sign-in's id, as a download is (lib/staff.js
 * watchPrints). Mounted once, at the root of the app above every view and layout (App.jsx), so a
 * print from the phone shell, the map, the list or a page is logged exactly once; no banner does it.
 */
export function PrintAudit() {
  const meta = useMeta();
  useEffect(() => watchPrints(meta), [meta]);
  return null;
}

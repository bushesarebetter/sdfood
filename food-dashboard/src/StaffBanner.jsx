import { Fragment, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Dialog, { CloseButton } from "./Dialog";
import { useMeta, useMode } from "./useMeta";
import { bandSummary } from "./lib/bands";
import { isStaff, staffBar, PUBLIC_RECORD_NOTE, USE_NOTE, watchPrints } from "./lib/staff";

// The notice opens by itself on the first page after each sign-in, until "I have read this" is pressed for
// this export's run. The mark lives in sessionStorage, which a new tab starts empty and which the server
// empties at every sign-in (Clear-Site-Data, city_site/server.mjs), so the next person on a shared City
// computer always meets the notice open.
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
 * On every page of the City staff site: one line that keeps each rule in view in a few words (lib/staff.js
 * staffBar: "For City of San Diego staff · A student analysis, not a City or County finding · Do not share
 * names or bands outside the City or use a band for any decision about a business · Downloads, prints and
 * messages are likely public records · A demonstration, not a City tool · Not cleared for public release:
 * 17 checks open"), whom to write to, a button that opens the whole notice, and sign-out. A screen reader
 * hears the points as one punctuated sentence. The notice is the public-record note, the full use rule,
 * what a band 1 place's group rate is and which lines are ours, whom to write to, the open checks and every
 * instruction, then "I have read this", last, so it is reached only past every line. It opens by itself
 * after each sign-in until that button is pressed; closing it any other way does not count as read. On
 * paper the whole notice always prints, open or not. `compact` is the phone layout: the same line, and the
 * notice as a full-screen sheet.
 */
export default function StaffBanner({ fixed = false, compact = false }) {
  const meta = useMeta();
  const mode = useMode();
  const staff = isStaff(meta);
  const run = meta?.run;
  const [open, setOpen] = useState(() => staff && !seenFor(run));
  const panelId = useId();
  const titleId = useId();
  const toggleRef = useRef(null);
  const refocus = useRef(false);
  useEffect(() => {
    if (staff && !seenFor(run)) setOpen(true);
  }, [staff, run]);
  // Closed from inside the notice: focus goes to the toggle, which says where the notice lives. This runs
  // after the phone sheet's Dialog has handed focus back, so it has the last word.
  useEffect(() => {
    if (open || !refocus.current) return;
    refocus.current = false;
    toggleRef.current?.focus();
  }, [open]);
  if (!staff) return null;
  const b = staffBar(meta);
  const close = () => {
    refocus.current = true;
    setOpen(false);
  };
  const acknowledge = () => {
    markSeen(run);
    close();
  };
  // A POST from this page: the server signs out only on a same-site POST, so no link elsewhere can do it.
  const signOut = (
    <form method="post" action="/logout" className="inline">
      <button type="submit" className="whitespace-nowrap border-b border-ink/40 font-semibold text-ink hover:border-ink">Sign out</button>
    </form>
  );
  const pad = compact ? "px-3" : "px-4 lg:px-5";
  const last = b.points.length - 1;

  const rules = (
    <>
      <p><span className="font-semibold">Public records.</span> {PUBLIC_RECORD_NOTE}</p>
      <p><span className="font-semibold">Use rule.</span> {USE_NOTE}</p>
      <p>
        <span className="font-semibold">Reading the list.</span> {mode === "bands" && `${bandSummary(meta, "1")} `}
        Lines marked &ldquo;Our reading&rdquo; are the site&rsquo;s, not the County&rsquo;s.
      </p>
      {b.contact && <p>{b.contact}</p>}
    </>
  );
  const checks = (
    <>
      {b.open && <p className="font-semibold">{b.open}</p>}
      {b.checks.length > 0 && (
        <details className="mt-1">
          <summary className="cursor-pointer text-ink-2 hover:text-ink">Which checks</summary>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-ink-2">
            {b.checks.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </details>
      )}
      {b.guidance.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {b.guidance.map((g) => <li key={g}>{g}</li>)}
        </ul>
      )}
    </>
  );
  const ack = (
    <p>
      <button type="button" onClick={acknowledge} className="bg-ink px-4 py-1.5 text-[13px] font-semibold text-paper hover:bg-ink-2">
        I have read this
      </button>
      <span className="ml-3 text-ink-2">It stays one click away, at the top of every page.</span>
    </p>
  );

  return (
    <div role="note" aria-label="Notice for City staff" className={`border-b border-ink bg-paper-edge text-ink ${fixed ? "shrink-0" : ""}`}>
      <div className={`print-hide flex flex-wrap items-center gap-x-4 gap-y-1 py-1.5 text-[13px] leading-[1.4] ${pad}`}>
        {/* The points take the line; the buttons follow them, or wrap under them on a narrow screen. Each
            point is one unit that wraps whole, its dot at the end of the line; a screen reader hears the
            sentence instead of the dots. */}
        <p className={compact ? "basis-full" : "min-w-[18rem] flex-1"}>
          <span className="sr-only">{`${b.points.join(". ")}.`}</span>
          <span aria-hidden="true">
            {b.points.map((pt, i) => (
              <Fragment key={pt}>
                <span className={`inline-block ${i === 0 ? "font-semibold" : ""}`}>
                  {pt}
                  {i < last && <span className="pl-1.5 pr-1 font-normal text-ink-3">&middot;</span>}
                </span>
                {i < last && " "}
              </Fragment>
            ))}
          </span>
        </p>
        <span className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
          {b.mail && (
            <a href={b.mail.href} className="border-b border-ink/40 text-ink hover:border-ink">{b.mail.label}</a>
          )}
          <button
            ref={toggleRef}
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            {...(compact ? { "aria-haspopup": "dialog" } : { "aria-controls": panelId })}
            className="inline-flex items-center gap-1 whitespace-nowrap border-b border-ink/40 text-ink hover:border-ink"
          >
            {open && !compact ? "Hide the notice" : b.toggle}
            <svg width="10" height="6" viewBox="0 0 10 6" aria-hidden="true" className={open ? "rotate-180" : ""}>
              <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </button>
          {signOut}
        </span>
      </div>

      {/* One scroller, capped at half the screen; "I have read this" is last inside it, after every
          instruction. At lg it sits in the left column's foot, beside the end of the instructions. */}
      {open && !compact && (
        <div
          id={panelId}
          role="region"
          aria-label="The whole notice"
          tabIndex={0}
          className={`print-hide max-h-[50dvh] overflow-y-auto border-t border-ink/20 bg-paper-sunk py-3 text-[13px] leading-[1.5] ${pad}`}
        >
          <div className="grid gap-x-8 gap-y-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
            <div className="space-y-2 lg:col-start-1 lg:row-start-1">{rules}</div>
            <div className="lg:col-start-2 lg:row-start-1 lg:row-span-2">{checks}</div>
            <div className="lg:col-start-1 lg:row-start-2 lg:self-end">{ack}</div>
          </div>
        </div>
      )}

      {/* On the phone, a full-screen sheet over everything (the cookie line included) that scrolls as a
          whole at any zoom, the button at its end. Put on the page's body, so no overlay's stacking holds it. */}
      {open && compact && createPortal(
        <Dialog titleId={titleId} onClose={close} closeOnBackdrop={false} overlayClassName="!p-0" className="min-h-dvh max-w-none border-0" z={60}>
          <div className="flex items-center justify-between border-b border-rule-strong px-5 py-1" style={{ paddingTop: "max(4px, env(safe-area-inset-top))" }}>
            <h2 id={titleId} className="label focus:outline-none">Notice for City staff</h2>
            <CloseButton onClose={close} label="Hide the notice" />
          </div>
          <div className="space-y-4 px-5 pt-4 text-[14px] leading-[1.5] text-ink" style={{ paddingBottom: "max(32px, env(safe-area-inset-bottom))" }}>
            <div className="space-y-2">{rules}</div>
            <div>{checks}</div>
            {ack}
          </div>
        </Dialog>,
        document.body,
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

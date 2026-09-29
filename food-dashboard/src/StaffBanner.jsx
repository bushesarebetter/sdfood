import { useEffect } from "react";
import { useMeta } from "./useMeta";
import { isStaff, contactLine, reviewStatus, reviewGuidance, GUIDANCE, PUBLIC_RECORD_NOTE, USE_NOTE, auditPrint } from "./lib/staff";

/**
 * On every page of the City staff site, and it prints: downloads and printouts are likely public
 * records, what the list is and is not for, whom to write to, how to sign out, and whether the list
 * has passed the checks a public release would need, each open check as an instruction (the
 * "demonstration" one first when the City has recorded no request or TRUST Ordinance
 * determination). It cannot be dismissed.
 */
export default function StaffBanner({ fixed = false, compact = false }) {
  const meta = useMeta();
  const staff = isStaff(meta);
  // Every print from a staff page is logged with the sign-in's id, as a download is (the banner is on
  // every page, so this is the one place that sees them all). The compact banner shares the page.
  useEffect(() => {
    if (!staff || compact || typeof window === "undefined") return undefined;
    const onPrint = () => auditPrint(meta, window.location.pathname.slice(0, 120));
    window.addEventListener("beforeprint", onPrint);
    return () => window.removeEventListener("beforeprint", onPrint);
  }, [staff, compact, meta]);
  if (!staff) return null;
  const contact = contactLine(meta);
  const open = reviewStatus(meta).length;
  const guidance = reviewGuidance(meta);
  // A POST from this page: the server signs out only on a same-site POST, so no link elsewhere can do it.
  const signOut = (
    <form method="post" action="/logout" className="inline">
      <button type="submit" className="whitespace-nowrap border-b border-ink/40 font-semibold text-ink hover:border-ink">Sign out</button>
    </form>
  );
  if (compact) {
    const demo = guidance[0] === GUIDANCE.demonstration ? guidance[0] : null;
    return (
      <div role="note" className="border border-ink bg-paper-edge px-3 py-2 text-[13px] leading-[1.45] text-ink">
        <span className="font-semibold">For City of San Diego staff.</span> {demo && <>{demo} </>}{PUBLIC_RECORD_NOTE} {signOut}
      </div>
    );
  }
  return (
    <div role="note" className={`border-b border-ink bg-paper-edge px-4 py-2 text-[13px] leading-[1.5] text-ink ${fixed ? "shrink-0" : ""}`}>
      <div className="mx-auto max-w-[76rem] md:px-4">
        <span className="font-semibold">For City of San Diego staff.</span> {PUBLIC_RECORD_NOTE} {USE_NOTE}
        {contact && <> Questions and corrections: {contact}.</>}
        {open > 0 && <> This list has not passed {open} of the checks a public release would need (see About this site).</>}
        {" "}{signOut}
        {guidance.length > 0 && (
          <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
            {guidance.map((g) => <li key={g}>{g}</li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

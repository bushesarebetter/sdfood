import { useMeta } from "./useMeta";
import { isStaff, contactLine, reviewStatus, reviewGuidance, PUBLIC_RECORD_NOTE, USE_NOTE } from "./lib/staff";

/**
 * On every page of the City staff site, and it prints: downloads and printouts are public records,
 * what the list is and is not for, whom to write to, how to sign out, and whether the list has
 * passed the checks a public release would need. It cannot be dismissed.
 */
export default function StaffBanner({ fixed = false, compact = false }) {
  const meta = useMeta();
  if (!isStaff(meta)) return null;
  const contact = contactLine(meta);
  const open = reviewStatus(meta).length;
  const guidance = reviewGuidance(meta);
  const signOut = <a href="/logout" className="whitespace-nowrap border-b border-ink/40 font-semibold text-ink hover:border-ink">Sign out</a>;
  if (compact) {
    return (
      <div role="note" className="border border-ink bg-paper-edge px-3 py-2 text-[13px] leading-[1.45] text-ink">
        <span className="font-semibold">For City of San Diego staff.</span> {PUBLIC_RECORD_NOTE} {signOut}
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

import { useMeta } from "./useMeta";
import { isStaff } from "./lib/staff";
import { useStaffNotice, showStaffNotice } from "./useStaffNotice";

/**
 * On the staff site, once the notice bar is closed with its ×: "Staff notice", which brings the bar back
 * with the whole notice open, and sign-out, which lived in the bar. Nothing while the bar shows, and
 * nothing on the public site. A sign-out is a POST: the server signs out only on a same-site POST.
 */
export default function StaffNoticeLinks({ className = "" }) {
  const meta = useMeta();
  const { hidden } = useStaffNotice();
  if (!isStaff(meta) || !hidden) return null;
  const link = "whitespace-nowrap border-b border-ink/25 pb-px text-[13px] text-ink-2 hover:border-ink hover:text-ink";
  return (
    <span className={`print-hide inline-flex shrink-0 items-center gap-4 ${className}`}>
      <button type="button" onClick={() => showStaffNotice()} className={link}>Staff notice</button>
      <form method="post" action="/logout" className="inline">
        <button type="submit" className={`${link} font-semibold text-ink`}>Sign out</button>
      </form>
    </span>
  );
}

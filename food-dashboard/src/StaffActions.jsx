import { useMeta } from "./useMeta";
import { isStaff, contactLine } from "./lib/staff";
import { SITE } from "./site";

const LINK = "border-b border-ink/25 text-ink hover:border-ink";

/**
 * The City does not inspect restaurants; the County does. So on the staff site every place says
 * where a question about it goes: a resident's report or a suspected illness to the County, a
 * question about the County's record to its duty specialist, an error on this site to its contact.
 */
export default function StaffActions({ large = false }) {
  const meta = useMeta();
  if (!isStaff(meta)) return null;
  const r = SITE.regulator;
  const contact = contactLine(meta);
  return (
    <div className={`leading-[1.55] text-ink-2 ${large ? "text-[14.5px]" : "text-[13.5px]"}`}>
      <p className="label mb-2">What to do with a question about this place</p>
      <ul className="space-y-1.5">
        <li>A resident reports a problem here: the County takes food complaints at{" "}
          <a href={r.complaintsUrl} target="_blank" rel="noopener noreferrer" className={LINK}>its complaint page</a> or {r.complaintsPhone}.</li>
        <li>Someone got sick after eating here: the County&rsquo;s foodborne illness line, {r.illnessPhone}.</li>
        <li>The County&rsquo;s record looks wrong: the {r.dutyName}, {r.phone}, <a href={`mailto:${r.email}`} className={LINK}>{r.email}</a>.</li>
        <li>This site is wrong{contact ? <>: {contact}</> : ": the contact on the privacy page"}.</li>
      </ul>
    </div>
  );
}

import { useMeta } from "./useMeta";
import { isStaff, contactLine } from "./lib/staff";
import { SITE } from "./site";

const LINK = "border-b border-ink/25 text-ink hover:border-ink";

/**
 * The City does not inspect restaurants; the County does. So on the staff site every place says
 * where a question about it goes: a resident's report or a suspected illness to the County, pests
 * outside a building to County Vector Control, a question about the County's record to its duty
 * specialist, an error on this site to its contact. A sick resident is given the County's number:
 * relaying their health details would put medical information in a City record.
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
        <li>A resident reports a problem here: the County takes food complaints on{" "}
          <a href={r.complaintsUrl} target="_blank" rel="noopener noreferrer" className={LINK}>its online form</a>, at{" "}
          <a href={`mailto:${r.complaintsEmail}`} className={LINK}>{r.complaintsEmail}</a> or {r.complaintsPhone}. It no longer
          accepts anonymous complaints and needs a name plus a phone number or email.</li>
        <li>Someone got sick after eating here: call 911 in a medical emergency. Otherwise the County&rsquo;s Epidemiology
          Liaison at {r.illnessPhone} takes reports, or email <a href={`mailto:${r.illnessEmail}`} className={LINK}>{r.illnessEmail}</a>.
          Give a sick resident the County&rsquo;s number rather than relaying their health details, which would put medical
          information in a City record.</li>
        <li>Rats, mice or flies outside a building: {r.vectorName}, {r.vectorPhone}.</li>
        <li>The County&rsquo;s record looks wrong: the {r.dutyName}, {r.phone}, <a href={`mailto:${r.email}`} className={LINK}>{r.email}</a>.</li>
        <li>This site is wrong{contact ? <>: {contact}</> : ": the contact on the privacy page"}.</li>
      </ul>
    </div>
  );
}

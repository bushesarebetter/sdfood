import PageFrame from "./PageFrame";
import { useMeta, useMode } from "./useMeta";
import { fmtDate } from "./lib/dates";
import { REPO_URL } from "./constants";
import { SITE, STUDENT_NOTE } from "./site";

const ANALYTICS_SRC = import.meta.env.VITE_ANALYTICS_SRC || "";

// A dated record of what changed on the site, newest first.
const CHANGES = [
  ["2026-09-24", "Version 3. Every listed place's County records are shown one record at a time with the County's own status text, and the site's readings are labelled \"Our reading\". Each place's record loads on its own. No list shows a position. The published rule and its bands appear only in a bands export. System fonts replace Google Fonts, and the offline copy checks the network first for data."],
  ["2026-09-21", "First version, with invented sample data."],
];

function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function Section({ heading, children }) {
  return (
    <section className="mb-9 last:mb-0">
      <h2 className="label mb-2">{heading}</h2>
      <div className="space-y-3 font-serif text-[16px] leading-[1.6] text-ink-2">{children}</div>
    </section>
  );
}

const Link = ({ href, children }) => (
  <a href={href} target="_blank" rel="noopener noreferrer" className="border-b border-ink/25 text-ink hover:border-ink">
    {children}
  </a>
);
const Mail = ({ to }) => <a href={`mailto:${to}`} className="border-b border-ink/25 text-ink hover:border-ink">{to}</a>;

export default function Privacy({ onNavigate }) {
  const meta = useMeta();
  const mode = useMode();
  const contact = typeof meta?.contact === "string" && meta.contact.trim() ? meta.contact.trim() : null;
  const operator = meta?.operator && (meta.operator.name || meta.operator.contact) ? meta.operator : null;
  const r = SITE.regulator;
  const authorsRoute = contact ? <>write to <Mail to={contact} /></> : <>open an issue at <Link href={`${REPO_URL}/issues`}>the project&rsquo;s GitHub issues</Link></>;
  const go = (p) => (e) => { e.preventDefault(); onNavigate(p); };

  return (
    <PageFrame onNavigate={onNavigate}>
      <p className="label mb-4">Updated {fmtDate(CHANGES[0][0])}</p>
      <h1 className="mb-10 font-serif text-[36px] font-medium leading-[1.08] tracking-[-0.02em] text-ink sm:text-[44px]">Privacy, terms and corrections</h1>

      <Section heading="What this site collects">
        <p>
          Nothing of its own. There is no account and no cookie set by this site. The one form, &ldquo;Near an address&rdquo;, sends
          what you type to Google, as you type, to suggest addresses and then to locate the one you choose; this site stores none of it.
          Three settings live in your browser&rsquo;s local storage: whether you have seen the first-visit note, whether you dismissed
          the cookie note, and whether you chose technical wording.
        </p>
        {ANALYTICS_SRC ? (
          <p>Page views are counted by a script loaded from {hostOf(ANALYTICS_SRC)}. It records the page, the referrer and a coarse location; it does not set a cookie.</p>
        ) : (
          <p>No analytics script runs on this site.</p>
        )}
      </Section>

      <Section heading="The copy kept in your browser">
        <p>
          The site installs a service worker so it opens quickly and works offline. It keeps, in your browser&rsquo;s Cache Storage, the
          site&rsquo;s own code and images, and the data files you have opened: the list, the export&rsquo;s description and each
          place&rsquo;s record you viewed (up to 300 of them, for up to a week). It always asks the network for data first and uses the
          copy only when the network does not answer. Nothing about you is in it.
        </p>
        <p>
          To clear it, clear this site&rsquo;s data in your browser&rsquo;s settings (in Chrome and Edge: Settings, Privacy, Site data;
          in Safari: Settings, Advanced, Website Data), or remove the installed app.
        </p>
      </Section>

      <Section heading="Fonts">
        <p>The site uses the fonts already on your device. It requests no font from Google Fonts or any other font service.</p>
      </Section>

      <Section heading="Google Maps">
        <p>
          The basemap and Street View are drawn by Google Maps, loaded from Google&rsquo;s servers when the map opens. Google receives
          your IP address and the map tiles you request, and may set its own cookies. <Link href="https://policies.google.com/privacy">Google&rsquo;s privacy policy</Link> covers that.
        </p>
      </Section>

      <Section heading="Hosting">
        <p>
          The site is served by {SITE.host.name}, which keeps ordinary web-server logs: IP address, request path and time.{" "}
          <Link href={SITE.host.privacyUrl}>{SITE.host.name}&rsquo;s privacy policy</Link> covers those.
        </p>
      </Section>

      <Section heading="The County's words and ours">
        <p>
          Every record comes from <Link href={r.resultsUrl}>{r.resultsName}</Link>, the County&rsquo;s published inspection results, and
          council districts from SANDAG. Nothing else goes in: no reviews, no owners&rsquo; names, no phone numbers.
        </p>
        <p>
          <b className="font-semibold text-ink">The County&rsquo;s, verbatim:</b> each record&rsquo;s visit date, visit type, status text,
          score and grade, and each item&rsquo;s text and severity. Each County record is its own row; none is merged with another for
          display.
        </p>
        <p>
          <b className="font-semibold text-ink">The site&rsquo;s own readings,</b> labelled &ldquo;Our reading&rdquo; where they appear:
          a routine inspection retyped as a re-grade or reopening visit, the reason given for a closure, the theme each item is put under,
          and the record flags the filters use{mode === "bands" ? "; and the published rule's points and bands, which are the site's alone" : ""}.
        </p>
      </Section>

      <Section heading="Corrections">
        <p>
          <b className="font-semibold text-ink">If this site differs from {r.resultsName},</b> that is ours to fix: {authorsRoute}. We check
          the place against {r.resultsName}, correct the next export, and list the change in the{" "}
          <a href="/corrections" onClick={go("/corrections")} className="border-b border-ink/25 text-ink hover:border-ink">corrections log</a>.
        </p>
        <p>
          <b className="font-semibold text-ink">If {r.resultsName} itself is wrong,</b> the County&rsquo;s record is the one to correct.
          Ask the County&rsquo;s {r.dutyName}: {r.phone}, <Mail to={r.email} />. Once the County corrects its record, the next export
          drawn from it carries the correction.
        </p>
        {mode === "bands" && (
          <p>
            <b className="font-semibold text-ink">A place&rsquo;s points or band.</b> An owner or manager may ask for a review{" "}
            {contact ? <>at <Mail to={contact} /></> : <>through the project&rsquo;s GitHub issues</>}. We recount each item on the
            place&rsquo;s worksheet against the County&rsquo;s record and answer within five business days. While a review is open, a
            listing that rests on a single inspection is suspended: the place shows &ldquo;Under review&rdquo; and its record, with no
            band or points. The outcome goes in the corrections log.
          </p>
        )}
      </Section>

      <Section heading="Terms of use">
        <p>
          {STUDENT_NOTE} The site is provided as is and without warranty of any kind. It is not a {SITE.county} assessment and does not
          replace one. A place that is not listed is not rated safe or unsafe. The County&rsquo;s{" "}
          <Link href={r.resultsUrl}>inspection search</Link> is the record of reference, and where a record here differs from it, the
          County&rsquo;s is right.
        </p>
        <p>
          You may quote or reuse the list with attribution, and only with its list date attached
          {meta?.generated ? <> (this export: {fmtDate(meta.generated)})</> : null}. Do not reuse it after it expires
          {meta?.expires ? <> ({fmtDate(meta.expires)})</> : null}. The downloaded spreadsheet carries both dates on every row. The code
          is released under the MIT licence at <Link href={REPO_URL}>GitHub</Link>.
        </p>
      </Section>

      <Section heading="Operator and legal notices">
        {operator ? (
          <p>
            Operated by {operator.name ?? "the approved operator"}
            {operator.contact ? <>; legal notices to <Mail to={operator.contact} /></> : null}.
          </p>
        ) : (
          <p>Not set: this export is not approved for publication.</p>
        )}
      </Section>

      <Section heading="Contact">
        <p>
          The authors are {SITE.authors}. For the County&rsquo;s record, the County&rsquo;s {r.dutyName}; for this site,{" "}
          {contact ? <Mail to={contact} /> : <Link href={`${REPO_URL}/issues`}>GitHub issues</Link>}.
        </p>
      </Section>

      <Section heading="Changes">
        <ul className="space-y-2">
          {CHANGES.map(([date, what]) => (
            <li key={date}><b className="tnum font-semibold text-ink">{fmtDate(date)}.</b> {what}</li>
          ))}
        </ul>
      </Section>
    </PageFrame>
  );
}

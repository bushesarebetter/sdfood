import PageFrame from "./PageFrame";
import { isStaff, PUBLIC_RECORD_NOTE, USE_NOTE, COOKIE_NOTE_STAFF } from "./lib/staff";
import { useMeta, useMode } from "./useMeta";
import { fmtDate } from "./lib/dates";
import { REPO_URL } from "./constants";
import { SITE, STUDENT_NOTE } from "./site";

const ANALYTICS_SRC = import.meta.env.VITE_ANALYTICS_SRC || "";

// A dated record of what changed on the site, newest first.
const CHANGES = [
  ["2026-09-29", "Version 4. The rule is now the simplest one that did as well as the others: points are how far a restaurant's average routine score over two years fell below 100, and the worksheet lists the scores it averages. Bands are kept only where they held at every backtest date, and every scored place shows what places with about its points did. Places outside the City are described by rates measured outside the City. The City staff site shows who is responsible, that downloads are likely public records, and every check the list has not passed; it keeps no offline copy. An owner or manager may ask whether their business is on the staff site, and every such request puts its points and band on hold the same business day."],
  ["2026-09-24", "Version 3. Every listed place's County records are shown one record at a time with the County's own status text, and the site's readings are labelled \"Our reading\". Each place's record loads on its own. No list shows a position. The students' point rule and its bands appear only in a bands export. System fonts replace Google Fonts, and the offline copy checks the network first for data."],
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
  // A public export names a contact as a string; the staff copy of meta.json (publish_city_site.py) as {name, email}.
  const rawContact = typeof meta?.contact === "string" ? meta.contact : meta?.contact?.email;
  const contact = typeof rawContact === "string" && rawContact.trim() ? rawContact.trim() : null;
  const operator = meta?.operator && (meta.operator.name || meta.operator.contact || meta.operator.email)
    ? { ...meta.operator, contact: meta.operator.contact ?? meta.operator.email } : null;
  const staff = isStaff(meta);
  const r = SITE.regulator;
  // A report about a place goes by email, like an owner's question: a public issue would publish it.
  const authorsRoute = contact || SITE.ownerContact ? <>write to <Mail to={contact || SITE.ownerContact} /></>
    : <>email the authors (the address appears here once the site&rsquo;s operator sets it; please do not open a public GitHub issue about a business)</>;
  // An owner's question about their business is never asked in public: an email, or nothing yet.
  const ownerMail = contact || SITE.ownerContact;
  const ownerRoute = ownerMail ? <>email <Mail to={ownerMail} /></> : <>email the authors (the address appears here once the site&rsquo;s operator sets it)</>;
  const NOT_ISSUES = "Please do not open a GitHub issue about a business: issues are public.";
  const go = (p) => (e) => { e.preventDefault(); onNavigate(p); };

  return (
    <PageFrame onNavigate={onNavigate}>
      <p className="label mb-4">Updated {fmtDate(CHANGES[0][0])}</p>
      <h1 className="mb-10 font-serif text-[36px] font-medium leading-[1.08] tracking-[-0.02em] text-ink sm:text-[44px]">Privacy, terms and corrections</h1>

      {staff && (
        <Section heading="The City staff site">
          <p>
            You sign in with a City staff sign-in. Under your sign-in id the server logs each sign-in and sign-out with its network
            address, each unsuccessful sign-in with the name typed and the address, each place record opened and each list file fetched, each
            address lookup (not what you typed), and each CSV download and print. The logs are kept by the site&rsquo;s host. The site keeps no offline copy: it removes
            any service worker and marks every data file not to be stored. On a shared computer, use Sign out at the top of any page, then
            close the browser.
          </p>
          <p>
            &ldquo;Near an address&rdquo; sends what you type to this site&rsquo;s own server, which looks it up with OpenStreetMap&rsquo;s
            Nominatim and, if that finds nothing, the US Census Bureau&rsquo;s geocoder. Results &copy; OpenStreetMap contributors.
          </p>
        </Section>
      )}

      <Section heading="What this site collects">
        {staff ? (
          <p>
            Nothing of its own beyond the staff sign-in above. There is no account apart from that sign-in. {COOKIE_NOTE_STAFF} The one
            form, &ldquo;Near an address&rdquo;, goes through this site&rsquo;s own server, as described above; the server keeps only the
            access log, which records by sign-in each data file fetched and each list downloaded or printed. Three
            settings live in your browser&rsquo;s local storage: whether you have seen the first-visit note, whether you dismissed the
            cookie note, and whether you chose technical wording.
          </p>
        ) : (
          <p>
            Nothing of its own. There is no account and no cookie set by this site. The one form, &ldquo;Near an address&rdquo;, sends
            what you type to Google, as you type, to suggest addresses and then to locate the one you choose; this site stores none of it.
            Three settings live in your browser&rsquo;s local storage: whether you have seen the first-visit note, whether you dismissed
            the cookie note, and whether you chose technical wording.
          </p>
        )}
        {ANALYTICS_SRC ? (
          <p>Page views are counted by a script loaded from {hostOf(ANALYTICS_SRC)}. It records the page, the referrer and a coarse location; it does not set a cookie.</p>
        ) : (
          <p>No analytics script runs on this site.</p>
        )}
      </Section>

      {staff ? (
        <Section heading="No offline copy">
          <p>
            The staff site keeps no copy in your browser: it removes any service worker an earlier visit installed and marks every data
            file not to be stored. Sign out clears the site from the browser.
          </p>
        </Section>
      ) : (
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
      )}

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
          and the record flags the filters use{mode === "bands" ? "; and the students' point rule's points and bands, which are the site's alone" : ""}.
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
            <b className="font-semibold text-ink">A place&rsquo;s points or band.</b> An owner or manager may ask for a review:{" "}
            {ownerRoute}. {NOT_ISSUES} Every request goes on hold the
            same business day it arrives: the place shows &ldquo;Under review&rdquo; and its record, with no band or points. We recount
            each item on the place&rsquo;s worksheet against the County&rsquo;s record and answer within five business days. The outcome
            goes in the corrections log.
          </p>
        )}
      </Section>

      <Section heading="The City staff version">
        <p>
          The authors also run a sign-in site for City of San Diego staff that shows, for each restaurant, the County&rsquo;s record and
          points from the students&rsquo; point rule. An owner or manager may ask whether their business appears and see exactly what it
          shows: {ownerRoute} with its name and address. {NOT_ISSUES} We answer by email within five business days, and from the day
          we receive the request its points and band are withheld from the staff site and its worklists.
        </p>
      </Section>

      <Section heading="Terms of use">
        <p>
          {STUDENT_NOTE} The site is provided as is and without warranty of any kind. It is not a {SITE.county} assessment and does not
          replace one. A place that is not listed is not rated safe or unsafe. The County&rsquo;s{" "}
          <Link href={r.resultsUrl}>inspection search</Link> is the record of reference, and where a record here differs from it, the
          County&rsquo;s is right.
        </p>
        {staff ? (
          <p>
            {PUBLIC_RECORD_NOTE} {USE_NOTE} The list carries its date and expiry on every downloaded row; do not
            use it after it expires{meta?.expires ? <> ({fmtDate(meta.expires)})</> : null}.
          </p>
        ) : (
        <p>
          You may quote or reuse the list with attribution, and only with its list date attached
          {meta?.generated ? <> (this export: {fmtDate(meta.generated)})</> : null}. Do not reuse it after it expires
          {meta?.expires ? <> ({fmtDate(meta.expires)})</> : null}. The downloaded spreadsheet carries both dates on every row. The code
          is released under the MIT licence at <Link href={REPO_URL}>GitHub</Link>.
        </p>
        )}
      </Section>

      <Section heading="Operator and legal notices">
        {operator ? (
          <p>
            Operated by {operator.name ?? "the approved operator"}{operator.role ? <> ({operator.role})</> : null}
            {operator.contact ? <>; legal notices to <Mail to={operator.contact} /></> : null}.
            {meta?.sunset ? <> The staff site comes down on {fmtDate(meta.sunset)} unless a City owner takes it over.</> : null}
          </p>
        ) : (
          <p>Not set: this export is not approved for publication.</p>
        )}
      </Section>

      <Section heading="Contact">
        <p>
          The authors are {SITE.authors}. For the County&rsquo;s record, the County&rsquo;s {r.dutyName}; for this site,{" "}
          {contact ? <Mail to={contact} /> : <><Link href={`${REPO_URL}/issues`}>GitHub issues</Link> for anything that is not about a particular business</>}.
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

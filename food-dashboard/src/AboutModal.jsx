import Dialog, { CloseButton } from "./Dialog";
import { useAdvanced } from "./useAdvanced";
import { useExpired, useMeta, useMode, useSample } from "./useMeta";
import {
  GROUP_NOTE, auditedBandsName, bandDefs, bandPoints, bandSummary, backtestList, costLimitSentence, driftLines, frozenLine, persistenceSentence,
  rateRatio, restRate, restRatio, routeSentence, ruleSentence, utilityRows,
} from "./lib/bands";
import { isStaff, reviewStatus } from "./lib/staff";
import { gradeContextSentence } from "./lib/framing";
import { OUR_READING } from "./lib/inspections";
import { fmtDate } from "./lib/dates";
import { REPO_URL } from "./constants";
import { SITE, STUDENT_NOTE } from "./site";

const DOCS = {
  modelCard: `${REPO_URL}/blob/main/docs/MODEL_CARD.md`,
  contract: `${REPO_URL}/blob/main/docs/FOOD_DATA_CONTRACT.md`,
};

const pct = (x) => (typeof x === "number" ? `${Math.round(x * 100)}%` : "");
const rule = (s) => s.replace(/\.$/, "");
const sentence = (s) => (s ? `${s.charAt(0).toUpperCase()}${s.slice(1)}` : s);
const num = (x) => (typeof x === "number" ? x.toLocaleString("en-US") : "");
const isRange = (iv) => Array.isArray(iv) && iv.length === 2 && iv.every((x) => typeof x === "number");
/** "1.2 to 2.6"; with `floor`, a low end below it (a widened interval can reach below 0) shown at it. */
const ratioRange = (iv, { floor = null } = {}) => (isRange(iv) ? `${floor != null ? Math.max(floor, iv[0]) : iv[0]} to ${iv[1]}` : "");

/** Under the district table: a finding from the statistics review, stated as what it is. */
const CUISINE_NOTE =
  "A rough check by restaurant name, not a validated measure, suggests that among restaurants with no major violation at their next " +
  "routine inspection, those serving some cuisines are put in band 1 about twice as often as others; it comes through the County's " +
  "scores, which the rule passes on unchanged, and may reflect how items are cited.";

/**
 * About this site. Everything it says about the export is read from
 * meta.json, so the page cannot drift from the data it describes. In
 * `record` mode it covers the source, the data rules and what the site is
 * not; `bands` mode adds the students' point rule, its bands and their backtest.
 */
export default function AboutModal({ onClose, onNavigate }) {
  const { advanced } = useAdvanced();
  const meta = useMeta();
  const mode = useMode();
  const sample = useSample();
  const expired = useExpired();

  const link = (path, label) => (
    <a
      href={path}
      onClick={(e) => {
        if (!onNavigate) return;
        e.preventDefault();
        onClose();
        onNavigate(path);
      }}
      className="border-b border-ink/25 text-ink-2 hover:border-ink hover:text-ink"
    >
      {label}
    </a>
  );

  return (
    <Dialog titleId="about-title" onClose={onClose} className="max-w-[42rem]">
      <div className="flex items-start justify-between gap-4 border-b border-rule-strong px-7 py-5">
        <div>
          <p className="label mb-2">{advanced ? "Methodology" : "About this site"}</p>
          <h2 id="about-title" className="font-serif text-[26px] font-medium leading-[1.15] text-ink focus:outline-none">
            {mode === "bands" ? "The County's record, and the students' point rule over it" : "The County's inspection record, place by place"}
          </h2>
        </div>
        <CloseButton onClose={onClose} />
      </div>

      <div className="px-7 py-6">
        {sample && (
          <p className="mb-6 border border-band-2 px-4 py-3 font-serif text-[15px] leading-[1.55] text-ink">
            This is the site with invented data. Every place, address, inspection and figure shown is made up so the
            pages could be built and reviewed. Nothing here describes a real business.
          </p>
        )}

        <Section heading="What it shows">
          <p>
            Restaurants, limited-preparation food places and markets with a deli or food processing in the{" "}
            {SITE.fullName}{meta?.card?.outside ? <> (and, with the area switch, the rest of {SITE.county})</> : null}, visited
            by the County in the last 18 months, whose {SITE.regulator.resultsName} entry was not marked expired when the
            results were collected (the County says permit status is not reported online): each
            place's County records since January 2023, the County's status text for each, scores, grades, and the items
            inspectors cited in the three years before the last visit.
            {meta?.inspections_through && <> Inspections run through {fmtDate(meta.inspections_through)}.</>}
          </p>
          <p>{gradeContextSentence(meta)}</p>
        </Section>

        <Section heading="Source">
          <p>
            {sentence(meta?.source?.name ?? SITE.regulator.resultsName)}. Council districts come from SANDAG. Nothing else goes in:
            no reviews, no owners&rsquo; names, no phone numbers.
          </p>
        </Section>

        <Section heading="The County's words and ours">
          <p>
            Shown as the County published them: each record&rsquo;s date, visit type, status text (such as
            &ldquo;Complete&rdquo;, &ldquo;Ordered Closed&rdquo; or &ldquo;Approved to Reopen&rdquo;), score, grade, and
            each item&rsquo;s text and severity.
          </p>
          <p>
            Marked &ldquo;Our reading&rdquo; wherever they appear: re-grade or reopening visits ({rule(OUR_READING.followup)}),
            closure reasons, the theme of each item ({rule(OUR_READING.themes)}), and the record flags used by the filters (
            {rule(OUR_READING.flags)}){mode === "bands" ? "; and the points and bands of the students' point rule, which are ours entirely" : ""}.
          </p>
          <p>
            Dropped as not inspections: &ldquo;No Access&rdquo;, &ldquo;Self Closed&rdquo; and &ldquo;Status
            Verification&rdquo; visits. A score of 0 means not scored, and no grade is ever made from a score.
          </p>
        </Section>

        {mode === "bands" && <Rule meta={meta} advanced={advanced} expired={expired} />}

        <Section heading="Limits">
          <p>
            A finding is what one inspector recorded at one visit, and the public record does not say which inspector made
            it. The County&rsquo;s published record starts in January 2023.
          </p>
          {mode === "bands" && meta?.survivorship && <p>{meta.survivorship}</p>}
          {meta?.expires && (
            <p>
              This export is shown until {fmtDate(meta.expires)}. After that the site offers only a search of the record it
              holds, because the County&rsquo;s record will have moved on.
            </p>
          )}
        </Section>

        <Section heading="What it is not">
          <p>
            {STUDENT_NOTE} It is not a County assessment, and a place that is not listed is not rated safe or unsafe. Where a
            record here differs from {SITE.regulator.resultsName}, the County&rsquo;s is the record of reference.
          </p>
        </Section>
      </div>

      <p className="flex flex-wrap gap-x-5 gap-y-1 border-t border-rule px-7 py-4 text-[13px] text-ink-2">
        {link("/privacy", "Privacy, terms and corrections")}
        {link("/corrections", "Corrections log")}
        {mode === "bands" && <Ext href={DOCS.modelCard}>Model card</Ext>}
        <Ext href={DOCS.contract}>Data contract</Ext>
        <Ext href={SITE.regulator.resultsUrl}>The County&rsquo;s inspection search</Ext>
        <Ext href={REPO_URL}>Code on GitHub</Ext>
      </p>
    </Dialog>
  );
}

function Rule({ meta, advanced, expired }) {
  const card = meta?.card;
  const items = card?.items ?? [];
  const bands = bandDefs(meta);
  const rest = restRate(meta);
  const restX = restRatio(meta);
  const base = typeof card?.base_rate === "number" ? card.base_rate : null;
  const cr = meta?.catch_run;
  const utility = utilityRows(meta);
  const limit = costLimitSentence(meta);
  const byRoute = routeSentence(meta);
  const drift = driftLines(meta);
  return (
    <>
      <Section heading="The students' point rule (not a County grade or rating)">
        <p>{ruleSentence(meta)}</p>
        {frozenLine(meta) && <p>{frozenLine(meta)} Each list applies this version to the County&rsquo;s record as it stands on the list date.</p>}
        {drift.map((l) => <p key={l} className="text-ink">{l}</p>)}
        {typeof card?.eligibility === "string" && <p>It scores {card.eligibility.replace(/\.$/, "")}. Every other place carries no points.</p>}
        {items.length > 0 && (
          <Table
            head={["Count from the record", "Weight"]}
            rows={items.map((it) => [
              <>{it.label}{advanced && <span className="ml-1.5 font-mono text-[12px] text-ink-3">{it.item}</span>}</>,
              `${it.weight}${it.unit ? ` ${it.unit}` : ""}`,
            ])}
          />
        )}
        <p>
          The places with the most points are cut into bands by points, so places with equal points are always in the same
          band. Within a band, lists are ordered by points, then name.
          {expired && " This export is out of date, so its bands are not shown now."}
        </p>
      </Section>

      {bands.length > 0 && (
        <Section heading="What the bands have been worth">
          <p>
            The rule was applied to the record as it stood on {cr?.as_of ? fmtDate(cr.as_of) : "an earlier date"}, from only
            what was known then{typeof cr?.eligible === "number" ? `, for ${num(cr.eligible)} scored places` : ""}, and checked against each
            place&rsquo;s next routine inspection in the year that followed ({backtestList(meta)}).
          </p>
          <Table
            head={advanced ? ["Band", "Points", "Places now", "Labelled", "With a major", "Rate [95%]", `× ${base != null ? "all scored" : "below"}`, "Kept"] : ["Band", "Points", "Places now", "Had a major", base != null ? "Times the rate for all scored" : "Times the rate below"]}
            rows={[
              ...bands.map((b) => advanced
                ? [b.band, bandPoints(meta, b.band) ?? "", num(b.places_now), num(b.labelled), num(b.positives), `${pct(b.rate)}${Array.isArray(b.interval) ? ` [${pct(b.interval[0])}, ${pct(b.interval[1])}]` : ""}`, rateRatio(meta, b.band) ?? "", typeof b.kept_in_refits === "number" ? pct(b.kept_in_refits) : ""]
                : [`Band ${b.band}`, bandPoints(meta, b.band) ?? "", num(b.places_now), pct(b.rate), rateRatio(meta, b.band) ?? ""]),
              ...(rest != null ? [advanced ? ["below", "", "", num(card?.rest?.labelled), num(card?.rest?.positives), pct(rest), restX ?? "", ""] : ["Scored places below the bands", "", "", pct(rest), restX ?? ""]] : []),
              ...(base != null ? [advanced ? ["all scored", "", "", "", "", pct(base), "1", ""] : ["All scored restaurants", "", "", pct(base), "1"]] : []),
            ]}
            note={advanced ? "Rates at the next routine inspection in the backtest, Wilson 95% intervals. Kept: the share of a band's places that refits of the rule on resampled data keep in the band." : "The share of each band's places that had a major violation at their next routine inspection in the backtest."}
          />
          <p>{bandSummary(meta, "1")}</p>
          {byRoute && <p>{byRoute}</p>}
          <p>{GROUP_NOTE}</p>
        </Section>
      )}

      {Array.isArray(card?.by_origin) && card.by_origin.length > 0 && (
        <Section heading="How the bands were checked">
          <p>
            Places are cut into bands at fixed shares of the list, chosen before any outcome was looked at. A split between two
            bands is kept only if the higher band&rsquo;s rate was above the lower one&rsquo;s at every backtest date, and clearly
            so when the dates are pooled. Otherwise the two are one band. So there may be one band, or several.
          </p>
          <Table
            head={["Backtest date", ...bands.map((b) => `Band ${b.band}`), "Below the bands"]}
            rows={card.by_origin.map((o) => [fmtDate(o.as_of), ...bands.map((b) => (o[b.band]?.rate != null ? pct(o[b.band].rate) : "")),
                                               o.rest?.rate != null ? pct(o.rest.rate) : ""])}
            note="The share with a major at the next routine inspection, among places scored as of each date."
          />
        </Section>
      )}

      {curveRows(card).length > 0 && (
        <Section heading="What the points say, place by place">
          <p>
            Every scored place is also given an estimate: what places with about its points did in the backtest, read from a
            monotone fit to the counts below: more points never means a lower rate, and where the counts cannot tell point values apart their rate is pooled, so it levels off where the rates do. Each estimate comes with a likely range.
            {card && "curve_closure" in card && (
              <> There are two fits: one for places whose two scored years include no closure, and one for places whose two years
                include a routine inspection that ended in a closure, which the rule counts as 70; each place is read from its own,
                and an estimate from the second says so.</>
            )}{" "}
            The counts themselves:
          </p>
          <Table head={["Points", "Places", "Had a major", "Rate"]} rows={curveRows(card)} />
        </Section>
      )}

      {persistenceSentence(meta) && (
        <Section heading="Compared with what the record already shows">
          <p>{persistenceSentence(meta)}</p>
        </Section>
      )}

      {(utility || limit) && (
        <Section heading="When a band would be named">
          <p>
            Naming a band is worth it only if enough of its places go on to have a major. Call B the benefit of naming a place that
            does, and C the cost of naming one that does not: the share must be above C/(B+C). A band is named only when the low end
            of its interval clears that bar for a cost ratio C/B that someone at the City sets.{limit && <> {limit}</>}{" "}
            {typeof meta?.cost_ratio === "number"
              ? <>The cost ratio set for this list is {meta.cost_ratio}.</>
              : <>No one at the City has set a cost ratio for this list.</>}{" "}
            Bands support no decision about a business and no comparison between districts.
          </p>
          {utility && (
            <Table
              head={["Cost ratio C/B", "Bar C/(B+C)", "Bands that clear it"]}
              rows={utility.map((u) => [String(u.cost_ratio), pct(u.bar), u.named.length ? u.named.map((b) => `Band ${b}`).join(", ") : "none"])}
            />
          )}
          {utility && utility.every((u) => !u.named.length) && <p>No band clears any of these.</p>}
        </Section>
      )}

      {card?.outside && (
        <Section heading="Outside the City">
          <p>
            The rule and its band edges come from the City. For places elsewhere in {SITE.county} they were checked again on
            restaurants outside the City, at the same backtest dates.{" "}
            {card.outside.bands_shown
              ? "The bands held there too, so places outside the City are shown in bands, described by the rates measured outside the City."
              : "The bands did not hold there, so places outside the City show their points and estimate but no band."}
            {typeof card.outside.base_rate === "number" && <> Outside the City, {pct(card.outside.base_rate)} of scored restaurants had a major at their next routine inspection.</>}
          </p>
        </Section>
      )}

      {meta?.fairness?.by_district && Object.keys(meta.fairness.by_district).length > 0 && (
        <DistrictTable meta={meta} />
      )}

      {isStaff(meta) && reviewStatus(meta).length > 0 && (
        <Section heading="What this list has not passed">
          <p>A public release of this list would need every check below to pass. The staff site shows the list anyway, with this said:</p>
          <ul className="list-disc space-y-1 pl-5">{reviewStatus(meta).map((r, i) => <li key={i}>{r}</li>)}</ul>
        </Section>
      )}
    </>
  );
}

/** A curve's counts by points (`bins`), as table rows. */
const binRows = (c) => (Array.isArray(c?.bins) ? c.bins : []).map((b) => [
  b.min_points === b.max_points ? `${b.min_points}` : `${b.min_points} to ${b.max_points}`, num(b.labelled), num(b.positives), pct(b.rate),
]);

/** A curve's row of totals, headed by the places it covers. */
const totalRow = (c, label) => [
  <span className="font-semibold">{label}</span>, num(c?.labelled), num(c?.positives),
  typeof c?.labelled === "number" && c.labelled > 0 && typeof c?.positives === "number" ? pct(c.positives / c.labelled) : "",
];

/**
 * The counts under the estimate curves. An export with `curve_closure` fits `curve` to the places
 * whose two scored years include no closure, so each curve is headed by the places it covers, the
 * closure curve (when there is one) second; an older export's one curve covers every scored place.
 */
function curveRows(card) {
  if (!card) return [];
  const plain = binRows(card.curve);
  if (!("curve_closure" in card)) return plain;
  const rows = plain.length ? [totalRow(card.curve, "Places whose two scored years include no closure"), ...plain] : [];
  if (card.curve_closure) rows.push(totalRow(card.curve_closure, "Places whose two years include a closure counted as 70"), ...binRows(card.curve_closure));
  return rows;
}

/**
 * The backtest by council district (`meta.fairness.by_district`): the places in the audited bands,
 * how many had a major, the district's share of the wrongly named over its share of the labelled
 * scored places with its 95% and family-wise intervals (the family-wise one also widened for an
 * assumed design effect of 2, allowing for inspectors, when the export has it), and the
 * false-positive rate against the City's. A column the export has no figure for is left out.
 */
function DistrictTable({ meta }) {
  const f = meta.fairness;
  const rows = Object.entries(f.by_district).filter(([d]) => d !== "None");
  const any = (test) => rows.some(([, r]) => test(r ?? {}));
  const family = any((r) => isRange(r.interval_family));
  const deff = any((r) => isRange(r.interval_family_deff));
  const fpr = any((r) => typeof r.fpr_ratio === "number");
  const bands = auditedBandsName(meta).toLowerCase();
  return (
    <Section heading="By council district">
      <p>
        For a list of named places, the harm is a place in a band that then had no major: a wrongly named place. By council
        district, in the backtest, for places in {bands}: how many there were, how many had a major, and the district&rsquo;s share
        of the wrongly named over its share of the labelled scored places (the scored places whose next routine inspection is
        known), where 1 is even{fpr ? "; and, of its labelled places with no major, the share in a band over the same share for the City" : ""}.
      </p>
      <Table
        head={[
          "District", "In a band", "Had a major", "Its share of the wrongly named, over its share of the labelled scored places",
          ...(family ? ["Family-wise"] : []), ...(deff ? ["Allowing for inspectors (an assumed design effect of 2)"] : []),
          ...(fpr ? ["Of its places with no major, the share in a band, over the City's"] : []),
        ]}
        rows={rows.map(([d, r]) => [
          `District ${d}`, num(r.named),
          typeof r.precision === "number" ? `${pct(r.precision)}${isRange(r.precision_interval) ? ` (${pct(r.precision_interval[0])} to ${pct(r.precision_interval[1])})` : ""}` : "",
          typeof r.false_share_ratio === "number" ? `${r.false_share_ratio}×${isRange(r.interval) ? ` (${ratioRange(r.interval)})` : ""}` : "",
          ...(family ? [ratioRange(r.interval_family)] : []), ...(deff ? [ratioRange(r.interval_family_deff, { floor: 0 })] : []),
          ...(fpr ? [typeof r.fpr_ratio === "number" ? `${r.fpr_ratio}×` : ""] : []),
        ])}
        note={
          "Had a major: the share of the district's places in a band that had one at their next routine inspection, with its likely range. " +
          "Beside the share ratio, its 95% interval for that district alone" +
          (family ? "; family-wise, a wider interval that holds for all the districts at once, since one district in nine can look high by chance" : "") +
          (deff ? "; allowing for inspectors, the family-wise interval widened as if there were half as many places (an assumed design effect of 2), " +
            "since places one inspector visits may be cited alike and the record does not say which inspector made a visit, shown from 0 where the widening reaches below it" : "") +
          ". 1 is even."
        }
      />
      {Array.isArray(f.problems) && f.problems.length > 0 && (
        <p>Uneven: {f.problems.join("; ")}. Part of a district&rsquo;s gap may be how its inspectors cite, not its restaurants: the record does not say which inspector made a visit.</p>
      )}
      <p>{CUISINE_NOTE}</p>
    </Section>
  );
}

function Ext({ href, children }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="border-b border-ink/25 text-ink-2 hover:border-ink hover:text-ink">
      {children}
    </a>
  );
}

function Section({ heading, children }) {
  return (
    <section className="mb-6 last:mb-0">
      <h3 className="label mb-2">{heading}</h3>
      <div className="space-y-3 font-serif text-[15px] leading-[1.6] text-ink-2">{children}</div>
    </section>
  );
}

function Table({ head, rows, note }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full font-sans text-[13px] leading-[1.4]">
        <thead>
          <tr className="border-b border-rule-strong text-left">
            {head.map((h, i) => (
              <th key={i} scope="col" className={`label py-1.5 pr-3 ${i ? "text-right" : ""}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, j) => (
            <tr key={j} className="border-b border-rule align-baseline">
              {r.map((c, i) => (
                <td key={i} className={`py-1.5 pr-3 ${i ? "tnum whitespace-nowrap text-right" : "text-ink"}`}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {note && <p className="mt-1.5 font-sans text-[13px] text-ink-2">{note}</p>}
    </div>
  );
}

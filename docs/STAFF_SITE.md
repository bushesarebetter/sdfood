# The City staff site: who may use it, and for what

The staff site (`https://sdfood-city.onrender.com`, behind a sign-in) is the food-dashboard with the
real export. It shows every listed restaurant and market in San Diego County with the County's
inspection record, and scores restaurants with the students' point rule. This page is its use policy.
The site links to it, and `publish_city_site.py` will not publish without the approval it describes.
How to run it is in [RUNBOOK.md](RUNBOOK.md); how it is built and hosted is in [HOSTING.md](HOSTING.md).

## What it is, and what it is not

- **It is** a student analysis of the County's published inspection results (SD Food Info), shown
  record by record, with a transparent point rule whose every point can be checked by hand.
- **It is not** a City or County finding about any business, a County grade or rating, or an
  inspection schedule. The County, not the City, inspects restaurants. Nothing here changes what an
  inspector does.
- **The rule is a summary, not a better predictor.** Ranking the same restaurants by their recent
  major violations, which the County's record already shows, picks out a group with about the same
  rate. The point rule's value is that anyone can see and check why a place scores what it does.

## Who may use it

City of San Diego staff, each with their own sign-in (`SITE_USERS` on the service), issued only:

1. after a responsible adult is named in `docs/STAFF_APPROVAL.json` (the students are minors: a minor
   can disaffirm an agreement, so the City needs an adult it can hold to these terms);
2. after someone at the City has asked for access in writing (`city_requestor`); and
3. after the City has said whether its TRUST Ordinance (San Diego Municipal Code §§ 210.0101–
   210.0112, on surveillance technology) applies (`trust_determination`). If it does, the City needs
   Privacy Advisory Board review (§ 210.0104) and a Council vote (§ 210.0106) before any staff use,
   even of a free tool: record the vote in `council_approval`. Until then, the method and the
   counts-only dashboard can be shown, but not the named list. The server enforces it: until
   `access_approved` (a request with its name and date, and a TRUST answer of "does not apply", or
   "applies" with the Council's approval), only the site's operators (`SITE_OPERATORS` on the service:
   the people who build and check it) see the named list; a City sign-in issued early sees why, not
   the list. Every page also says the site is a demonstration until then.

One sign-in per person, never shared, under a pseudonymous id (`u01`, `u02`, ...) whose key the
City's owner of the site keeps. Remove a person's sign-in the day they leave. A sign-in lasts until
"Sign out", 30 idle minutes or 10 hours. Under each id the host's logs record every sign-in and
sign-out with its network address, every unsuccessful sign-in with the name typed, every place record
opened (each place's file is fetched when it is opened, so the log does show which places a person
opened, though the list itself loads every name and band at once), every address lookup (not what
was typed), and every CSV download and print.

## What it is for

| Use | Why it fits |
|---|---|
| Answering a constituent who asks about a place | The County's full record, in one page, with where to send a complaint (every place page says) |
| Seeing a council district's pattern | District views and the About page's district table |
| Preparing a conversation with the County | The method, the backtest, and the three questions only the County can answer ([outreach.md](../outreach.md)) |
| City programs with their own authority | For example, the grease-control program: the record shows sewage and grease-trap citations (item 22) |

## What it is not for

Never use a band, points or an estimate for a permit, licence, code-enforcement, grant, procurement,
hiring or public-statement decision about a business, or to contact a business about its band. Do not
forward names or bands outside the City. Places outside the City are shown for reference only; the
City has no role there.

## Public records

"Internal" is not a legal category. What City staff download, print, copy, screenshot or send from the
site, and their messages about it on any account or device (*City of San Jose v. Superior Court*
(2017) 2 Cal.5th 608), are likely City public records under the California Public Records Act (Gov.
Code § 7920.530) and may have to be released on request. Nothing on the site makes them confidential:
its use rules are use rules, not a promise of confidentiality, and a disclosure to any member of the
public waives an exemption (§ 7921.505). The site says so on every page. That is why every downloaded
row carries its list's date, expiry and run and what its band means, why a band is described as a
statistic about a group, and why the students never promise a list will stay confidential.

## Corrections and disputes

- **The County's record is wrong:** the County's Food & Housing duty specialist, (858) 505-6900.
- **This site is wrong, or an owner disputes a place's points or band:** the corrections contact in
  `docs/STAFF_APPROVAL.json`, shown on the site. The place goes on hold (`docs/holds.json`) the same
  business day the request arrives, with `publish_city_site.py --holds-only`, which changes nothing
  else and needs no rebuild: it keeps its County record and loses its points and band until the
  review is done, and it moves to the end of every list and worklist, so its position does not give
  its points away. The worklists apply the same holds. The outcome goes in the corrections log.
- **How an owner can find out.** The site is behind a sign-in and staff do not contact businesses
  about bands, so the public site's privacy page says the staff version exists and how an owner or
  manager can ask, by email only (`VITE_OWNER_CONTACT` on the public site; never a public GitHub
  issue, which would publish the business's band), whether their business appears and see exactly
  what it shows; the answer comes by email within five business days, and the place is held from the
  day the request arrives.

## What staff are told the list has not passed

The staff site does not wait for the public-release gates ([PUBLISHING.md](PUBLISHING.md)); it says
what has not been done, on every page (the banner, as instructions) and in full (About this site):

- in plain words, from `docs/STAFF_APPROVAL.json`: no City request for access or TRUST Ordinance
  determination on record (until both are, the banner calls the site a demonstration, not a City
  tool), no lawyer has reviewed naming these businesses, the County has not commented, no business on
  the list has been told, and whether the operator is a student author;
- whether the County's record has moved since the rule was frozen (`meta.drift`), so the rates may be
  out of date;
- every public-release gate the list fails. Today these include that the points do no better than a
  place's recent major violations, that no band clears an approved cost ratio, and that some council
  districts get more than their share of places in a band that then had no major (the district table,
  with intervals). Part of a district's gap may be how its inspectors cite, not its restaurants: the
  record does not say which inspector made a visit.

## The pilot

While a silent pilot runs ([PILOT.md](PILOT.md)), no band may reach an inspector or a County
supervisor from this site: the pilot's result would then measure the list's influence, not its
accuracy. The access log shows which place records each person opened and which lists they
downloaded, so the analysis can report the result with and without the inspections at places staff
had opened.

## Sunset

The staff site comes down on the `sunset` date in `docs/STAFF_APPROVAL.json` (at most a year ahead),
unless a City owner has taken it over (a named office that will run the refresh, or the County's own
data feed replaces the scraper). `publish_city_site.py` refuses to publish after that date, and the
server itself closes the data the day after it, whatever was last deployed. How to hand it over or
take it down: [RUNBOOK.md](RUNBOOK.md).

## Where the data lives

The real export, the pulls and the worklists sit in `data/` on the machine that runs the refresh, and
in the private deploy repository. They must never enter the public repository. A school-district
OneDrive is a poor home for them: the district controls, monitors and eventually deletes the account.
Move `data/` (and the private checkout) to storage the responsible adult controls, and ask the school
in writing whether this is a school activity.

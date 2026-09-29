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
3. after the City has said whether its TRUST Ordinance (San Diego Municipal Code ch. 2, art. 10,
   div. 1, on surveillance technology) applies (`trust_determination`). Until then, the method and the
   counts-only dashboard can be shown, but not the named list.

One sign-in per person, never shared. Remove a person's sign-in the day they leave. Every record
opened is logged with the sign-in's name (the host's logs).

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

"Internal" is not a legal category. Anything City staff download, print, paste or send from the site
can be a City public record under the California Public Records Act (Gov. Code §7920.530), and anyone
may request it. The site says so on every page. That is why every downloaded row carries its list's
date, expiry and run, why a band is described as a statistic about a group, and why the students never
promise a list will stay confidential.

## Corrections and disputes

- **The County's record is wrong:** the County's Food & Housing duty specialist, (858) 505-6900.
- **This site is wrong, or an owner disputes a place's points or band:** the corrections contact in
  `docs/STAFF_APPROVAL.json`, shown on the site. The place goes on hold (`docs/holds.json`) within one
  business day: at the next `publish_city_site.py`, which needs no rebuild, it keeps its County record
  and loses its points and band until the review is done. The outcome goes in the corrections log.

## What staff are told the list has not passed

The staff site does not wait for the public-release gates ([PUBLISHING.md](PUBLISHING.md)); it shows
which of them the list fails, on every page (the banner) and in full (About this site). Today these
include that no rule is within 0.01 AUC of the best model, and that some council districts get more
than their share of places in a band that then had no major (the district table). Part of a district's
gap may be how its inspectors cite, not its restaurants: the record does not say which inspector made
a visit.

## The pilot

While a silent pilot runs ([PILOT.md](PILOT.md)), no band may reach an inspector or a County
supervisor from this site: the pilot's result would then measure the list's influence, not its
accuracy. The access log lets the analysis report the result with and without inspections at places
staff had looked at.

## Sunset

The staff site comes down on the `sunset` date in `docs/STAFF_APPROVAL.json`, unless a City owner has
taken it over (a named office that will run the refresh, or the County's own data feed replaces the
scraper). `publish_city_site.py` refuses to publish after that date.

## Where the data lives

The real export, the pulls and the worklists sit in `data/` on the machine that runs the refresh, and
in the private deploy repository. They must never enter the public repository. A school-district
OneDrive is a poor home for them: the district controls, monitors and eventually deletes the account.
Move `data/` (and the private checkout) to storage the responsible adult controls, and ask the school
in writing whether this is a school activity.

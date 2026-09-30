# The City staff site: who may use it, and for what

The staff site (`https://sdfood-city.onrender.com`, behind a sign-in) is the food-dashboard with the
real export. It shows every listed restaurant and market in San Diego County with the County's
inspection record, and scores restaurants with the students' point rule. This page is its use policy.
The site links to it, and `publish_city_site.py` will not publish without the approval it describes.
How to run it is in [RUNBOOK.md](RUNBOOK.md); how it is built and hosted is in [HOSTING.md](HOSTING.md).

## What it is, and what it is not

- **It is** a student analysis of the County's published inspection results (SD Food Info), shown
  record by record, with a transparent point rule whose every point can be checked by hand, offered
  to City staff (no City office uses it yet). Independent student project, not affiliated with or
  endorsed by the City of San Diego or the County of San Diego.
- **It is not** a City or County finding about any business, a County grade or rating, or an
  inspection schedule. The County, not the City, inspects restaurants. Nothing here changes what an
  inspector does.
- **The rule is a summary, not a better predictor.** Ranking the same restaurants by their recent
  major violations, which the County's record already shows, picks out a group with about the same
  rate. The point rule's value is that anyone can see and check why a place scores what it does.

## Who may use it

City of San Diego staff, each with their own sign-in (a sign-in id and an access token, `SITE_USERS` on
the service; never a City account), issued only:

1. after a responsible adult is named in `docs/STAFF_APPROVAL.json` (the students are minors: a minor
   can disaffirm an agreement, so the City needs an adult it can hold to these terms);
2. after someone at the City has asked for access in writing (`city_requestor`: their name, and the
   date they asked); and
3. after the City has said whether its TRUST Ordinance (San Diego Municipal Code §§ 210.0101–
   210.0112, on surveillance technology) applies (`trust_determination`: the answer, who at the City
   gave it, and when). If it does, the City needs Privacy Advisory Board review (§ 210.0104) and a
   Council vote (§ 210.0106) before any staff use, even of a free tool: record the vote in
   `council_approval` (the resolution, and the date of the vote). Until then, the method and the
   counts-only dashboard can be shown, but not the named list. The server enforces it: until
   `access_approved` (the request, with its name and date; and a TRUST answer of "does not apply",
   or "applies" with the Council's approval, with who gave it and when; every date YYYY-MM-DD on or
   before the day of publishing, so a date still to come or a placeholder such as "tbd" is not on
   record), only the site's operators (`SITE_OPERATORS` on the service: the people who build and
   check it) see the named list. The server opens it to anyone else only when `access_approved` is
   exactly `true`. A site sign-in issued early sees why (the Withheld page), not the list. Every
   page also says the site is a demonstration until then. The operator's own older sign-in
   (`SITE_PASSWORD`) is never given to anyone, and is an operator only while it is the only sign-in
   ([RUNBOOK.md](RUNBOOK.md), "Sign-ins").

One sign-in per person, never shared, under a pseudonymous id (`u01`, `u02`, ...) whose key (who is
who) the operator keeps until a City office owns the site. The id and its access token are this site's
own: any message that sends them says they are not the person's City account, and the sign-in page
says never to enter a City user name or password there. Remove a person's sign-in the day they leave.
A sign-in lasts until "Sign out", 30 idle minutes or 10 hours. Under each id the host's logs record
every sign-in and sign-out with its network address; every refused sign-in (a wrong id or token, or
too many tries) with the address, and the id typed only when it is one of the site's ids; every place
record opened (each place's file is
fetched when it is opened, so the log does show which places a person opened, though the list itself
loads every name and band at once); every address lookup (not what was typed); and every CSV download
and print (a list printout with how many places it lists, never the search typed). The log is kept in
the site's hosting account at Render, where the operator, and anyone with access to that account, can
read it; Render keeps it only briefly unless it is sent on to a log store. During a pilot it is used,
by sign-in id, to report the pilot's result with and without the places staff opened ("The pilot"
below). The sign-in page and the Withheld page say so before any record is made.

## What it is for

| Use | Why it fits |
|---|---|
| Answering a constituent who asks about a place | The County's full record, in one page, with where to send a complaint (every place page says) |
| Raising a council district's pattern with the County | The district view's counts of the County-record facts (majors, closures, B or C grades), and the selected district's facts as shares of its own places. They are what inspectors cite, and the record does not say which inspector made a visit: take a district's pattern to the County as a question, never as a ranking of districts |
| Preparing a conversation with the County | The method, the backtest, and the three questions only the County can answer ([outreach.md](../outreach.md)) |
| City programs with their own authority | For example, the grease-control program: the record shows sewage and grease-trap citations (item 22) |

## What it is not for

Never use a band, points or an estimate for a permit, licence, code-enforcement, grant, procurement,
hiring or public-statement decision about a business, or to contact a business about its band. Do not
forward names or bands outside the City. Places outside the City are shown for reference only; the
City has no role there.

## Reading a place's page

- **The County's words are shown as published:** each record's status ("Complete", "Ordered Closed",
  "Approved to Reopen", "Self Closed"), its inspection type ("Routine", "Re-inspection", "Site
  Investigation", "Environmental", "Status Verification") and its notes ("County note: Impoundment").
  What else the page says about a record is our reading, and marked so: a re-grade, a complaint or
  other field visit, a status verification (shown, never scored), a closure's reason, a "Self Closed"
  record with a major read as the operator's own closure, a closure read from a later "Approved to
  Reopen" ("Closure, our reading"), and an "Approved to Reopen" no closure could be placed before.
- **A closure with no reopening on record leads.** When a place's last closure has no "Approved to
  Reopen" and no graded visit after it, every view leads with it ("Ordered closed <month> <year>, no
  reopening on record"; "Self closed" when the operator's own closure is all that day holds, and
  "Closed" for a closure read from a later reopening), not with the letter from before the closure.
  The County posts no grade card while it has a place closed. The letter stays in the record and in
  the CSV's grade columns, and the CSV adds `open_closure_date`. The site never says a place is
  closed now: a later visit the County did not grade may have been its reopening, and the page lists
  those visits.
- **Counts say what they count.** "Since <month>: N reinspections; X 'Ordered Closed' records and Y
  closures in our reading", with any "Self Closed" closures, closures read from a reopening, and
  reopenings with no closure placed. Whenever the "Ordered Closed" records outnumber the closures
  that start at one, the page and the pasted text add the rule: a further order within 30 days of the
  last, with no reopening or graded visit between, is part of the same closure. A closure read as
  "permit" means no major was cited that day and a County note that day mentions a permit; one read
  as "other" means no major was cited that day and no County note that day mentions a permit (the
  County's record gives no reason): the page lists the items cited that day, or says none were.
- **"Copy the record"** (text to paste into a reply) lists every closure in the three years before
  the last visit, and every "Approved to Reopen" no closure could be placed before, in the same words
  as the page.
- **Items by theme** count every item in the 36 months before the last visit, even when the list of
  items is cut at 150 (majors first, then the newest; no place in the September 2026 pull has more
  than 83, so none is cut); a view that has to count from a cut list says so.
- **The last visit** is named in the County's words too: the staff CSV's `last_visit_type` gives our
  reading and the County's own type ("complaint or other field visit (our reading; County type: Site
  Investigation)").
- **What counts as 70.** A routine inspection that started a closure for a health hazard (a County
  closure order, the operator's own closure with a major cited, or a closure read from a later
  reopening) counts as 70 in the rule's average, every time: the County usually gives no score that
  day. The worksheet says "this rule counts it as 70", with the County's own score beside it when it
  gave one. A closure read as "permit" or "other" is not counted as 70: a routine that ended in one is
  averaged only if the County scored it.
- **An estimate names the group of points it is read from** ("with 7 to 25 points"): every place in
  a group gets the group's rate ([MODEL_CARD.md](MODEL_CARD.md), "Estimates").

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
  its points away. A held id that is not on the live list and that no publish has held (a typo), or
  one that differs from a listed id only in case, is refused before anything changes; an id a publish
  held before whose place has since left the list gets a warning ([RUNBOOK.md](RUNBOOK.md), "One
  place"). The worklists and the staff API apply the same holds. The frozen copies of a month's
  worklists kept for a pilot are read-only: a hold does not change them, and they are never shown to
  staff. The outcome goes in the corrections log.
- **How an owner can find out.** The site is behind a sign-in and staff do not contact businesses
  about bands, so the public site's privacy page says the staff version exists and how an owner or
  manager can ask, by email only (`VITE_OWNER_CONTACT`, set in the public site's environment on Render
  to the corrections contact's email, then "Save, rebuild, and deploy": [HOSTING.md](HOSTING.md),
  "The public site"; never a public GitHub issue, which would publish the business's band), whether
  their business appears and see exactly what it shows; the answer comes by email within five
  business days, and the place is held from the day the request arrives. Every staff publish reads
  the live public page and checks that it carries the corrections contact's email; until it does,
  the staff notice lists that as an open item ("the public site does not yet give an owner an email
  address to ask whether their business is on this list").

## What staff are told the list has not passed

The staff site does not wait for the public-release gates ([PUBLISHING.md](PUBLISHING.md)); it says
what has not been done, on every page (the staff bar counts the open checks, and its notice gives them
as instructions) and in full (About this site):

- in plain words, from `docs/STAFF_APPROVAL.json`: no City request for access or TRUST Ordinance
  determination on record (until both are, the staff bar calls the site a demonstration, not a City
  tool), no lawyer has reviewed naming these businesses, the County has not commented, no business on
  the list has been told, and whether the operator is a student author; and, checked on the live
  public site at each publish, whether its privacy page gives an owner an email address to ask;
- whether the County's record has moved since the rule was frozen (`meta.drift`), so the rates may be
  out of date. Before the formal check can run (it needs a complete quarter after the backtest year,
  counted 30 days after it ends: the first counts from January 30, 2027), the export's drift note on
  the latest quarter becomes an instruction too ("every rate on this site is probably low", or high),
  without counting as an open check;
- when the monitor finds that a list it has scored on later inspections did not hold up as its
  backtest said (`meta.monitor`, [RUNBOOK.md](RUNBOOK.md), "Reading the monitor"), an instruction to
  read the rates and bands with that in mind, again not counted as an open check;
- every public-release gate the list fails. Today these include that the points do no better than a
  place's recent major violations, that no band clears an approved cost ratio, and that some council
  districts get more than their share of places in a band that then had no major (the district table,
  with intervals). Part of a district's gap may be how its inspectors cite, not its restaurants: the
  record does not say which inspector made a visit. The district view says the same of its counts on
  every staff export.

The notice opens by itself on the first page after each sign-in (the server empties the browser's
session storage at every sign-in, so the next person on a shared computer meets it open) and stays
open until "I have read this". The bar's × counts as read and closes the bar for the rest of that
browser session; "Staff notice" in the masthead then brings it back with the notice open. Every
printout carries the whole notice, whether the bar is showing or not. On a phone, or any window under
768 pixels wide, the bar keeps the same line and the notice opens as a full-screen sheet; that layout
offers no CSV download and no list printout (a browser print is still logged). Every print is logged
once, from any layout: a place or page under its address, and "Print this list" (beside the list's CSV
download) under the list's name with how many places it lists. That printout holds every row of the
filtered and sorted list, not only the 50 on screen, with its scope, dates, the use rule and the
public-record note.

## The pilot

While a silent pilot runs ([PILOT.md](PILOT.md)), no band may reach an inspector or a County supervisor
from this site: the pilot's result would then measure the list's influence, not its accuracy. The
access log shows which place records each person opened and which lists they downloaded or printed, so
the analysis can report the result with and without the inspections at places staff had opened.

## Sunset

The staff site comes down on the `sunset` date in `docs/STAFF_APPROVAL.json` (at most a year ahead),
unless a City owner has taken it over (a named office that will run the refresh, or the County's own
data feed replaces the scraper). `publish_city_site.py` refuses to publish after that date, and the
server itself closes the data the day after it, whatever was last deployed. How to hand it over or
take it down: [RUNBOOK.md](RUNBOOK.md).

## Where the data lives

The real export, the pulls and the worklists sit in `data/` on the machine that runs the refresh. The
private deploy repository holds the export the site serves and, in `ops/`, what it takes to rebuild it:
the source of the site and of the list, the frozen rule, the pull's meta (not the pull itself), the
approval, the holds (with the record of every id a publish has held on its list), the monitor's
output and every archived list, which the prospective test and the monitor score and no later export
can rebuild. The pulls and the worklists are not there. None of it
may ever enter the public repository. A school-district OneDrive is a poor home for them: the district
controls, monitors and eventually deletes the account. Move `data/` (and the private checkout) to
storage the responsible adult controls, and ask the school in writing whether this is a school
activity.

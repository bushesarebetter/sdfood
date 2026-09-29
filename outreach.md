# Outreach kit: San Diego food inspections, for City staff

For City of San Diego staff and council offices. Fill in the `[brackets]`. Link the research
dashboard (`dashboard.html`, `[dashboard link]`; counts only, no facility rows), never the public
site. The staff site's address may go to a City requestor; its sign-ins go only to named staff, after
the steps in [docs/STAFF_SITE.md](docs/STAFF_SITE.md). Every number here is from the README,
docs/MODEL_CARD.md and FAIRNESS.md. When quoting days sooner, say what they are: about 2% of the
277–303 days between a facility's routine inspections, found earlier within the month; never
prevented illness.

## Three questions only the County can answer

The County's Food, Water and Housing Division does the inspecting. Before any pilot we need to know:

1. **How are routine inspections assigned?** By inspector territory, by facility category, or both?
2. **Who sets the order within the month?** The inspector, a supervisor, or a system?
3. **Which system holds the schedule,** and could a monthly list be read into it?

---

## Email to City staff

**Subject:** The County's food-inspection record, place by place, for City staff: looking for an owner

Hi [Name],

We are Chenhao Zhang and Ayan Pendharkar, two high-school students at Canyon Crest Academy. From the
County's published food-inspection results we built a site for City staff. For every restaurant and
market in the City (and, with a switch, the rest of the county) it shows the County's full
inspection record on one page, where to send a resident's complaint, and a simple point rule that
marks the places whose record points to a major violation at the next routine inspection, with each
point explained. The County is the data source and the inspecting agency. We are independent and not
affiliated with or endorsed by the County of San Diego.

The site exists, behind a sign-in (https://sdfood-city.onrender.com), but no one at the City has
access yet, and no one will until:

1. someone at the City asks for it in writing and names the office that would own it;
2. the City tells us whether its TRUST Ordinance (surveillance technology) applies; and
3. our adult point of contact, [NAME, ROLE], has agreed a one-page data-use note with you.

What it shows, checked on inspections it had never seen:

- **The rule is one line.** Points are how far a restaurant's average routine score over two years
  fell below 100. Restaurants with 8 or more points (an average of 92 or lower) had a major violation
  at their next routine inspection at about 1.7 times the rate of all scored restaurants: about 37 in
  100 against 21, and the pattern held at every backtest date. Sorting by recent major violations does
  about as well; the rule's value is that anyone can check why a place scores what it does.
- **Ordering a month's routine inspections the same way** would have found major violations about
  6 days sooner within a council district's month than the order actually worked (about 2% of the
  time between a facility's routine inspections).
- **No detectable coverage gap across neighborhood income** (FAIRNESS.md). Some council districts
  get more than their share of marked places that then had no major; the site shows which.

What we are asking for:

- **An owner.** A City office willing to own the tool, or to tell us it is not useful. We are
  students; the site comes down on [sunset date] unless someone takes it over.
- **Five users for two weeks,** then 30 minutes on what food-safety questions reach your office,
  and whether this helps answer them.
- **The TRUST Ordinance answer,** before anyone signs in.

Please treat anything downloaded or printed from the site as a City record: it may be released under
the Public Records Act. Brief each council office separately; for the Council as a body, we would
share only the counts-only summary: [dashboard link].

Thank you,
Chenhao Zhang and Ayan Pendharkar, Canyon Crest Academy
[email] · Adult point of contact: [NAME, ROLE, EMAIL]

## Follow-up (a week later, same thread)

Hi [Name], floating this back up. The short version: a site that puts the County's inspection record
for every City restaurant on one page, with a one-line rule anyone can check, ready for five City
users once an office owns it. Happy to send a one-page summary instead of a call. Chenhao and Ayan

## Note to the County (before anything is published)

**Subject:** Request for comment: an analysis of your published food-inspection results

Hi [Name],

We are two students at Canyon Crest Academy (Chenhao Zhang and Ayan Pendharkar). Using your
published results on SD Food Info, we tested whether ordering each month's routine inspections by
each facility's own record would find major violations sooner. We have built a sign-in site for City
staff, which we will open only after the City asks for it and names an owner, and we would like your
comment before anything is published.
We are independent, not affiliated with or endorsed by the County.

- **What we saw in your published record:** apart from school kitchens, whose twice-yearly
  inspections federal law requires for schools in the national school lunch program, how often a
  place is routinely inspected differs little by kind of place (low-risk facilities every 315 days,
  restaurants every 312), and a B or C may be re-graded within 30 days. The next routine came a median 277 days after one that found a
  major, against 303 after one that did not. Within a month, the order inspections were done in did
  not put the places with worse records first; ordering by the facility's average routine score
  would have found major violations about 5.8 days sooner in a council district's month, about 2% of
  that interval. We would like to know whether that matches how you schedule.
- **What we would like to learn:** the three questions at the top of this kit.
- **What would make it better:** your inspection data through an official extract, including
  inactive permits, and **inspector or territory ids**, which let an analysis separate a place
  from its inspector. With your data we would use your actual inspector assignments, not council
  districts. A records request is drafted below; we would gladly use whatever route you prefer.
- **Our commitment:** our repository's public website shows only invented sample data, and no
  real names will be published from your data without your review.

Thank you,
Chenhao Zhang and Ayan Pendharkar · Adult point of contact: [NAME, ROLE, EMAIL]

---

## The 20-second version

> "San Diego did about 18,700 routine food inspections in 2025. How often each place is inspected
> is the County's call, and we leave it alone. We tested ordering each month's inspections by each
> facility's own record:
> a one-line rule, lowest average routine score first, would have found major violations about
> six days sooner within a council district's month, on the County's own 2025-26 data: about 2%
> of the time between a facility's routine inspections. A silent
> pilot could confirm it without changing a single inspection."

## If they ask

- **"Is it reliable?"** It was tested forward in time: built on 2023-24, checked on 32,548 routine
  inspections from 2025-26. Accuracy holds across three separate cutoffs (AUC 0.72 to 0.76), and
  the main comparisons carry 95% intervals. The top 20% of the list finds major violations at 2.4 times
  the base rate. It reorders visits everyone already gets; it skips no one.
- **"Do you need the model?"** Mostly not. The one-line rule reaches 48% in the top 20% against
  the model's 49%, and 5.8 of the model's 6.4 days. The model's edge is real (the intervals exclude
  zero) but small: about 0.6 day, some 0.2% of the time between routine inspections.
- **"Will it prevent food poisoning?"** We can't show that, and neither could a pilot this size:
  foodborne illness is rare, under-reported and hard to trace to one visit, and the public record
  has no illness data. What the ordering changes is timing. A major violation is corrected at the
  inspection that finds it, so finding it about 6 days sooner means about 6 fewer days of an
  uncorrected major, with the same inspectors, schedule and number of visits. Summed over the
  majors, the one-line rule's head start comes to about 13,800 facility-days a year (95% CI 12,900
  to 14,700), if each violation was already there at the start of the month. It is a free scheduling change,
  not a proven health intervention, and the silent pilot tests the timing before anything changes.
- **"Is the list confidential?"** No, and we never promise it is. What City staff download, print
  or send is a City record and may be released under the Public Records Act. That is why every
  downloaded row carries its date, expiry and run, and why a band is described as a statistic about a
  group, never a finding about one place.
- **"Who runs it after you graduate?"** Whoever owns it at the City, or no one: the site comes down on
  its sunset date unless a City office takes it over. The refresh is one command
  (`refresh_city_site.py`, docs/RUNBOOK.md), and an official County data feed would replace the scraper.
- **"Why two sets of numbers?"** The research numbers score each routine inspection county-wide.
  The students' point rule scores City restaurants monthly and asks whether the next routine inspection
  within a year finds a major; it is shown as bands. Both say a facility's own record is a strong
  guide.
- **"Does it target poor or immigrant neighborhoods?"** From FAIRNESS.md: flag rates and actual
  rates were both nearly flat across ZIP income, and under a single top-20% cut the model found
  46% to 52% of each income quartile's major violations (the rule 44% to 52%). The gap between the
  lowest- and highest-income quartiles is +3.4 points for the model (95% CI −4.6 to +11.7) and
  +4.6 for the rule (−4.1 to +13.5): "no detectable difference", not proof of evenness. The rule's
  false-positive rate is 16.7% in the lowest-income quartile against 15.3% in the highest, with
  overlapping intervals. The model uses no ZIP code, and coverage by group is monitored in any pilot.
- **"What would it take?"** Someone has to produce and send each month's list. Our script builds
  the lists from refreshed data; someone at the County would still pass a district's list to its
  inspection supervisor. The estimate assumes a finding does not depend on the day of the month, and it
  ignores routing: a reordered month may cost more driving, which an active pilot would measure.
- **"What can't public data show?"** SD Food Info lists only facilities that exist today, so every
  test here is on survivors; places that closed are missing. Even if a fifth more inspections came
  from closed places ranked as badly as possible, the top 20% would still hold about twice its
  share of major violations. The County's full records remove the question.
- **"What do you want?"** Twenty minutes, the County's comment, and, if it is useful, a silent
  pilot.

---

## Records request template (California Public Records Act)

Send to the County of San Diego, Department of Environmental Health and Quality, Food, Water and
Housing Division, through the County's Public Records Request Center, linked from the Department's
records page (https://www.sandiegocounty.gov/content/sdc/deh/doing_business/records.html). Fill in the
brackets.

> **Subject:** California Public Records Act request: food facility inspection data
>
> To the Custodian of Records, Department of Environmental Health and Quality:
>
> Under the California Public Records Act (Gov. Code sec. 7920.000 et seq.), I request copies of
> the following records, in an electronic format such as CSV or the format in which they are kept:
>
> 1. For every food facility permitted in San Diego County from January 1, 2020 to the date of
>    this request, **including facilities whose permits are inactive, expired or closed**: the
>    facility record id, name, address, business type, permit status, and the dates the permit was
>    issued and closed.
> 2. For every inspection of those facilities in that period: the facility record id, inspection
>    date, inspection type, status, score, grade, each violation cited with its severity (major or
>    minor), and any closure order.
> 3. For each inspection in item 2, if the Department holds or can extract such a field, the
>    **inspector or inspection territory** that performed it. A consistent anonymized id in place of
>    an inspector's name is acceptable.
> 4. Records showing how routine inspections are scheduled: the risk category assigned to each
>    facility, the routine inspection frequency for each category (FDA Retail Program Standard 3),
>    whether routine inspections are on schedule, the assignment of facilities to inspectors or
>    territories, and the monthly routine inspection schedules or work lists for [months].
>
> If any part is exempt, please release the rest and cite the exemption for what is withheld. If
> the records exist in a database, an export of the fields above is sufficient. Please tell me in
> advance if fees will exceed $[amount].
>
> This request is for independent, noncommercial research on inspection scheduling.
>
> Thank you,
> [NAME], [adult point of contact], on behalf of Chenhao Zhang and Ayan Pendharkar, Canyon Crest Academy
> [email] · [phone] · [mailing address]

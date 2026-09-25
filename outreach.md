# Outreach kit: San Diego food inspections, for City staff

For City of San Diego staff and council offices. Fill in the `[brackets]`. Link the
de-identified dashboard (`dashboard.html`, `[dashboard link]`), never the public site. Every number
here is from the README and FAIRNESS.md.

## Three questions only the County can answer

The County's Food & Housing Division does the inspecting. Before any pilot we need to know:

1. **How are routine inspections assigned?** By inspector territory, by facility category, or both?
2. **Who sets the order within the month?** The inspector, a supervisor, or a system?
3. **Which system holds the schedule,** and could a monthly list be read into it?

---

## Email to City staff

**Subject:** County food-inspection records and monthly worklists, by council district

Hi [Name],

We are Chenhao Zhang and Ayan Pendharkar, two high-school students at Canyon Crest Academy. From
the County's published food-inspection results we built an internal API for City staff. For each
council district it gives the County's inspection record for every listed restaurant and market,
a published scoring rule's points and bands, and a monthly worklist of the facilities due for a
routine inspection. It is a FastAPI service in our repository's `api/` folder, with interactive
documentation and access by key. The County remains the data source and the inspecting agency.
We are independent and not affiliated with or endorsed by the County of San Diego.

What we found, tested on 2025-26 inspections our methods had never seen:

- **Most of the gain needs no model.** Ordering a month's routine inspections by each facility's
  average routine score, lowest first, puts **48%** of major violations in the first 20% of
  inspections, and within a council district's month finds them **5.8 days sooner** than the
  order actually worked. Our model reaches 6.2 days.
- Restaurants in the published rule's top band had a major violation at their next routine
  inspection at **about twice the rate** of other restaurants (37.2% against 17.8%).
- Coverage is even across neighborhoods (details below).

The next step we would suggest is a silent pilot the City could propose to the County
(docs/PILOT.md): one or two district supervisors get a frozen list before each month, inspectors
change nothing, and after three months we compare when major violations would have been found in
the list's order with the order actually worked.

Two disclosures. Our data come from the County's public SD Food Info search; we would switch to an
official extract. And our repository also contains a public website that would show named City
restaurants from the County's data. Today it shows only invented sample data, and we will not
publish real names without the County's review.

A de-identified summary is here: [dashboard link]. Could we have 20 minutes to show you the API?

Thank you,
Chenhao Zhang and Ayan Pendharkar, Canyon Crest Academy
[email] · Adult point of contact: [NAME, ROLE, EMAIL]

## Follow-up (a week later, same thread)

Hi [Name], floating this back up. The short version: ordering each district's routine inspections
by each facility's own record would have found major violations about 6 days sooner within the
month, on the County's 2025-26 data, and a silent pilot could confirm it without changing any
inspection. Happy to send a one-page summary instead of a call. Chenhao and Ayan

## Note to the County (before anything is published)

**Subject:** Request for comment: an analysis of your published food-inspection results

Hi [Name],

We are two students at Canyon Crest Academy (Chenhao Zhang and Ayan Pendharkar). Using your
published results on SD Food Info, we tested whether ordering each month's routine inspections by
each facility's own record would find major violations sooner. We are sharing internal,
by-district tools with City staff, and we would like your comment before anything is published.
We are independent, not affiliated with or endorsed by the County.

- **What we saw:** routine cadence is set by category, and follow-up visits respond to findings.
  The next routine came a median 277 days after one that found a major, against 303 after one
  that did not. Within that schedule, ordering by the facility's average routine score found
  major violations about 5.8 days sooner in a council district's month.
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

> "San Diego did about 18,700 routine food inspections in 2025. The County sets how often by
> facility category. We tested ordering each month's inspections by each facility's own record:
> a one-line rule, lowest average routine score first, would have found major violations about
> six days sooner within a council district's month, on the County's own 2025-26 data. A silent
> pilot could confirm it without changing a single inspection."

## If they ask

- **"Is it reliable?"** It was tested forward in time: built on 2023-24, checked on 32,552 routine
  inspections from 2025-26. Accuracy holds across three separate cutoffs (AUC 0.72 to 0.76), and
  every comparison has a 95% interval. The top 20% of the list finds major violations at 2.4 times
  the base rate. It reorders visits everyone already gets; it skips no one.
- **"Do you need the model?"** Mostly not. The one-line rule reaches the same 48% in the top 20%
  and 5.8 of the model's 6.2 days. The model adds about 0.4 day.
- **"Why two sets of numbers?"** The research numbers score each routine inspection county-wide.
  The published rule scores City restaurants monthly and asks whether the next routine inspection
  within a year finds a major; it is shown as bands. Both say a facility's own record is a strong
  guide.
- **"Does it target poor or immigrant neighborhoods?"** From FAIRNESS.md: "Neither lower-income
  nor higher-Hispanic areas are over-targeted." "Under a single top-20% cut, the model finds 45% to
  51% of each income quartile's major violations and the one-line rule 45% to 51%, with the
  lowest-income quartile at the top of both ranges." The model uses no ZIP code.
- **"What would it take?"** Someone has to produce and send each month's list. Our script builds
  the lists from refreshed data; someone at the County would still pass a district's list to its
  supervisor. The estimate assumes a finding does not depend on the day of the month, and it
  ignores routing: a reordered month may cost more driving, which an active pilot would measure.
- **"What can't public data show?"** SD Food Info lists only facilities that exist today, so every
  test here is on survivors; places that closed are missing. Even if a fifth more inspections came
  from closed places ranked as badly as possible, the top 20% would still hold about twice its
  share of major violations. The County's full records remove the question.
- **"What do you want?"** Twenty minutes, the County's comment, and, if it is useful, a silent
  pilot.

---

## Records request template (California Public Records Act)

Send to the County of San Diego, Department of Environmental Health and Quality, Food and Housing
Division (use the County's public records request portal if it has one). Fill in the brackets.

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
> 3. For each inspection in item 2, the **inspector or inspection territory** that performed it.
>    A consistent anonymized id in place of an inspector's name is acceptable.
> 4. Records showing how routine inspections are scheduled: the routine inspection frequency by
>    facility category, the assignment of facilities to inspectors or territories, and the monthly
>    routine inspection schedules or work lists for [months].
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

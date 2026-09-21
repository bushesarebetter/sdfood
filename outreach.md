# Outreach kit — San Diego food-inspection risk model

Everything you need to take this to the people who could actually use it. Fill in the
`[brackets]`. Attach the dashboard link and (optionally) the repo.

---

## Who to contact (in order)

1. **County of San Diego — Dept. of Environmental Health & Quality (DEHQ), Food & Housing
   Division (FHD).** They run the inspections; they're the real owner of this idea. Look up the
   current **FHD Assistant Director / Division Chief** by name on the county site before sending —
   a named person beats a general inbox. Public FFIS/data contact as a starting relay:
   `fhdutyeh@sdcounty.ca.gov`.
2. **Your County Supervisor's office** (find your district at sandiegocounty.gov). Supervisors set
   priorities for county departments; a one-line nudge from them gets a department meeting fast.
   Use this if FHD goes quiet after two tries.
3. **UCSD / SDSU public-health or data-science faculty** — a co-sign or a class project gives the
   work institutional weight and a path to a proper internal validation.

## How to run it
- Send Email 1 to FHD. If no reply in ~1 week, send the 2-line bump. If still nothing after two
  weeks, send Email 2 to your Supervisor's office.
- Keep the first email short — the goal is a 15-minute call, not to explain everything.
- Lead with **reliability + efficiency** (catch problems sooner, same staff). Do **not** claim it
  prevents illnesses or saves a specific dollar amount — you can't prove that yet, and it invites
  attack. Offer to validate on their internal data.

---

## Email 1 — to FHD (the main ask)

**Subject:** A free way to catch critical food violations sooner — built on your public data

Hi [Name],

I'm Ayan Pendharkar, a San Diego resident with a background in machine learning. Using the Food &
Housing Division's own public inspection data, I built something I think could help your inspectors,
and I'd like 15 minutes to show you.

The division does roughly 21,000 routine inspections a year on a set schedule — a spotless bakery
gets visited about as often as a repeat offender. I built a model that scores each facility by how
likely it is to have a critical violation, so inspectors could take the riskiest ones first.

I tested it the honest way — trained it on 2023–2024, then checked it against 2025 inspections it
had never seen:

- Inspecting the **top 20% by risk** would have surfaced about **45% of all critical violations**.
- Reordering inspections by risk — same dates, same staff — would have caught critical violations
  about **6 days sooner on average**, while low-risk facilities waited under a day longer.

No new staff, no new system, no cost. It runs on data you already publish.

I know a model built from the outside has real limits, so I'd want to validate it against your fuller
internal records and add fairness checks before anything went live. This is a starting point, and I'm
offering it for free because I think it could help San Diegans.

Here's a short interactive summary: [dashboard link]. Could we set up a brief call?

Thank you for the work you do,
Ayan Pendharkar
[email] · [phone]

---

## Email 1 — follow-up bump (send ~1 week later, reply to the same thread)

Hi [Name] — just floating this back up. Happy to make it a 15-minute call or just send a one-page
summary, whichever is easier. The short version: risk-ranking your routine inspections would catch
critical violations ~6 days sooner at no added cost, tested on your own 2025 data. — Ayan

---

## Email 2 — to your County Supervisor's office (if FHD is unresponsive)

**Subject:** Constituent proposal — a free tool to improve county food-safety inspections

Hi [Supervisor's office],

I'm Ayan Pendharkar, a resident of District [#]. On my own, using the county's public food-inspection
data, I built and tested a tool that would help Environmental Health catch critical restaurant
violations sooner — about 6 days earlier on average — by inspecting the highest-risk facilities first,
at no added cost. It's tested on the county's own 2025 inspections.

I've reached out to the Food & Housing Division but haven't been able to connect. Would your office be
willing to point me to the right person, or take a quick look? A short summary is here: [dashboard link].

I'm not asking for money — just a chance to show it to the people who could use it.

Thank you,
Ayan Pendharkar
[email] · [phone]

---

## The 20-second version (for a call, a hallway, a comment)

> "San Diego does about 21,000 food inspections a year on a fixed schedule. I built a model, on the
> county's own public data, that ranks facilities by how likely they are to have a critical violation.
> Tested on 2025 inspections it had never seen, going in that order would've caught critical violations
> about six days sooner — same inspectors, same budget. I'd love to validate it on your internal data."

## If they ask the hard questions
- **"Is it reliable?"** Tested out-of-sample; accuracy is stable (AUC 0.73–0.75) across three separate
  time periods, not one lucky split. Code and method are public.
- **"Does it just target poor or immigrant neighborhoods?"** I tested this directly against Census
  income and ethnicity data. It does **not** — the model is calibrated across income and ethnicity
  (predicted risk matches actual violation rate in every group), and it actually flags lower-income
  ZIPs *less* often, because their real violation rates aren't higher. The one thing to manage is
  equal *coverage*: keep baseline routine inspections everywhere so lower-scored areas aren't
  neglected. Full numbers in FAIRNESS.md.
- **"What do you want?"** A pilot on your data, and a fair test. That's it.

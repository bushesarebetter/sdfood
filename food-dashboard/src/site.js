/**
 * Everything about this deployment that is a fact about the place rather than
 * about the interface. Another county changes this file, its export, and
 * nothing else.
 */
export const SITE = {
  name: "San Diego",
  fullName: "City of San Diego",
  county: "San Diego County",
  countyOfficial: "County of San Diego",
  siteTitle: "San Diego Food Inspection Record",
  shortTitle: "Food Inspection Record",
  siteUrl: "https://sd-food-safety-risk.onrender.com",

  // Who serves the site, for the privacy page. Change it with the host.
  host: { name: "Render", privacyUrl: "https://render.com/privacy" },

  center: { lat: 32.78, lng: -117.13 },
  bounds: { south: 32.53, west: -117.29, north: 33.12, east: -116.9 },

  // Council districts of the City of San Diego.
  districts: { count: 9, label: "Council district", short: "District" },

  // Who inspects, where their results live, and whom to call. The County
  // inspects retail food facilities in every city in the county, the City of
  // San Diego included.
  regulator: {
    name: "San Diego County Department of Environmental Health and Quality",
    short: "the County",
    resultsUrl: "https://www.sandiegocounty.gov/content/sdc/deh/fhd/ffis.html",
    resultsName: "SD Food Info",
    programUrl: "https://www.sandiegocounty.gov/content/sdc/deh/fhd/food/food.html",
    // The Food and Housing Division's duty specialist: questions about the
    // County's own record, and corrections to it.
    dutyName: "Food & Housing duty specialist",
    phone: "(858) 505-6900",
    email: "fhdutyeh@sdcounty.ca.gov",
    // Where a customer reports what they saw at a place. The County asks for
    // a name and a phone number or email; it does not take anonymous reports.
    complaintsUrl: "https://www.sandiegocounty.gov/content/sdc/deh/fhd/food/foodcomplaints.html",
    complaintsPhone: "(858) 505-6903",
    // Suspected food poisoning goes to the foodborne illness line.
    illnessPhone: "(858) 505-6814",
    grades: { A: "90 to 100", B: "80 to 89", C: "79 or below" },
    // The month the County's published inspection results begin.
    recordStart: "2023-01",
    // The County's rule for a major violation, stated wherever the share of
    // majors that still end with an A is given.
    majorRule:
      "The County requires each major violation to be corrected during the inspection, or the affected area is closed.",
    // The County's own disclaimer for SD Food Info, quoted as published
    // (complete sentences, unedited). Checked against the page on the date given.
    disclaimer: {
      url: "https://www.sandiegocounty.gov/content/sdc/deh/fhd/ffis/disclaimer.html",
      retrieved: "2026-09-24",
      paragraphs: [
        "The web site provides grade scores and a summary of violations noted by Department of Environmental Health and Quality (DEHQ) specialists for the past three years at each facility. The conditions observed and documented during a food establishment inspection may have been corrected, and violations may have been corrected since the last date of inspection. New violations or problems may have developed since the last inspection.",
        "The information provided on this web site is a summary and is not intended to substitute for County official records showing the complete results of an inspection.",
        "DEHQ does not guarantee the accuracy of the information reported on this web site, and disclaims liability for any errors.",
        "DEHQ does not endorse any food establishment.",
      ],
    },
  },

  authors: "Chenhao Zhang and Ayan Pendharkar, Canyon Crest Academy, San Diego",
  citationAuthors: "Zhang, C., and Pendharkar, A.",
  attributions:
    "Inspection results: San Diego County Department of Environmental Health and Quality, SD Food Info. Council districts: SANDAG. Basemap and Street View: Google Maps.",

  searchHint: "Try part of a name or a street.",
};

/** On every page footer, in the share tags and in the app manifest. */
export const STUDENT_NOTE = "Independent student project, not affiliated with or endorsed by the County of San Diego.";

export const DISTRICT_NUMBERS = Array.from({ length: SITE.districts.count }, (_, i) => i + 1);

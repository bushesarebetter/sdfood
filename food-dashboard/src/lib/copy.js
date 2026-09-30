/**
 * Interface strings in two registers: plain, the default, and technical, for
 * environmental-health staff and analysts. The two say the same facts in
 * different words.
 *
 * Rules: "major violation" is the County's own term and is kept; a band is
 * named by its number and its points, never by an adjective; results are
 * stated as rates; no em dashes; no "not X, Y" contrasts.
 */
import { SITE } from "../site.js";
import { FIELD_TYPES } from "./inspections.js";

const PLAIN = {
  appName: SITE.siteTitle,
  aboutButton: "About this site",

  bandTitle: "Which bands",
  bandUnit: "by points on the students' point rule",
  typeTitle: "Kind of place",
  flagTitle: "In the 12 months before the list date",
  flagUnit: "our reading",

  searchPlaceholder: "Search for a restaurant or market",
  searchHint: SITE.searchHint,

  detailHistory: "Inspection scores",
  detailHistoryNote: "The County records we keep, oldest to newest",
  detailFindings: "What inspectors found",
  detailFindingsNote: "Items cited in the three years before the last visit, by theme (our reading of the County's item text)",
  detailFacts: "What the County's record shows",
  detailFactsNote: "The 12 months before the last visit",
  detailNoFacts: `No closure, major violation, B or C grade, repeat reinspection, ${FIELD_TYPES} visit in the 12 months before the last visit.`,
  detailCard: "How the points add up",
  detailCardNote: "Each row is a number from the County's record, times its weight; the rule above says which years it reads",
  detailNearby: "Other listed places nearby",
  detailStreetView: "Street View",
  detailRecord: "The County's record",
  detailVisits: "The County records we keep",
};

const ADVANCED = {
  ...PLAIN,
  aboutButton: "Methodology",
  bandTitle: "Bands",
  bandUnit: "cumulative",
  typeTitle: "Facility type",
  flagTitle: "Record flags, 12 months to the list date",
  searchPlaceholder: "Search facility",
  detailHistory: "Inspection history",
  detailHistoryNote: "Score by record; reinspections, re-grade or reopening visits, complaint or other field visits (our reading) and status verifications drawn lighter",
  detailFindings: "Violations by theme",
  detailFindingsNote: "Report items, 36 months before the last visit; major, minor, good retail practice",
  detailFacts: "Record, 12 months",
  detailCard: "Worksheet",
  detailCardNote: "value × weight = points, per item; the window is in meta.card.window",
  detailNearby: "Nearby listed facilities",
  detailRecord: "DEHQ record",
};

export function copyFor(advanced) {
  return advanced ? ADVANCED : PLAIN;
}

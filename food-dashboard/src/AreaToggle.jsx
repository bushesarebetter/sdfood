/**
 * Which part of the County's record to show: the City of San Diego (places
 * inside a council district) or every listed place in San Diego County.
 * Shown only when the export holds places outside the City.
 */
export default function AreaToggle({ county, onChange, compact = false, note = null }) {
  const btn = (on) =>
    `${compact ? "min-h-[36px] px-3 text-[13px] font-medium" : "min-h-[32px] border px-2.5 py-1 text-[13px] leading-none"} ${
      on ? (compact ? "bg-ink text-paper" : "border-ink bg-ink text-paper") : compact ? "text-ink-2" : "border-rule-strong bg-transparent text-ink-2 hover:border-ink hover:text-ink"
    }`;
  const choices = [
    [false, compact ? "City" : "City of San Diego"],
    [true, compact ? "County" : "All of San Diego County"],
  ];
  const group = (
    <div role="group" aria-label="Area" className={compact ? "inline-flex border border-rule-strong bg-paper shadow-paper" : "flex flex-wrap gap-1.5"}>
      {choices.map(([value, label]) => (
        <button key={label} onClick={() => onChange(value)} aria-pressed={county === value} className={btn(county === value)}>
          {label}
        </button>
      ))}
    </div>
  );
  if (compact || !county || !note) return group;
  return (
    <div>
      {group}
      <p className="mt-2.5 text-[13px] leading-[1.45] text-ink-2">{note}</p>
    </div>
  );
}

/** Under the switch, when the county is shown: how places outside the City are described. */
export function outsideNote(meta) {
  const o = meta?.card?.outside;
  if (!o) return null;
  return o.bands_shown
    ? "Outside the City, bands and rates are the ones measured on restaurants outside the City."
    : "Outside the City, places show their points and an estimate measured outside the City, but no band: the bands did not hold there.";
}

/** The places in scope: the City only unless `county` is on. */
export function inArea(facilities, county) {
  if (!facilities || county) return facilities;
  return { ...facilities, features: facilities.features.filter((f) => f.properties.council_district != null) };
}

export function hasCountyPlaces(facilities) {
  return Boolean(facilities?.features?.some((f) => f.properties.council_district == null));
}

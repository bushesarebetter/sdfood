/**
 * Which part of the County's record to show: the City of San Diego (places
 * inside a council district) or every listed place in San Diego County.
 * Shown only when the export holds places outside the City.
 */
export default function AreaToggle({ county, onChange, compact = false }) {
  const btn = (on) =>
    `${compact ? "min-h-[36px] px-3 text-[13px] font-medium" : "min-h-[32px] border px-2.5 py-1 text-[13px] leading-none"} ${
      on ? (compact ? "bg-ink text-paper" : "border-ink bg-ink text-paper") : compact ? "text-ink-2" : "border-rule-strong bg-transparent text-ink-2 hover:border-ink hover:text-ink"
    }`;
  const choices = [
    [false, compact ? "City" : "City of San Diego"],
    [true, compact ? "County" : "All of San Diego County"],
  ];
  return (
    <div role="group" aria-label="Area" className={compact ? "inline-flex border border-rule-strong bg-paper shadow-paper" : "flex flex-wrap gap-1.5"}>
      {choices.map(([value, label]) => (
        <button key={label} onClick={() => onChange(value)} aria-pressed={county === value} className={btn(county === value)}>
          {label}
        </button>
      ))}
    </div>
  );
}

/** The places in scope: the City only unless `county` is on. */
export function inArea(facilities, county) {
  if (!facilities || county) return facilities;
  return { ...facilities, features: facilities.features.filter((f) => f.properties.council_district != null) };
}

export function hasCountyPlaces(facilities) {
  return Boolean(facilities?.features?.some((f) => f.properties.council_district == null));
}

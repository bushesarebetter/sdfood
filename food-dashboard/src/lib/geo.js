/** Distance in metres between two [lon, lat] pairs; exact enough within a city. */
export function metersBetween(a, b) {
  const k = Math.cos((a[1] * Math.PI) / 180);
  const dx = (b[0] - a[0]) * 111320 * k;
  const dy = (b[1] - a[1]) * 110540;
  return Math.hypot(dx, dy);
}

/** Other listed places within `maxM` of a feature, nearest first. */
export function nearbySites(feature, fc, maxM = 800, n = 3) {
  if (!feature || !fc?.features) return [];
  const here = feature.geometry.coordinates;
  const id = feature.properties?.facility_id;
  const out = [];
  for (const f of fc.features) {
    if (f === feature || (id != null && f.properties?.facility_id === id)) continue;
    const meters = metersBetween(here, f.geometry.coordinates);
    if (meters <= maxM) out.push({ feature: f, meters });
  }
  return out.sort((a, b) => a.meters - b.meters).slice(0, n);
}

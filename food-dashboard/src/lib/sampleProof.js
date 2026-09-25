/**
 * An export may call itself the invented sample only if it is one.
 *
 * `meta.sample: true` switches off every publication gate (approval stamp,
 * owner contact, named bands, expiry), so the flag alone is not enough: an
 * export that sets it must also look like the output of
 * scripts/make_sample_export.py. Invented ids and names, no source URL, and a
 * provenance of "sample". A real export with the flag flipped is refused here.
 */
export const SAMPLE_ID = /^SAMPLE-FFPP-\d{5}$/;

/** Why an export that claims to be the sample is not one ([] when the claim holds or is not made). */
export function sampleProblems(meta, features = []) {
  if (meta?.sample !== true) return [];
  const out = [];
  if (meta?.run !== "sample") out.push('meta.run is not "sample"');
  if (meta?.source?.url != null) out.push("meta.source.url is set");
  if (meta?.provenance?.code_sha !== "sample") out.push('meta.provenance.code_sha is not "sample"');
  const badId = features.find((f) => !SAMPLE_ID.test(String(f?.properties?.facility_id ?? "")));
  if (badId) out.push(`place ${JSON.stringify(badId?.properties?.facility_id)} does not have a sample id`);
  const badName = features.find((f) => !String(f?.properties?.name ?? "").startsWith("Sample "));
  if (badName) out.push(`place ${JSON.stringify(badName?.properties?.name)} is not named "Sample …"`);
  return out;
}

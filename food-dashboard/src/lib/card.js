/**
 * How a place's points add up (`bands` mode).
 *
 * The published rule (`meta.card`) is a short list of counts from a place's
 * County record, each with a whole-number weight: `items` are
 * `{ item, label, weight, unit, feature }`. Each place carries its worksheet
 * (`score_card`): one row per item, `{ item, weight, value, points, met }`,
 * where `value` is the place's own count and `points = weight × value`. The
 * place's `points` are the sum of the rows, which the export check enforces.
 */
const num = (x) => (typeof x === "number" && Number.isFinite(x) ? x : 0);
const show = (x) => (Number.isInteger(x) ? String(x) : String(Math.round(x * 10) / 10));

export function worksheet(p, meta) {
  const card = p?.score_card;
  if (!Array.isArray(card) || !card.length) return null;
  const items = new Map((meta?.card?.items ?? []).map((it) => [it.item, it]));
  const rows = card.map((r) => {
    const it = items.get(r.item) ?? {};
    const weight = num(r.weight ?? it.weight);
    const value = num(r.value);
    const points = typeof r.points === "number" ? r.points : weight * value;
    return { item: r.item, label: it.label ?? String(r.item ?? ""), unit: it.unit ?? null, weight, value, points, met: points > 0 };
  });
  const sum = rows.reduce((a, r) => a + r.points, 0);
  const total = typeof p.points === "number" ? p.points : sum;
  return { rows, met: rows.filter((r) => r.met), unmet: rows.filter((r) => !r.met), total, consistent: Math.abs(total - sum) < 1e-9 };
}

/**
 * One worksheet row as text. Technical: "Food-temperature citations in the
 * last year: 3 × 2 = 6 points". Plain: "Food-temperature citations in the
 * last year: 3 (6 points)".
 */
export function rowText(r, { advanced = false } = {}) {
  const pts = `${show(r.points)} ${r.points === 1 ? "point" : "points"}`;
  return advanced ? `${r.label}: ${show(r.value)} × ${show(r.weight)} = ${pts}` : `${r.label}: ${show(r.value)} (${pts})`;
}

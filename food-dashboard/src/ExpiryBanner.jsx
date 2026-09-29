import { useMeta } from "./useMeta";
import { isExpired, expiryNotice, soonNotice } from "./lib/expiry";

/**
 * Shown on every page once meta.expires has passed, and in the last days before it (so staff are
 * warned before the list goes search-only). It cannot be dismissed, and it prints: a place page
 * printed from an out-of-date export must say so.
 */
export default function ExpiryBanner({ fixed = false, compact = false }) {
  const meta = useMeta();
  const text = isExpired(meta) ? expiryNotice(meta) : soonNotice(meta);
  if (!text) return null;
  const [first, ...rest] = text.split(/(?<=\.) /);
  return (
    <div role="note" className={`border-b border-ink bg-paper-edge text-ink ${compact ? "border px-3 py-2 text-[13px] leading-[1.45]" : "px-4 py-2 text-[13px] leading-[1.5]"} ${fixed ? "shrink-0" : ""}`}>
      <div className={compact ? "" : "mx-auto max-w-[76rem] md:px-4"}>
        <span className="font-semibold">{first}</span> {rest.join(" ")}
      </div>
    </div>
  );
}

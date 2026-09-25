import { useSample } from "./useMeta";

/**
 * Shown on every page while the export is the invented sample. It cannot be
 * dismissed: a reader who lands on a place page from a link must never take
 * a sample record for a real one.
 */
export default function SampleBanner({ fixed = false, compact = false }) {
  const sample = useSample();
  if (!sample) return null;
  if (compact) {
    return (
      <div role="note" className="print-hide border border-band-2 bg-paper-edge px-3 py-2 text-[13px] leading-[1.45] text-ink">
        <span className="font-semibold text-band-2">Sample data.</span> Every place here is invented.
      </div>
    );
  }
  return (
    <div role="note" className={`print-hide border-b border-band-2 bg-paper-edge px-4 py-2 text-[13px] leading-[1.5] text-ink ${fixed ? "shrink-0" : ""}`}>
      <div className="mx-auto max-w-[76rem] md:px-4">
        <span className="font-semibold text-band-2">Sample data.</span> Every place on this site is invented so the site could be
        built and reviewed. No real business, address or inspection is shown.
      </div>
    </div>
  );
}

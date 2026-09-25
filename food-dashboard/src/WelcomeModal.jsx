import Dialog from "./Dialog";
import { useAdvanced } from "./useAdvanced";
import { useMeta, useMode, useSample } from "./useMeta";
import { bandSummary } from "./lib/bands";
import { SITE, STUDENT_NOTE } from "./site";

/**
 * Shown once, on the first visit to the map: what a dot is, what a place
 * view holds, and which lines are the County's and which are ours.
 */
export default function WelcomeModal() {
  const { seenWelcome, dismissWelcome, advanced, toggle } = useAdvanced();
  const meta = useMeta();
  const mode = useMode();
  const sample = useSample();

  if (seenWelcome) return null;

  return (
    <Dialog titleId="welcome-title" onClose={dismissWelcome} className="max-w-[34rem]" z={70} align="center">
      <div className="border-b border-rule-strong px-8 pb-6 pt-7">
        <p className="label mb-3">{SITE.name}</p>
        <h2 id="welcome-title" className="font-serif text-[28px] font-medium leading-[1.1] tracking-[-0.02em] text-ink focus:outline-none">
          How to read the map
        </h2>
      </div>

      <div className="space-y-4 px-8 py-6 font-serif text-[16px] leading-[1.55] text-ink-2">
        {mode === "bands" ? (
          <p>
            Coloured dots are places in the bands of the published rule; darker = more points. Grey dots are other listed
            places. {bandSummary(meta, "1")}
          </p>
        ) : (
          <p>Every dot is a listed place, drawn alike. The list is by name.</p>
        )}
        <p>
          Select a place to see its County records: each visit with the County&rsquo;s status text, scores, grades and the
          items inspectors cited. Lines marked &ldquo;Our reading&rdquo; are the site&rsquo;s, not the County&rsquo;s.
        </p>
        <p className="border-t border-rule pt-4 text-[15px]">
          {sample ? "Every place shown is invented: this is the site before its real data." : STUDENT_NOTE}
        </p>
      </div>

      <div className="flex flex-col gap-3 border-t border-rule-strong px-8 py-5 sm:flex-row sm:items-center sm:justify-between">
        <button onClick={dismissWelcome} className="bg-ink px-6 py-2.5 text-[14px] font-semibold text-paper hover:bg-ink-2">
          Open the map
        </button>
        <button
          onClick={() => { if (!advanced) toggle(); dismissWelcome(); }}
          className="border-b border-ink/25 pb-px text-left text-[13px] text-ink-2 hover:border-ink hover:text-ink sm:text-right"
        >
          Use technical terms
        </button>
      </div>
    </Dialog>
  );
}

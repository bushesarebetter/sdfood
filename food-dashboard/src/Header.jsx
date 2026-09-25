import { useState } from "react";
import { useAdvanced } from "./useAdvanced";
import SearchBox from "./SearchBox";
import AboutModal from "./AboutModal";
import { SITE } from "./site";

/**
 * Masthead for the map: the name, the scope, the search, the register toggle
 * and About. Its height is reserved so nothing below it moves as it loads.
 */
export default function Header({ facilities, onSelect, onHome, onNavigate }) {
  const { advanced, toggle } = useAdvanced();
  const [aboutOpen, setAboutOpen] = useState(false);

  return (
    <>
      <header className="print-hide shrink-0 border-b border-rule-strong bg-paper">
        <div className="flex min-h-[108px] flex-col justify-center gap-3 px-5 py-3 lg:min-h-[56px] lg:flex-row lg:items-center lg:justify-between lg:gap-8 lg:py-2.5">
          <div className="flex items-baseline gap-3">
            <p className="font-serif text-[19px] font-semibold leading-none tracking-[-0.01em] text-ink">
              <a
                href="/"
                onClick={(e) => {
                  if (!onHome) return;
                  e.preventDefault();
                  onHome();
                }}
                className="border-b border-transparent hover:border-ink"
              >
                {SITE.shortTitle}
              </a>
            </p>
            <span aria-hidden="true" className="hidden h-3 w-px bg-rule-strong sm:block" />
            <p className="hidden text-[12px] leading-none text-ink-2 sm:block">{SITE.fullName}, the County&rsquo;s inspection record</p>
          </div>

          <div className="flex items-center gap-3 lg:flex-1 lg:justify-end">
            <div className="min-w-0 flex-1 lg:max-w-[24rem]">
              <SearchBox facilities={facilities} onSelect={onSelect} />
            </div>
            <RegisterToggle advanced={advanced} onToggle={toggle} />
            <button onClick={() => setAboutOpen(true)} className="shrink-0 whitespace-nowrap border-b border-ink/25 pb-px text-[13px] text-ink-2 hover:border-ink hover:text-ink">
              {advanced ? "Methodology" : "About this site"}
            </button>
          </div>
        </div>
      </header>

      {aboutOpen && <AboutModal onClose={() => setAboutOpen(false)} onNavigate={onNavigate} />}
    </>
  );
}

function RegisterToggle({ advanced, onToggle }) {
  return (
    <div role="group" aria-label="Terminology" className="hidden shrink-0 border border-rule-strong sm:flex">
      {[
        { key: false, label: "Plain" },
        { key: true, label: "Technical" },
      ].map(({ key, label }) => (
        <button
          key={label}
          onClick={() => advanced !== key && onToggle()}
          aria-pressed={advanced === key}
          title={key ? "Environmental-health terminology (report items, weights, intervals)" : "Everyday language"}
          className={`px-2.5 py-1 text-[12px] font-medium ${advanced === key ? "bg-ink text-paper" : "bg-transparent text-ink-2 hover:text-ink"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

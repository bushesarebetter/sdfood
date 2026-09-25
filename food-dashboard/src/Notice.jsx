import { useState } from "react";

const KEY = "food.seenNotice";

function seen() {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

function mark() {
  try {
    window.localStorage.setItem(KEY, "1");
  } catch {
    /* private mode: the notice shows again next visit */
  }
}

/**
 * One line, shown once. This site sets no cookies itself; Google Maps, which
 * draws the basemap and Street View, may set its own.
 */
export default function Notice({ placement = "inline", onNavigate }) {
  const [hidden, setHidden] = useState(seen);
  if (hidden) return null;

  const dismiss = () => {
    mark();
    setHidden(true);
  };

  const frame = placement === "fixed" ? "fixed inset-x-0 bottom-0 z-50 border-t" : "border-b";

  return (
    <div
      role="status"
      className={`print-hide ${frame} border-rule-strong bg-paper-sunk px-4 py-2 text-[12px] text-ink-2`}
      style={placement === "fixed" ? { paddingBottom: "max(8px, env(safe-area-inset-bottom))" } : undefined}
    >
      <div className="mx-auto flex max-w-[76rem] flex-wrap items-center justify-between gap-x-4 gap-y-1 md:px-4">
        <p>
          This site sets no cookies of its own. Google Maps, which draws the map, may set its own.{" "}
          <a
            href="/privacy"
            onClick={(e) => {
              e.preventDefault();
              onNavigate("/privacy");
            }}
            className="border-b border-ink/25 text-ink hover:border-ink"
          >
            Details
          </a>
        </p>
        <button onClick={dismiss} className="text-[12px] font-semibold text-ink hover:underline">
          OK
        </button>
      </div>
    </div>
  );
}

import { useEffect, useRef } from "react";
import { focusables, trapTarget } from "./lib/focus";

/**
 * The one modal dialog every overlay uses (About, the first-visit note, the
 * copy box, the phone's address check). On open it moves focus to the
 * dialog's heading (the element whose id is `titleId`); Tab and Shift+Tab stay
 * inside; Escape closes it, and only it; on close, focus returns to whatever
 * had it before. A click on the backdrop closes it too.
 */
export default function Dialog({ titleId, onClose, children, className = "", overlayClassName = "", z = 60, align = "start", closeOnBackdrop = true }) {
  const panelRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement;
    const panel = panelRef.current;
    const heading = panel?.querySelector(`[id="${titleId}"]`) ?? panel;
    if (heading && !heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
    heading?.focus({ preventScroll: true });

    const onKey = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        e.preventDefault();
        onCloseRef.current?.();
        return;
      }
      if (e.key !== "Tab" || !panel) return;
      const items = focusables(panel);
      const active = document.activeElement;
      const target = items.length ? trapTarget(items, active, e.shiftKey, items.includes(active)) : heading;
      if (target) {
        e.preventDefault();
        target.focus();
      }
    };
    // Capture, so a panel's own Escape handler underneath never sees the key.
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      if (previous && typeof previous.focus === "function" && document.contains(previous)) previous.focus({ preventScroll: true });
    };
  }, [titleId]);

  return (
    <div
      className={`print-hide fixed inset-0 flex justify-center overflow-y-auto bg-ink/40 p-3 sm:p-8 ${align === "center" ? "items-center" : "items-start"} ${overlayClassName}`}
      style={{ zIndex: z }}
      onMouseDown={(e) => closeOnBackdrop && e.target === e.currentTarget && onCloseRef.current?.()}
    >
      <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby={titleId} className={`my-auto w-full border border-rule-strong bg-paper ${className}`}>
        {children}
      </div>
    </div>
  );
}

/** The close button every dialog uses. */
export function CloseButton({ onClose, label = "Close" }) {
  return (
    <button type="button" onClick={onClose} aria-label={label} className="-mr-2 flex h-11 w-11 shrink-0 items-center justify-center text-ink-3 hover:text-ink">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    </button>
  );
}

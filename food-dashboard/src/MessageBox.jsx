import { useRef, useState } from "react";
import Dialog, { CloseButton } from "./Dialog";

/**
 * Text to copy (a citation, a place's record), shown in full so nobody
 * pastes text they have not seen, with a copy button. When the clipboard
 * works the status says so; when it does not, the text is still right there.
 */
export default function MessageBox({ title, text, copied = null, onClose }) {
  const areaRef = useRef(null);
  const [status, setStatus] = useState(
    copied === true ? "Copied to your clipboard." : copied === false ? "Select the text and copy it." : ""
  );

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setStatus("Copied to your clipboard.");
    } catch {
      areaRef.current?.select();
      setStatus("The browser blocked the clipboard. Select the text and press Ctrl+C or Cmd+C.");
    }
  }

  return (
    <Dialog titleId="message-title" onClose={onClose} className="max-w-[40rem]" z={80} align="center">
      <div className="flex items-center justify-between border-b border-rule-strong px-5 py-1">
        <h2 id="message-title" className="label focus:outline-none">{title}</h2>
        <CloseButton onClose={onClose} />
      </div>
      <textarea
        ref={areaRef}
        readOnly
        value={text}
        rows={16}
        aria-label={title}
        onFocus={(e) => e.target.select()}
        className="block w-full resize-y border-0 bg-paper px-5 py-4 font-mono text-[13px] leading-[1.55] text-ink focus:outline-none"
      />
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule-strong px-5 py-3">
        <p className="text-[13px] text-ink-2" role="status">{status}</p>
        <div className="flex items-center gap-4">
          <button onClick={copy} className="bg-ink px-4 py-2 text-[13px] font-semibold text-paper hover:bg-ink-2">
            Copy
          </button>
          <button onClick={onClose} className="border-b border-ink/25 text-[13px] text-ink-2 hover:border-ink hover:text-ink">
            Done
          </button>
        </div>
      </div>
    </Dialog>
  );
}

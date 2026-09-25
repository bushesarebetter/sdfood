import { useEffect, useRef, useState } from "react";
import { suggestAddresses, newSession, placesAvailable } from "./places";

const DEBOUNCE_MS = 250;
const MIN_CHARS = 3;

/**
 * A text field that suggests addresses as you type, the way a maps app does.
 *
 * `value` is the text; `onChange(text)` fires on every keystroke and clears
 * any earlier pick; `onPick(pick)` fires when a suggestion is chosen, with the
 * suggestion's place so the caller can skip the geocoder. Arrow keys move,
 * Enter picks, Escape closes; a click elsewhere closes. When suggestions are
 * not available the field is an ordinary input.
 */
export default function AddressInput({ value, onChange, onPick, className, ...inputProps }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const boxRef = useRef(null);
  const sessionRef = useRef(null);
  const seqRef = useRef(0);
  const id = inputProps.id ?? inputProps["aria-label"]?.toLowerCase().replace(/\W+/g, "-");
  const listId = `${id}-suggestions`;

  useEffect(() => {
    const text = value.trim();
    if (text.length < MIN_CHARS || !placesAvailable()) {
      setItems([]);
      return undefined;
    }
    const seq = ++seqRef.current;
    const timer = setTimeout(async () => {
      try {
        if (!sessionRef.current) sessionRef.current = await newSession();
      } catch {
        return;
      }
      const found = await suggestAddresses(text, sessionRef.current);
      if (seq !== seqRef.current) return; // a newer keystroke superseded this one
      setItems(found);
      setCursor(0);
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [value]);

  useEffect(() => {
    function onDocClick(e) {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function choose(item) {
    onChange(item.text);
    onPick?.(item);
    setItems([]);
    setOpen(false);
    sessionRef.current = null; // the pick ends the billing session
  }

  function onKeyDown(e) {
    if (!open || items.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => (c + 1) % items.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => (c - 1 + items.length) % items.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(items[cursor]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  const show = open && items.length > 0;

  return (
    <div ref={boxRef} className="relative">
      <input
        type="text"
        value={value}
        onChange={(e) => { onChange(e.target.value); onPick?.(null); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={show}
        aria-controls={listId}
        aria-activedescendant={show ? `${listId}-${cursor}` : undefined}
        className={className}
        {...inputProps}
      />
      {show && (
        <ul
          id={listId}
          role="listbox"
          className="absolute left-0 right-0 top-full z-50 mt-1 border border-rule-strong bg-paper shadow-paper"
        >
          {items.map((item, i) => (
            <li
              key={item.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === cursor}
              onMouseEnter={() => setCursor(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(item)}
              className={`cursor-pointer border-b border-rule px-3.5 py-2 last:border-b-0 ${i === cursor ? "bg-paper-edge" : "hover:bg-paper-sunk"}`}
            >
              <span className="block truncate text-[13px] leading-snug text-ink">{item.main}</span>
              {item.secondary && <span className="block truncate text-[11px] text-ink-3">{item.secondary}</span>}
            </li>
          ))}
          <li className="px-3.5 py-1.5 text-right text-[10px] text-ink-3" aria-hidden="true">
            Suggestions by Google
          </li>
        </ul>
      )}
    </div>
  );
}

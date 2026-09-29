import { useSyncExternalStore } from "react";

/**
 * Whether the staff notice bar is closed (its ×) for this browser session, and a way to open the whole
 * notice from elsewhere (the masthead's "Staff notice"). One store, so the bar and the masthead agree on
 * every page. Kept in sessionStorage: a new browser session, and every new sign-in (the server clears
 * site storage on sign-in), brings the bar back. Until the notice has been read in this session the bar
 * shows, and the whole notice opens, whatever this says (StaffBanner); the × itself marks it read.
 */
const HIDDEN_KEY = "food.staffNoticeHidden";
const listeners = new Set();

function readHidden() {
  try {
    return window.sessionStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

let state = { hidden: typeof window !== "undefined" ? readHidden() : false, openSeq: 0 };

function set(next) {
  state = { ...state, ...next };
  try {
    if (state.hidden) window.sessionStorage.setItem(HIDDEN_KEY, "1");
    else window.sessionStorage.removeItem(HIDDEN_KEY);
  } catch {
    /* the bar then shows again on the next page, which is the safe side */
  }
  listeners.forEach((l) => l());
}

/** Calls `l` on every change; returns the function that stops it. */
export function subscribeStaffNotice(l) {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** The store as it is now, {hidden, openSeq}, outside React. */
export const staffNoticeState = () => state;

/** {hidden, openSeq}: openSeq goes up each time something asks for the whole notice to open. */
export function useStaffNotice() {
  return useSyncExternalStore(subscribeStaffNotice, staffNoticeState, staffNoticeState);
}

/** The bar's ×: closed for the rest of this browser session. */
export const hideStaffNotice = () => set({ hidden: true });

/** Bring the bar back and, by default, open the whole notice. */
export const showStaffNotice = ({ open = true } = {}) => set({ hidden: false, openSeq: state.openSeq + (open ? 1 : 0) });

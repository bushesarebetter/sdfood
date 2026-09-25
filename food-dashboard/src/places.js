import { loadPlaces } from "./useGoogleMap";
import { SITE } from "./site";

/**
 * Address suggestions from Google Places, biased to the city.
 *
 * One session token covers the keystrokes of one search and the lookup of the
 * chosen place, which is how Google bills it. A picked suggestion resolves to
 * a point without a separate geocode. If the key has no Places access the
 * first request is refused and suggestions switch off for the rest of the visit;
 * the fields still take a typed address.
 */
let disabled = false;

export const placesAvailable = () => !disabled;

export async function newSession() {
  const places = await loadPlaces();
  return new places.AutocompleteSessionToken();
}

export async function suggestAddresses(input, sessionToken) {
  if (disabled || !input || input.trim().length < 3) return [];
  try {
    const places = await loadPlaces();
    const { suggestions } = await places.AutocompleteSuggestion.fetchAutocompleteSuggestions({
      input,
      sessionToken,
      locationRestriction: SITE.bounds,
      includedRegionCodes: ["us"],
      language: "en-US",
      region: "us",
    });
    return suggestions
      .map((s) => s.placePrediction)
      .filter(Boolean)
      .map((p) => ({
        id: p.placeId,
        main: p.mainText?.toString() ?? p.text.toString(),
        secondary: p.secondaryText?.toString() ?? "",
        text: p.text.toString(),
        prediction: p,
      }));
  } catch (err) {
    const msg = String(err?.message ?? err);
    if (/denied|not activated|not authorized|permission|billing|api key|ApiNotActivated/i.test(msg)) disabled = true;
    return [];
  }
}

/** The chosen suggestion as a point and a printable address. Ends the session. */
export async function resolvePlace(pick) {
  const place = pick.prediction.toPlace();
  await place.fetchFields({ fields: ["location", "formattedAddress"] });
  if (!place.location) throw new Error("NOT_FOUND");
  return {
    point: [place.location.lng(), place.location.lat()],
    label: place.formattedAddress ?? pick.text,
  };
}

import { useRef, useEffect, useState } from "react";
import { Loader } from "@googlemaps/js-api-loader";
import { SITE } from "./site";

export const SAN_DIEGO_CENTER = SITE.center;

// One loader per page. The Google Maps JS API is a singleton -- calling
// importLibrary twice with different options throws, so the options are fixed here.
let loaderPromise = null;
let loader = null;
let placesPromise = null;

// What a visitor reads when the map cannot load. The reason goes to the console.
export const MAP_UNAVAILABLE = "The map is not available right now. The list shows the same places.";

export function loadMaps() {
  if (!loaderPromise) {
    const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
    if (!apiKey) {
      console.error("Map not loaded: VITE_GOOGLE_MAPS_API_KEY is not set. Copy food-dashboard/.env.example to food-dashboard/.env and add a Google Maps JavaScript API key.");
      return Promise.reject(new Error(MAP_UNAVAILABLE));
    }
    loader = new Loader({ apiKey, version: "weekly" });
    // `streetView` powers StreetViewPanel and `geometry` gives us computeHeading,
    // used to aim the pano camera back at the place.
    loaderPromise = Promise.all([
      loader.importLibrary("core"),
      loader.importLibrary("maps"),
      loader.importLibrary("geometry"),
      loader.importLibrary("streetView"),
      // Resolve to the merged google.maps namespace so callers get every loaded
      // library off one object instead of juggling per-library handles.
    ]).then(() => window.google.maps);
  }
  return loaderPromise;
}

/**
 * The Places library, loaded on first use rather than with the map: only the
 * address fields need it, and a key without Places access should not stop
 * the map from drawing.
 */
export function loadPlaces() {
  if (!placesPromise) {
    placesPromise = loadMaps().then(() => loader.importLibrary("places"));
    placesPromise.catch(() => { placesPromise = null; });
  }
  return placesPromise;
}

/**
 * Creates a Google Maps vector map in `containerRef` and calls `onLoad(map)` once
 * it is ready. Mirrors the old useMapbox signature so MapView's structure is unchanged.
 *
 * A Map ID is required: deck.gl's WebGL overlay only interleaves correctly on a
 * vector map, and the dark styling lives in the Cloud console style attached to
 * that Map ID (google.maps.Map `styles` is ignored when mapId is present).
 */
export default function useGoogleMap(containerRef, onLoad, zoom = 12) {
  const mapRef = useRef(null);
  const onLoadRef = useRef(onLoad);
  onLoadRef.current = onLoad;

  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    loadMaps()
      .then((maps) => {
        if (cancelled || !containerRef.current) return;

        const map = new maps.Map(containerRef.current, {
          center: SAN_DIEGO_CENTER,
          zoom,
          mapId: import.meta.env.VITE_GOOGLE_MAPS_MAP_ID || "DEMO_MAP_ID",
          disableDefaultUI: true,
          zoomControl: true,
          scaleControl: true,
          mapTypeControl: true,
          mapTypeControlOptions: {
            style: maps.MapTypeControlStyle.DROPDOWN_MENU,
            position: maps.ControlPosition.TOP_RIGHT,
            mapTypeIds: ["roadmap", "satellite"],
          },
          streetViewControl: true,
          clickableIcons: false,
          gestureHandling: "greedy",
        });

        mapRef.current = map;
        onLoadRef.current(map);
      })
      .catch((err) => {
        if (err?.message !== MAP_UNAVAILABLE) console.error("Map not loaded:", err);
        if (!cancelled) setError(MAP_UNAVAILABLE);
      });

    return () => {
      cancelled = true;
      mapRef.current = null;
    };
  }, []);

  return { mapRef, error };
}

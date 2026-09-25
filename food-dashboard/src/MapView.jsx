import { useRef, useEffect, useState, useCallback, useMemo } from "react";
import { GoogleMapsOverlay } from "@deck.gl/google-maps";
import { ScatterplotLayer } from "@deck.gl/layers";
import useGoogleMap from "./useGoogleMap";
import MapLegend from "./MapLegend";
import { useMode } from "./useMeta";
import { passesFilters } from "./lib/filters";
import { typeLabel } from "./lib/inspections";
import { gradeView } from "./lib/grades";
import { markFor } from "./lib/marks";

const INITIAL_ZOOM = 12;
const FLY_ZOOM = 16;

// The tooltip is built as HTML. Names and addresses are data and are escaped.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/**
 * The map: one dot per listed place that passes the filters. In `record`
 * mode every dot is alike; in `bands` mode the band carries the colour,
 * darker for more points. When the map cannot load, `onError` tells the
 * layout, which shows the list instead; the reason goes to the console.
 */
export default function MapView({
  facilities,
  filters,
  selected,
  onSelect,
  showLegend = true,
  selectionOffsetY = 0,
  // {point: [lon, lat]} from the address check, drawn as an ink ring.
  pointOverlay = null,
  onError = null,
}) {
  const containerRef = useRef(null);
  const overlayRef = useRef(null);
  const infoWindowRef = useRef(null);
  const [mapReady, setMapReady] = useState(false);
  const mode = useMode();

  const handleMapLoad = useCallback((map) => {
    const overlay = new GoogleMapsOverlay({ interleaved: false });
    overlay.setMap(map);
    overlayRef.current = overlay;
    infoWindowRef.current = new window.google.maps.InfoWindow({ disableAutoPan: true });
    setMapReady(true);
  }, []);

  const { mapRef, error } = useGoogleMap(containerRef, handleMapLoad, INITIAL_ZOOM);

  useEffect(() => {
    if (error) onError?.(error);
  }, [error, onError]);

  const shown = useMemo(
    () => (facilities ? facilities.features.filter((f) => passesFilters(f.properties, filters, { mode })) : []),
    [facilities, filters, mode]
  );

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay || !mapReady) return;

    const showTooltip = (info) => {
      const iw = infoWindowRef.current;
      const map = mapRef.current;
      if (!iw || !map) return;
      if (!info.object) {
        iw.close();
        return;
      }
      const p = info.object.properties;
      const mark = markFor(p, { mode });
      const g = gradeView(p.grade);
      const [lng, lat] = info.object.geometry.coordinates;
      iw.setContent(`
        <div style="font-family:system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;padding:9px 12px;min-width:170px;max-width:260px">
          <div style="font-size:13px;font-weight:600;color:#17150F;line-height:1.3;margin-bottom:3px">${esc(p.name)}</div>
          <div style="font-size:12px;color:#55503F;line-height:1.35;margin-bottom:5px">${esc(p.address)}</div>
          <div style="font-size:12px;color:#55503F">
            ${mark.label ? `<span style="color:${mark.text ?? "#55503F"};font-weight:600">${esc(mark.label)}</span>, ` : ""}${esc(typeLabel(p.facility_type).toLowerCase())}, ${esc(g.graded ? `grade ${g.short}` : g.text.toLowerCase())}
          </div>
        </div>
      `);
      iw.setPosition({ lat, lng });
      iw.open(map);
    };

    const handleCursor = ({ isHovering }) => {
      const el = mapRef.current?.getDiv();
      if (el) el.style.cursor = isHovering ? "pointer" : "";
    };

    const layers = [
      ...(pointOverlay?.point
        ? [new ScatterplotLayer({
            id: "address-layer",
            data: [{ position: pointOverlay.point }],
            getPosition: (d) => d.position,
            radiusUnits: "pixels",
            getRadius: 9,
            filled: false,
            stroked: true,
            lineWidthUnits: "pixels",
            getLineWidth: 2.5,
            getLineColor: [23, 21, 15, 255],
          })]
        : []),
      new ScatterplotLayer({
        id: "places-layer",
        data: shown,
        pickable: true,
        stroked: true,
        filled: true,
        radiusUnits: "meters",
        radiusMinPixels: 4,
        radiusMaxPixels: 13,
        lineWidthUnits: "pixels",
        getPosition: (f) => f.geometry.coordinates,
        getRadius: (f) => markFor(f.properties, { mode }).radius,
        getFillColor: (f) => [...markFor(f.properties, { mode }).rgb, 240],
        updateTriggers: { getRadius: [mode], getFillColor: [mode] },
        getLineColor: [251, 249, 245, 230],
        getLineWidth: 1.2,
        onHover: (info) => {
          showTooltip(info);
          handleCursor({ isHovering: Boolean(info.object) });
        },
        onClick: (info) => info.object && onSelect(info.object),
      }),
    ];

    overlay.setProps({ layers });
  }, [shown, mapReady, onSelect, pointOverlay, mode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !pointOverlay?.point) return;
    const [lng, lat] = pointOverlay.point;
    map.panTo({ lat, lng });
    map.setZoom(15);
  }, [pointOverlay]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selected) return;
    const [lng, lat] = selected.geometry.coordinates;
    map.panTo({ lat, lng });
    if (map.getZoom() < FLY_ZOOM) map.setZoom(FLY_ZOOM);
    if (selectionOffsetY) map.panBy(0, selectionOffsetY);
  }, [selected, selectionOffsetY]);

  useEffect(() => {
    return () => {
      overlayRef.current?.finalize();
      overlayRef.current = null;
      infoWindowRef.current?.close();
    };
  }, []);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" aria-label="Map of the listed places" role="region" />

      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-paper px-8">
          <div className="max-w-md border border-rule-strong bg-paper-sunk px-6 py-5" role="status">
            <p className="label mb-2">The map did not load</p>
            <p className="font-serif text-[15px] leading-[1.55] text-ink-2">{error}</p>
          </div>
        </div>
      )}

      {showLegend && !error && <MapLegend bandsShown={["1", "2", "3"].filter((b) => mode !== "bands" || filters?.band == null || filters.band === "all" || Number(b) <= Number(filters.band))} showUnbanded={mode === "bands" && filters?.band === "all"} />}
    </div>
  );
}

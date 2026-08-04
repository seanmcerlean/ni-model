import { useCallback, useEffect, useRef, useState } from "react";
import { GeoJSON as GeoJSONComponent, MapContainer } from "react-leaflet";
import { GeoJSON as GeoJSONLayer, Layer, PathOptions } from "leaflet";

import niGeoJsonRaw from "../geo/ni.geojson?raw";
import { LOCATION_CODES, VotingPrediction, YearSnapshot } from "../types";

const niGeoJson = JSON.parse(niGeoJsonRaw) as GeoJSON.FeatureCollection;
const NI_BOUNDS: [[number, number], [number, number]] = [
  [53.95, -8.35],
  [55.35, -5.25],
];

function featureId(feature: GeoJSON.Feature): string {
  return LOCATION_CODES[feature.properties?.LAD24CD ?? ""] ?? "";
}

interface Props {
  snapshot: YearSnapshot | null;
  voting: VotingPrediction | null;
  onLocationClick: (locationId: string) => void;
}

type ColourMode = "vote" | "community";
type Rgb = readonly [number, number, number];

const COLOURS: Record<string, Rgb> = {
  unite: [22, 163, 74],
  remain: [37, 99, 235],
  catholic: [34, 197, 94],
  protestant: [14, 165, 233],
  other: [168, 85, 247],
  none: [148, 163, 184],
};

export function blendedColour(parts: Array<[number, Rgb]>): string {
  const total = parts.reduce((sum, [weight]) => sum + weight, 0);
  if (total <= 0) return "#475569";
  const channels = [0, 1, 2].map((channel) => Math.round(
    parts.reduce((sum, [weight, colour]) => sum + weight * colour[channel], 0) / total,
  ));
  return `rgb(${channels.join(", ")})`;
}

function voteColour(voting: VotingPrediction | null, locationId: string): string {
  const prediction = voting?.by_location?.[locationId];
  if (!prediction) return "#475569";
  return blendedColour([
    [prediction.unite_share, COLOURS.unite],
    [prediction.remain_share, COLOURS.remain],
  ]);
}

function communityColour(snapshot: YearSnapshot | null, locationId: string): string {
  const breakdown = snapshot?.locations?.[locationId]?.religious_breakdown;
  if (!breakdown) return "#475569";
  return blendedColour(([
    "catholic", "protestant", "other", "none",
  ] as const).map((background) => [breakdown[background] ?? 0, COLOURS[background]]));
}

export function NiMap({ snapshot, voting, onLocationClick }: Props) {
  const [colourMode, setColourMode] = useState<ColourMode>("vote");
  const geoJsonRef = useRef<GeoJSONLayer | null>(null);

  const style = useCallback((feature: GeoJSON.Feature | undefined): PathOptions => {
    if (!feature) return { fillColor: "#334155", fillOpacity: 0.65, weight: 1.2, color: "#cbd5e1" };
    const locationId = featureId(feature);
    return {
      fillColor: colourMode === "vote"
        ? voteColour(voting, locationId)
        : communityColour(snapshot, locationId),
      fillOpacity: 0.88,
      weight: 1.2,
      color: "#f8fafc",
    };
  }, [colourMode, snapshot, voting]);

  const tooltip = useCallback((feature: GeoJSON.Feature): string => {
    const total = snapshot?.location_breakdown[featureId(feature)];
    return `<strong>${feature.properties?.LAD24NM ?? ""}</strong>${total === undefined ? "" : `<br>${total.toLocaleString()} residents`}`;
  }, [snapshot]);

  useEffect(() => {
    const layer = geoJsonRef.current;
    if (!layer) return;
    layer.setStyle(style);
    layer.eachLayer((child) => {
      const feature = (child as Layer & { feature?: GeoJSON.Feature }).feature;
      if (feature) child.setTooltipContent(tooltip(feature));
    });
  }, [style, tooltip]);

  function onEachFeature(feature: GeoJSON.Feature, layer: Layer) {
    const id = featureId(feature);
    layer.on("click", () => onLocationClick(id));
    layer.bindTooltip(tooltip(feature), { sticky: true });
  }

  return (
    <MapContainer
      bounds={NI_BOUNDS}
      boundsOptions={{ padding: [18, 18] }}
      maxBounds={NI_BOUNDS}
      maxBoundsViscosity={1}
      style={{ height: "100%", width: "100%", background: "#1a1a2e" }}
      zoomControl={false}
      dragging={false}
      scrollWheelZoom={false}
      doubleClickZoom={false}
      boxZoom={false}
      keyboard={false}
      touchZoom={false}
    >
      <GeoJSONComponent
        ref={geoJsonRef}
        data={niGeoJson}
        style={style}
        onEachFeature={onEachFeature}
      />
      <fieldset className="map-mode" aria-label="Map colouring">
        <legend>Map colouring</legend>
        <label><input type="radio" name="map-colour" checked={colourMode === "vote"}
          onChange={() => setColourMode("vote")} />Unite / Remain</label>
        <label><input type="radio" name="map-colour" checked={colourMode === "community"}
          onChange={() => setColourMode("community")} />Community</label>
      </fieldset>
      <div className="map-legend">
        {colourMode === "vote" ? <>
          <span><i className="swatch unite" />More Unite</span>
          <span><i className="swatch vote-blend" />Blended estimate</span>
          <span><i className="swatch remain" />More Remain</span>
        </> : <>
          <span><i className="swatch catholic" />Catholic</span>
          <span><i className="swatch protestant" />Protestant</span>
          <span><i className="swatch other" />Other</span>
          <span><i className="swatch none" />None</span>
        </>}
      </div>
    </MapContainer>
  );
}

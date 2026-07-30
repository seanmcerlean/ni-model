import { GeoJSON, MapContainer, TileLayer } from "react-leaflet";
import { Layer, PathOptions } from "leaflet";

import niGeoJsonRaw from "../geo/ni.geojson?raw";
import { YearSnapshot } from "../types";

const niGeoJson = JSON.parse(niGeoJsonRaw) as GeoJSON.FeatureCollection;

interface Props {
  snapshot: YearSnapshot | null;
  onLocationClick: (locationId: string) => void;
}

function catholicRatio(snapshot: YearSnapshot, locationId: string): number {
  const locTotal = snapshot.location_breakdown[locationId] ?? 0;
  if (locTotal === 0) return 0.5;
  // Approximate: scale religious breakdown proportionally to location share
  const totalPop = snapshot.total_population || 1;
  const locShare = locTotal / totalPop;
  const catholic = (snapshot.religious_breakdown["catholic"] ?? 0) * locShare;
  return catholic / locTotal;
}

function choroColor(ratio: number): string {
  // Green = Catholic majority, Orange = Protestant majority, Grey = neutral
  if (ratio > 0.55) return `rgba(34,139,34,${0.3 + ratio * 0.5})`;
  if (ratio < 0.45) return `rgba(255,140,0,${0.3 + (1 - ratio) * 0.5})`;
  return "rgba(150,150,150,0.4)";
}

export function NiMap({ snapshot, onLocationClick }: Props) {
  function style(feature: GeoJSON.Feature | undefined): PathOptions {
    if (!feature || !snapshot) return { fillColor: "#555", fillOpacity: 0.4, weight: 1, color: "#fff" };
    const ratio = catholicRatio(snapshot, feature.properties?.id ?? "");
    return {
      fillColor: choroColor(ratio),
      fillOpacity: 0.75,
      weight: 1.5,
      color: "#fff",
    };
  }

  function onEachFeature(feature: GeoJSON.Feature, layer: Layer) {
    layer.on("click", () => onLocationClick(feature.properties?.id ?? ""));
    layer.bindTooltip(feature.properties?.name ?? "", { sticky: true });
  }

  return (
    <MapContainer
      center={[54.65, -6.7]}
      zoom={8}
      style={{ height: "100%", width: "100%", background: "#1a1a2e" }}
      zoomControl={true}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
      />
      <GeoJSON
        key={snapshot?.year ?? "empty"}
        data={niGeoJson}
        style={style}
        onEachFeature={onEachFeature}
      />
    </MapContainer>
  );
}

import { GeoJSON, MapContainer, TileLayer } from "react-leaflet";
import { Layer, PathOptions } from "leaflet";

import niGeoJsonRaw from "../geo/ni.geojson?raw";
import { LOCATION_CODES, YearSnapshot } from "../types";

const niGeoJson = JSON.parse(niGeoJsonRaw) as GeoJSON.FeatureCollection;

function featureId(feature: GeoJSON.Feature): string {
  return LOCATION_CODES[feature.properties?.LAD24CD ?? ""] ?? "";
}

interface Props {
  snapshot: YearSnapshot | null;
  onLocationClick: (locationId: string) => void;
}

function communityBalance(snapshot: YearSnapshot, locationId: string): number {
  const detail = snapshot.locations?.[locationId];
  if (!detail) return 0;
  const catholic = detail.religious_breakdown.catholic ?? 0;
  const protestant = detail.religious_breakdown.protestant ?? 0;
  return (catholic - protestant) / Math.max(catholic + protestant, 1);
}

function choroColor(balance: number): string {
  if (balance > 0.08) return balance > 0.3 ? "#15803d" : "#22c55e";
  if (balance < -0.08) return balance < -0.3 ? "#0369a1" : "#0ea5e9";
  return "#64748b";
}

export function NiMap({ snapshot, onLocationClick }: Props) {
  function style(feature: GeoJSON.Feature | undefined): PathOptions {
    if (!feature || !snapshot) return { fillColor: "#334155", fillOpacity: 0.65, weight: 1.2, color: "#cbd5e1" };
    const balance = communityBalance(snapshot, featureId(feature));
    return {
      fillColor: choroColor(balance),
      fillOpacity: 0.82,
      weight: 1.2,
      color: "#f8fafc",
    };
  }

  function onEachFeature(feature: GeoJSON.Feature, layer: Layer) {
    const id = featureId(feature);
    layer.on("click", () => onLocationClick(id));
    const total = snapshot?.location_breakdown[id];
    layer.bindTooltip(
      `<strong>${feature.properties?.LAD24NM ?? ""}</strong>${total === undefined ? "" : `<br>${total.toLocaleString()} residents`}`,
      { sticky: true },
    );
  }

  return (
    <MapContainer
      center={[54.66, -6.72]}
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
      <div className="map-legend">
        <span><i className="swatch catholic" />Catholic background</span>
        <span><i className="swatch balanced" />Balanced</span>
        <span><i className="swatch protestant" />Protestant background</span>
      </div>
    </MapContainer>
  );
}

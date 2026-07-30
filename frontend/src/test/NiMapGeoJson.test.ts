import { describe, expect, it } from "vitest";

import niGeoJsonRaw from "../geo/ni.geojson?raw";

interface PolygonFeature {
  geometry: {
    type: string;
    coordinates: number[][][];
  };
}

describe("NI map GeoJSON", () => {
  it("contains valid Polygon coordinate rings", () => {
    const collection = JSON.parse(niGeoJsonRaw) as {
      features: PolygonFeature[];
    };

    expect(collection.features).toHaveLength(10);
    for (const feature of collection.features) {
      expect(feature.geometry.type).toBe("Polygon");
      for (const ring of feature.geometry.coordinates) {
        expect(ring.length).toBeGreaterThanOrEqual(4);
        for (const position of ring) {
          expect(position).toHaveLength(2);
          expect(position.every(Number.isFinite)).toBe(true);
        }
        expect(ring[ring.length - 1]).toEqual(ring[0]);
      }
    }
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock react-leaflet to avoid DOM/canvas issues in jsdom
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  GeoJSON: () => null,
}));

vi.mock("../geo/ni.geojson?raw", () => ({
  default: '{"type":"FeatureCollection","features":[]}',
}));

import App from "../App";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders header title", () => {
    render(<App />);
    expect(screen.getByText("Northern Ireland Population Model")).toBeInTheDocument();
  });

  it("renders map container", () => {
    render(<App />);
    expect(screen.getByTestId("map")).toBeInTheDocument();
  });

  it("renders Run button", () => {
    render(<App />);
    expect(screen.getByText("Run")).toBeInTheDocument();
  });

  it("Play button is disabled with no buffered years", () => {
    render(<App />);
    expect(screen.getByText("▶ Play")).toBeDisabled();
  });

  it("default start year is 1969", () => {
    render(<App />);
    const inputs = screen.getAllByRole("spinbutton");
    expect(inputs[0]).toHaveValue(1969);
  });

  it("default end year is 2030", () => {
    render(<App />);
    const inputs = screen.getAllByRole("spinbutton");
    expect(inputs[1]).toHaveValue(2030);
  });

  it("speed buttons are rendered", () => {
    render(<App />);
    expect(screen.getByText("0.5×")).toBeInTheDocument();
    expect(screen.getByText("5×")).toBeInTheDocument();
  });

  it("updates start year on input change", () => {
    render(<App />);
    const inputs = screen.getAllByRole("spinbutton");
    fireEvent.change(inputs[0], { target: { value: "2000" } });
    expect(inputs[0]).toHaveValue(2000);
  });
});

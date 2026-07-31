import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("lists and describes the sourced current model", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          id: "ni_base_2024",
          path: "models/ni_base_2024.yaml",
          name: "NI Historical Model",
          description: "Historical scenario",
          rate_jitter: 0.05,
          random_seed: 42,
          baseline_year: null,
          data_through: null,
          projection_version: null,
          birth_rules: 0,
          death_rules: 0,
          migration_rules: 0,
          internal_migration_rules: 0,
          birth_rate_rules: [],
          death_rate_rules: [],
          migration_rate_rules: [],
          internal_migration_rate_rules: [],
          year_min: 1969,
          year_max: null,
        },
        {
          id: "ni_current",
          path: "models/ni_current.yaml",
          name: "NI Current – NISRA 2024 principal projection",
          description: "Observed components followed by the principal projection.",
          rate_jitter: 0,
          random_seed: 42,
          baseline_year: 2021,
          data_through: 2024,
          projection_version: "NISRA/ONS 2024-based principal projection",
          birth_rules: 53,
          death_rules: 53,
          migration_rules: 103,
          internal_migration_rules: 0,
          birth_rate_rules: [],
          death_rate_rules: [],
          migration_rate_rules: [],
          internal_migration_rate_rules: [],
          year_min: 2022,
          year_max: 2074,
        },
      ],
    } as Response);

    render(<App />);
    const select = await screen.findByLabelText("Scenario definition");
    await waitFor(() => expect(select).toHaveTextContent("NI Current"));
    fireEvent.change(select, { target: { value: "models/ni_current.yaml" } });

    expect(screen.getByText("2021 Census")).toBeInTheDocument();
    expect(screen.getByText("NISRA/ONS 2024-based principal projection")).toBeInTheDocument();
  });

  it("shows the evidence-calibrated voting scenario", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [] } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          eligible_population: 80,
          projected_turnout: 76,
          turnout_rate: 0.95,
          unite_share: 0.36,
          remain_share: 0.42,
          undecided_share: 0.22,
          decided_unite_share: 0.4615,
          intervals: {
            unite_share: { low: 0.333, estimate: 0.36, high: 0.388 },
          },
          scenarios: [
            { id: "remain", label: "All undecided vote remain", unite_share: 0.36 },
            { id: "proportional", label: "Undecided split like decided voters", unite_share: 0.4615 },
            { id: "unite", label: "All undecided vote unite", unite_share: 0.58 },
          ],
          source: { id: "lucidtalk_winter_2025", name: "LucidTalk", sample_size: 1051, fieldwork: "2025", url: "https://www.lucidtalk.co.uk/news/lt-ni-tracker-poll-winter-2025/" },
          limitations: "Adult proxy",
        }),
      } as Response);

    render(<App />);
    expect(await screen.findByText("BORDER POLL SCENARIO")).toBeInTheDocument();
    expect(screen.getByText("95.0%")).toBeInTheDocument();
    expect(screen.getByText("All undecided vote unite")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "LucidTalk" })).toHaveAttribute(
      "href",
      "https://www.lucidtalk.co.uk/news/lt-ni-tracker-poll-winter-2025/",
    );
  });
});

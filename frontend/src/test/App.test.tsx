import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

  it("starts with an explicit random seed that can be changed or regenerated", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => [{
        id: "ni_current", path: "models/ni_current.yaml", name: "NI Current",
        description: "Current model", rate_jitter: 0, random_seed: 42,
        baseline_year: 2021, data_through: 2024, projection_version: "2024-based",
        default_start_year: 2024, default_end_year: 2035,
        birth_rules: 0, death_rules: 0, migration_rules: 0,
        internal_migration_rules: 0, birth_rate_rules: [], death_rate_rules: [],
        migration_rate_rules: [], internal_migration_rate_rules: [],
        year_min: 2024, year_max: 2050,
      }],
    } as Response);
    const randomValues = vi.spyOn(crypto, "getRandomValues")
      .mockImplementation((values) => {
        (values as Uint32Array)[0] = 123456;
        return values;
      });
    render(<App />);
    const seed = await screen.findByLabelText("Simulation seed");
    expect(seed).toHaveValue(123456);

    fireEvent.change(seed, { target: { value: "987" } });
    expect(seed).toHaveValue(987);
    fireEvent.click(screen.getByRole("button", { name: "New seed" }));
    expect(seed).toHaveValue(123456);
    randomValues.mockRestore();
  });

  it("Play button is disabled with no buffered years", () => {
    render(<App />);
    expect(screen.getByText("▶ Play")).toBeDisabled();
  });

  it("defaults to the current model start year", () => {
    render(<App />);
    const inputs = screen.getAllByRole("spinbutton");
    expect(inputs[0]).toHaveValue(2024);
  });

  it("defaults to a useful current projection horizon", () => {
    render(<App />);
    const inputs = screen.getAllByRole("spinbutton");
    expect(inputs[1]).toHaveValue(2035);
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
          default_start_year: 1969,
          default_end_year: 2024,
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
          default_start_year: 2024,
          default_end_year: 2035,
          birth_rules: 53,
          death_rules: 53,
          migration_rules: 103,
          internal_migration_rules: 0,
          birth_rate_rules: [],
          death_rate_rules: [],
          mortality_age_rates: [
            { rate: 149.379433, age_min: 85, age_max: 130 },
          ],
          migration_rate_rules: [],
          internal_migration_rate_rules: [],
          year_min: 2022,
          year_max: 2074,
        },
        {
          id: "ni_current_community",
          path: "models/ni_current_community.yaml",
          name: "NI Current – community-differentiated estimate",
          description: "Estimated community differential.",
          rate_jitter: 0,
          random_seed: 42,
          baseline_year: 2021,
          data_through: 2024,
          projection_version: "Estimated community differential",
          default_start_year: 2024,
          default_end_year: 2050,
          birth_rules: 0,
          death_rules: 0,
          migration_rules: 0,
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

    expect(screen.getByText("2021")).toBeInTheDocument();
    expect(screen.getByText("NISRA/ONS 2024-based principal projection")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Mortality age profile"));
    expect(screen.getByText("149.379433 per 1,000")).toBeInTheDocument();
    expect(screen.getByText("85–130")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Adjust this run"));
    const community = screen.getByRole("group", { name: "Community-specific multipliers" });
    expect(within(community).getByLabelText("Background")).toHaveValue("catholic");
    expect(within(community).getByLabelText("Birth rates")).toHaveValue(1);
    const fullPopulation = screen.getByRole("switch", { name: /Full population/ });
    expect(fullPopulation).not.toBeChecked();
    fireEvent.click(fullPopulation);
    expect(fullPopulation).toBeChecked();
    fireEvent.change(within(community).getByLabelText("Background"), {
      target: { value: "protestant" },
    });
    expect(within(community).getByLabelText("Background")).toHaveValue("protestant");

    fireEvent.change(select, { target: { value: "models/ni_base_2024.yaml" } });
    expect(screen.getByLabelText("Start")).toHaveValue(1969);
    expect(screen.getByLabelText("End")).toHaveValue(2024);
    fireEvent.change(select, { target: { value: "models/ni_current_community.yaml" } });
    expect(screen.getByLabelText("Start")).toHaveValue(2024);
    expect(screen.getByLabelText("End")).toHaveValue(2050);
  });

  it("shows the evidence-calibrated voting scenario", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => [] } as Response)
      .mockResolvedValue({
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
    expect(screen.getByText("Showing LucidTalk")).toBeInTheDocument();
    expect(screen.getByText("95.0%")).toBeInTheDocument();
    expect(screen.getByText("All undecided vote unite")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "LucidTalk" })).toHaveAttribute(
      "href",
      "https://www.lucidtalk.co.uk/news/lt-ni-tracker-poll-winter-2025/",
    );

    fireEvent.change(screen.getByLabelText("Polling calibration"), {
      target: { value: "custom_lucidtalk" },
    });
    const custom = screen.getByRole("group", { name: "Custom polling baseline" });
    expect(within(custom).getByLabelText("Unite %")).toHaveValue(41.4);
    await waitFor(() =>
      expect(fetch).toHaveBeenLastCalledWith(
        expect.stringContaining("custom_unite=41.4"),
        expect.anything(),
      ),
    );
    fireEvent.change(within(custom).getByLabelText("Unite %"), {
      target: { value: "50" },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("must total 100%");
  });
});

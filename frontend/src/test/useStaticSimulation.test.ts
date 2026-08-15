import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../deployment", () => ({
  isStaticDeployment: true,
  loadRecordingManifest: vi.fn().mockResolvedValue({
    schema_version: 1,
    models: [],
    scenarios: [{
      id: "current",
      model_path: "models/current.yaml",
      asset: "/recordings/current.json",
      seed: 1180,
      start_year: 2021,
      end_year: 2022,
      population_size: 1_903_175,
    }],
  }),
}));

import { useSimulationStream } from "../hooks/useSimulationStream";

afterEach(() => vi.unstubAllGlobals());

describe("recorded simulation playback", () => {
  it("loads the matching model recording and filters its year range", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        scenario: { id: "current" },
        snapshots: [
          { year: 2021, total_population: 100 },
          { year: 2022, total_population: 101 },
        ],
      }),
    }));
    const { result } = renderHook(() => useSimulationStream());

    act(() => result.current.startStream(
      2022, 2022, "models/current.yaml", { random_seed: 1180 } as never, "full",
    ));

    await waitFor(() => expect(result.current.status).toBe("complete"));
    expect(result.current.years).toEqual([2022]);
    expect(result.current.snapshots[2022].total_population).toBe(101);
    expect(fetch).toHaveBeenCalledWith(
      "/recordings/current.json",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("reports a missing canonical model recording", async () => {
    const { result } = renderHook(() => useSimulationStream());

    act(() => result.current.startStream(2021, 2022, "models/missing.yaml"));

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toMatch(/No recording/);
  });
});

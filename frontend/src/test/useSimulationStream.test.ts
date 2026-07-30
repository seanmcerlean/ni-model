import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSimulationStream } from "../hooks/useSimulationStream";

interface MockES {
  onmessage: ((e: { data: string }) => void) | null;
  onerror: (() => void) | null;
  listeners: Record<string, () => void>;
  addEventListener: (event: string, cb: () => void) => void;
  close: () => void;
  url: string;
}

let mockEs: MockES;

beforeEach(() => {
  mockEs = {
    onmessage: null,
    onerror: null,
    listeners: {},
    addEventListener(event: string, cb: () => void) { this.listeners[event] = cb; },
    close: vi.fn(),
    url: "",
  };
  vi.stubGlobal(
    "EventSource",
    vi.fn(function EventSourceMock(url: string) {
      mockEs.url = url;
      return mockEs;
    }),
  );
});

afterEach(() => { vi.unstubAllGlobals(); });

describe("useSimulationStream", () => {
  it("starts in idle state", () => {
    const { result } = renderHook(() => useSimulationStream());
    expect(result.current.status).toBe("idle");
    expect(result.current.years).toEqual([]);
  });

  it("sets status to streaming on startStream", () => {
    const { result } = renderHook(() => useSimulationStream());
    act(() => result.current.startStream(2024, 2026));
    expect(result.current.status).toBe("streaming");
  });

  it("buffers snapshots from onmessage events", () => {
    const { result } = renderHook(() => useSimulationStream());
    act(() => result.current.startStream(2024, 2025));

    const snap = { year: 2024, total_population: 100, religious_breakdown: {}, gender_breakdown: {}, location_breakdown: {} };
    act(() => mockEs.onmessage?.({ data: JSON.stringify(snap) }));

    expect(result.current.snapshots[2024]).toEqual(snap);
    expect(result.current.years).toContain(2024);
  });

  it("sets status to complete on complete event", () => {
    const { result } = renderHook(() => useSimulationStream());
    act(() => result.current.startStream(2024, 2024));
    act(() => mockEs.listeners["complete"]?.());
    expect(result.current.status).toBe("complete");
  });

  it("sets status to error on onerror", () => {
    const { result } = renderHook(() => useSimulationStream());
    act(() => result.current.startStream(2024, 2024));
    act(() => mockEs.onerror?.());
    expect(result.current.status).toBe("error");
    expect(result.current.error).toBeTruthy();
  });

  it("abort closes the stream and resets to idle", () => {
    const { result } = renderHook(() => useSimulationStream());
    act(() => result.current.startStream(2024, 2025));
    act(() => result.current.abort());
    expect(mockEs.close).toHaveBeenCalled();
    expect(result.current.status).toBe("idle");
  });

  it("resets snapshots on new startStream call", () => {
    const { result } = renderHook(() => useSimulationStream());
    act(() => result.current.startStream(2024, 2024));
    const snap = { year: 2024, total_population: 50, religious_breakdown: {}, gender_breakdown: {}, location_breakdown: {} };
    act(() => mockEs.onmessage?.({ data: JSON.stringify(snap) }));
    expect(result.current.years).toHaveLength(1);

    act(() => result.current.startStream(2025, 2025));
    expect(result.current.years).toHaveLength(0);
    expect(result.current.snapshots).toEqual({});
  });

  it("builds correct SSE URL with params", () => {
    const { result } = renderHook(() => useSimulationStream());
    act(() => result.current.startStream(1969, 2024, "models/custom.yaml"));
    expect(mockEs.url).toContain("start_year=1969");
    expect(mockEs.url).toContain("end_year=2024");
    expect(mockEs.url).toContain("model_path=models%2Fcustom.yaml");
  });
});

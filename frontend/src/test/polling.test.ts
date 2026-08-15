import { describe, expect, it } from "vitest";

import { allocateUndecided, applyPollingShock } from "../polling";

const prediction = {
  unite_share: 0.36,
  remain_share: 0.42,
  undecided_share: 0.22,
};

describe("allocateUndecided", () => {
  it("keeps the evidence-calibrated undecided share by default", () => {
    expect(allocateUndecided(prediction, "reported")).toEqual(prediction);
  });

  it("reports the headline split among decided voters", () => {
    expect(allocateUndecided(prediction, "decided")).toEqual({
      unite_share: 0.36 / 0.78,
      remain_share: 0.42 / 0.78,
      undecided_share: 0,
    });
  });

  it("does not invent a result when nobody has decided", () => {
    const allUndecided = { unite_share: 0, remain_share: 0, undecided_share: 1 };
    expect(allocateUndecided(allUndecided, "decided")).toEqual(allUndecided);
  });
});

describe("applyPollingShock", () => {
  const fullPrediction = {
    ...prediction,
    eligible_population: 100,
    projected_turnout: 80,
    turnout_rate: 0.8,
    decided_unite_share: 0.36 / 0.78,
    intervals: { unite_share: { low: 0.33, estimate: 0.36, high: 0.39 } },
    scenarios: [{ id: "base", label: "Base", unite_share: 0.36 }],
    source: { id: "test", name: "Test", sample_size: 100, fieldwork: "2025", url: "https://example.com" },
    limitations: "Test",
    by_location: {},
  };

  it("does nothing in the default neutral scenario", () => {
    expect(applyPollingShock(fullPrediction, "neutral")).toBe(fullPrediction);
  });

  it("transfers the observed 4.6-point change from Remain to Unite", () => {
    const result = applyPollingShock(fullPrediction, "brexit");

    expect(result?.unite_share).toBeCloseTo(0.406);
    expect(result?.remain_share).toBeCloseTo(0.374);
    expect(result?.undecided_share).toBe(0.22);
    expect(result?.intervals.unite_share.estimate).toBeCloseTo(0.406);
  });

  it("can apply the equal opposite shock", () => {
    const result = applyPollingShock(fullPrediction, "anti_brexit");

    expect(result?.unite_share).toBeCloseTo(0.314);
    expect(result?.remain_share).toBeCloseTo(0.466);
  });
});

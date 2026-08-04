import { describe, expect, it } from "vitest";

import { allocateUndecided } from "../polling";

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

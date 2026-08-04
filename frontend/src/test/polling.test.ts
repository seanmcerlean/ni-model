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

  it("can force the full undecided pool to either outcome", () => {
    expect(allocateUndecided(prediction, "unite")).toEqual({
      unite_share: 0.58,
      remain_share: 0.42,
      undecided_share: 0,
    });
    expect(allocateUndecided(prediction, "remain")).toEqual({
      unite_share: 0.36,
      remain_share: 0.64,
      undecided_share: 0,
    });
  });
});

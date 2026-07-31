import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocationDetail } from "../components/LocationDetail";

describe("LocationDetail", () => {
  it("shows a poll-calibrated area estimate and its limitation", () => {
    const onClose = vi.fn();
    render(<LocationDetail
      locationId="belfast"
      year={2030}
      detail={{
        total: 100,
        religious_breakdown: { catholic: 55, protestant: 25, none: 20 },
        gender_breakdown: { female: 52, male: 48 },
        origin_breakdown: { ni: 90, elsewhere: 10 },
        age_bands: { "18_34": 40, "35_64": 40, "65_plus": 20 },
      }}
      voting={{
        eligible_population: 80,
        projected_turnout: 76,
        turnout_rate: 0.95,
        unite_share: 0.57,
        remain_share: 0.33,
        undecided_share: 0.10,
        decided_unite_share: 0.633,
        intervals: {},
        scenarios: [],
      }}
      pollingSource="LucidTalk"
      onClose={onClose}
    />);

    expect(screen.getByText("57.0%")).toBeInTheDocument();
    expect(screen.getByText(/Not area-level polling/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close area details" }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});

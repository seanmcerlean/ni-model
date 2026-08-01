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

  it("uses stable semantic ordering instead of response insertion order", () => {
    const { container } = render(<LocationDetail
      locationId="belfast"
      year={2030}
      detail={{
        total: 100,
        religious_breakdown: { none: 10, other: 5, protestant: 35, catholic: 50 },
        gender_breakdown: { other: 1, male: 48, female: 51 },
        origin_breakdown: { other: 5, gb: 10, roi: 5, ni: 80 },
        age_bands: { "80_plus": 5, "35_49": 25, under_18: 20, "65_79": 10, "18_34": 25, "50_64": 15 },
      }}
      voting={null}
      pollingSource={null}
      onClose={vi.fn()}
    />);

    const sections = [...container.querySelectorAll(".detail-section")];
    const labels = (section: Element) => [...section.querySelectorAll(".detail-bar-label")]
      .map((element) => element.textContent);
    expect(labels(sections[0])).toEqual(["Catholic", "Protestant", "Other", "None"]);
    expect(labels(sections[1])).toEqual(["Female", "Male", "Other"]);
    expect(labels(sections[2])).toEqual(["Ni", "Roi", "Gb", "Other"]);
    expect(labels(sections[3])).toEqual(["Under 18", "18 34", "35 49", "50 64", "65 79", "80 Plus"]);
  });
});

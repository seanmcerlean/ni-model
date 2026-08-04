import { describe, expect, it } from "vitest";

import { blendedColour } from "../components/NiMap";

describe("NI map colouring", () => {
  it("blends category colours in proportion to their shares", () => {
    expect(blendedColour([
      [0.5, [22, 163, 74]],
      [0.5, [37, 99, 235]],
    ])).toBe("rgb(30, 131, 155)");
  });

  it("uses a neutral fallback when no category data is available", () => {
    expect(blendedColour([])).toBe("#475569");
  });
});

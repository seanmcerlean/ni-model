import { describe, expect, it } from "vitest";

import { blendedColour } from "../components/NiMap";

describe("NI map colouring", () => {
  it("blends category colours in proportion to their shares", () => {
    expect(blendedColour([
      [0.5, [22, 163, 74]],
      [0.5, [249, 115, 22]],
    ])).toBe("rgb(136, 139, 48)");
  });

  it("can sharpen a blend without replacing it with a solid category colour", () => {
    expect(blendedColour([
      [0.7, [34, 197, 94]],
      [0.3, [14, 165, 233]],
    ], 2.4)).toBe("rgb(32, 193, 110)");
  });

  it("uses a neutral fallback when no category data is available", () => {
    expect(blendedColour([])).toBe("#475569");
  });
});

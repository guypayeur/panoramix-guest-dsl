import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { progressBits } from "./api.js";

describe("progressBits", () => {
  it("omits when progress is missing", () => {
    assert.deepEqual(progressBits({}), []);
    assert.deepEqual(progressBits({ progress: null }), []);
  });

  it("shows walls/BEL only when supplied — never invents percent", () => {
    const bits = progressBits({
      progress: {
        elapsed: 34.227,
        bel: -152058908.82,
        walls: { wall_sec_time: 34.227 },
        executed: true,
        catalog: "reserve-f32",
      },
    });
    assert.ok(bits.includes("34.227s"));
    assert.ok(bits.includes("BEL -152058908.82"));
    assert.ok(bits.includes("executed"));
    assert.ok(bits.includes("reserve-f32"));
    assert.ok(!bits.some((bit) => String(bit).includes("%")));
  });
});

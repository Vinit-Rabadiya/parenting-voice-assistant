import assert from "node:assert/strict";
import { test } from "node:test";
import { mergeChunks } from "../../frontend/src/utils/audio.js";

test("merges audio batches in order", () => {
  const chunks = [new Float32Array([0.25, -0.5]), new Float32Array([0.75])];

  const result = mergeChunks(chunks);
  const expected = new Float32Array([0.25, -0.5, 0.75]);
  assert.deepEqual(result, expected);
});

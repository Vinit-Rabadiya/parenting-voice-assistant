import assert from "node:assert/strict";
import { test } from "node:test";
import { encodeWav, mergeChunks } from "../../frontend/src/utils/audio.js";

test("merges audio batches in order", () => {
  const chunks = [new Float32Array([0.25, -0.5]), new Float32Array([0.75])];

  const result = mergeChunks(chunks);
  const expected = new Float32Array([0.25, -0.5, 0.75]);
  assert.deepEqual(result, expected);
});

// verify the header describes the exact audio format accepted by the backend.
test("encodes a one-second mono pcm wav with correct header sizes", async () => {
  const blob = encodeWav(new Float32Array(16000));
  const buffer = await blob.arrayBuffer();
  const view = new DataView(buffer);
  const label = (offset) => new TextDecoder().decode(new Uint8Array(buffer, offset, 4));

  assert.equal(blob.type, "audio/wav");
  assert.equal(blob.size, 32044);
  assert.equal(label(0), "RIFF");
  assert.equal(view.getUint32(4, true), blob.size - 8);
  assert.equal(label(8), "WAVE");
  assert.equal(label(12), "fmt ");
  assert.equal(view.getUint32(16, true), 16);
  assert.equal(view.getUint16(20, true), 1);
  assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(24, true), 16000);
  assert.equal(view.getUint32(28, true), 32000);
  assert.equal(view.getUint16(32, true), 2);
  assert.equal(view.getUint16(34, true), 16);
  assert.equal(label(36), "data");
  assert.equal(view.getUint32(40, true), 32000);
});

// check signed conversion, clipping, sample order, and unchanged input.
test("converts float samples to pcm16 without modifying the recording", async () => {
  const samples = new Float32Array([-2, -1, -0.5, 0, 0.5, 1, 2]);
  const original = samples.slice();
  const view = new DataView(await encodeWav(samples).arrayBuffer());
  const actual = Array.from({ length: samples.length }, (_, i) => view.getInt16(44 + i * 2, true));

  assert.deepEqual(actual, [-32768, -32768, -16384, 0, 16383, 32767, 32767]);
  assert.deepEqual(samples, original);
});

// an empty or incorrectly typed value is not a captured sample array.
test("rejects missing, empty, and incorrectly typed samples", () => {
  for (const input of [undefined, null, [], [0.5], new Float32Array()]) {
    assert.throws(() => encodeWav(input), /nonempty Float32Array/);
  }
});

// invalid numbers must not silently become silence or clipped samples.
test("rejects nonfinite sample values", () => {
  for (const sample of [NaN, Infinity, -Infinity]) {
    assert.throws(() => encodeWav(new Float32Array([sample])), /finite numbers/);
  }
});

// enforce the same duration boundary as the backend validator.
test("accepts exactly 30 seconds and rejects one extra sample", () => {
  assert.equal(encodeWav(new Float32Array(480000)).size, 960044);
  assert.throws(() => encodeWav(new Float32Array(480001)), /30 seconds/);
});

// merged batches must keep their order when packaged into a wav.
test("encodes merged audio batches in their original order", async () => {
  const samples = mergeChunks([new Float32Array([0.25, -0.5]), new Float32Array([0.75])]);
  const view = new DataView(await encodeWav(samples).arrayBuffer());
  assert.equal(view.getUint32(40, true), 6);
  assert.deepEqual([44, 46, 48].map((offset) => view.getInt16(offset, true)), [8191, -16384, 24575]);
});

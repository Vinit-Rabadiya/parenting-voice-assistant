const TARGET_SAMPLE_RATE = 16000;
const MAX_RECORDING_SECONDS = 30;

export function mergeChunks(chunks) {
  let totalSamples = 0;
  for (const chunk of chunks) {
    totalSamples += chunk.length;
  }
  const samples = new Float32Array(totalSamples);
  let offset = 0;
  for (const chunk of chunks) {
    samples.set(chunk, offset);
    offset += chunk.length;
  }
  return samples;
}

export async function resampleAudio(samples, sourceSampleRate) {
  if (samples.length === 0) {
    throw new Error("Audio must contain at least one sample.");
  }
  if (!Number.isFinite(sourceSampleRate) || sourceSampleRate <= 0) {
    throw new Error("Sample rate must be a finite positive number.");
  }
  if (sourceSampleRate === TARGET_SAMPLE_RATE) {
    return samples;
  }
  const outputLength = Math.floor((samples.length * TARGET_SAMPLE_RATE) / sourceSampleRate);
  if (outputLength < 1) {
    throw new Error("Audio is too short to resample.");
  }

  const context = new OfflineAudioContext({
    numberOfChannels: 1,
    length: outputLength,
    sampleRate: TARGET_SAMPLE_RATE,
  });

  const inputBuffer = context.createBuffer(1, samples.length, sourceSampleRate);

  inputBuffer.copyToChannel(samples, 0);

  const source = context.createBufferSource();
  source.buffer = inputBuffer;
  source.connect(context.destination);
  source.start();
  const rendered = await context.startRendering();
  return rendered.getChannelData(0);
}

// package mono samples already resampled to 16000 hz as a pcm wav blob.
export function encodeWav(samples) {
  // reject invalid input before allocating the output file.
  if (!(samples instanceof Float32Array) || samples.length === 0) {
    throw new Error("WAV encoding requires a nonempty Float32Array.");
  }
  if (samples.length > TARGET_SAMPLE_RATE * MAX_RECORDING_SECONDS) {
    throw new Error("Audio recording must not exceed 30 seconds.");
  }
  for (const sample of samples) {
    if (!Number.isFinite(sample)) {
      throw new Error("Audio samples must contain only finite numbers.");
    }
  }

  // reserve 44 header bytes and two bytes for each 16-bit sample.
  const audioByteCount = samples.length * 2;
  const buffer = new ArrayBuffer(44 + audioByteCount);
  const view = new DataView(buffer);

  // write the short text labels required by the wav format.
  function writeLabel(offset, label) {
    for (let i = 0; i < label.length; i++) {
      view.setUint8(offset + i, label.charCodeAt(i));
    }
  }

  // describe the file size, pcm format, mono channel, and sample rate.
  // true tells the numeric writers to use wav's little-endian byte order.
  writeLabel(0, "RIFF");
  view.setUint32(4, 36 + audioByteCount, true);
  writeLabel(8, "WAVE");
  writeLabel(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, TARGET_SAMPLE_RATE, true);
  view.setUint32(28, TARGET_SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeLabel(36, "data");
  view.setUint32(40, audioByteCount, true);

  // clamp each float and convert it to a signed 16-bit audio value.
  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    const pcm = Math.trunc(sample * (sample < 0 ? 32768 : 32767));
    view.setInt16(44 + i * 2, pcm, true);
  }

  // return binary data that a future request can send directly to the backend.
  return new Blob([buffer], { type: "audio/wav" });
}

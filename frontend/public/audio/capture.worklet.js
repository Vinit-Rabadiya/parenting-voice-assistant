/* global AudioWorkletProcessor, registerProcessor */

// loaded by the microphone hook into the browser's audio processing thread.
// collect microphone samples and send them to the recording hook.
class MicrophoneCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    // reuse a small buffer instead of storing the entire recording here.
    this.buffer = new Float32Array(2048);
    this.offset = 0;
    this.stopped = false;

    // finish the recording when the hook requests a stop.
    this.port.onmessage = (event) => {
      if (event.data?.type !== "stop" || this.stopped) return;

      this.stopped = true;
      this.flush();
      this.port.postMessage({ type: "stopped" });
    };
  }

  // send the filled part of the buffer and reset its position.
  flush() {
    if (this.offset === 0) return;

    const samples = this.buffer.slice(0, this.offset);
    this.port.postMessage({ type: "samples", samples });
    this.offset = 0;
  }

  process(inputs) {
    // stop collecting samples after a stop request.
    if (this.stopped) return false;

    const channels = inputs[0];
    if (!channels || channels.length === 0) return true;

    // combine the input channels into mono samples.
    for (let i = 0; i < channels[0].length; i++) {
      let sum = 0;

      for (const channel of channels) {
        sum += channel[i];
      }

      this.buffer[this.offset] = sum / channels.length;
      this.offset += 1;

      // send each full buffer to the hook.
      if (this.offset === this.buffer.length) {
        this.flush();
      }
    }

    return true;
  }
}

// this name is used when the hook creates the audio node.
registerProcessor("microphone-capture", MicrophoneCaptureProcessor);

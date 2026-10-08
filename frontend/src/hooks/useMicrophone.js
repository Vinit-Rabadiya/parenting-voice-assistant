import { useRef, useState, useEffect, useCallback } from "react";
import { createWavBlob } from "../utils/audio";

const MAX_RECORDING_SECONDS = 30;
const STOP_TIMEOUT_MS = 2000;

// release only the resources belonging to this recording session.
function disposeSession(session) {
  if (!session) return;
  clearTimeout(session.limitTimer);
  clearTimeout(session.stopTimer);
  if (session.node) {
    session.node.port.onmessage = null;
    session.node.onprocessorerror = null;
    session.node.port.close();
    session.node.disconnect();
  }
  session.source?.disconnect();
  session.stream?.getTracks().forEach((track) => {
    track.onended = null;
    track.stop();
  });
  if (session.context && session.context.state !== "closed") {
    void session.context.close().catch(() => {});
  }
}

// keep recording resources separate from the state displayed by components.
function useMicrophone() {
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [recording, setRecording] = useState(null);
  const requestIdRef = useRef(0);
  const sessionRef = useRef(null);

  // cancel pending setup and discard unfinished audio without updating the ui.
  const releaseMicrophone = useCallback(() => {
    requestIdRef.current += 1;
    const session = sessionRef.current;
    sessionRef.current = null;
    disposeSession(session);
  }, []);

  // stop gracefully so the processor can send its last partial buffer.
  const stop = useCallback(() => {
    const session = sessionRef.current;
    if (!session) return;

    // cancel pending permission or ignore unfinished audio conversion.
    if (!session.started || session.preparing) {
      releaseMicrophone();
      setStatus("idle");
      return;
    }
    if (session.stopping) return;
    session.stopping = true;
    clearTimeout(session.limitTimer);
    setStatus("stopping");

    // a suspended or failed processor must not leave the microphone open.
    session.stopTimer = setTimeout(() => {
      if (sessionRef.current !== session) return;
      releaseMicrophone();
      setError("Recording could not finish. Please start a new recording.");
      setStatus("idle");
    }, STOP_TIMEOUT_MS);

    try {
      session.node.port.postMessage({ type: "stop" });
    } catch {
      releaseMicrophone();
      setError("Recording could not stop normally. Please try again.");
      setStatus("idle");
    }
  }, [releaseMicrophone]);

  // create one audio session for each user-triggered recording attempt.
  async function start() {
    if (sessionRef.current) return;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (
      !navigator.mediaDevices?.getUserMedia ||
      !AudioCtx ||
      !window.AudioWorkletNode
    ) {
      setError("Recording requires a supported browser on HTTPS or localhost.");
      return;
    }

    const requestId = ++requestIdRef.current;
    const session = {
      context: null,
      stream: null,
      source: null,
      node: null,
      chunks: [],
      sampleCount: 0,
      started: false,
      stopping: false,
      preparing: false,
      limitTimer: null,
      stopTimer: null,
    };
    sessionRef.current = session;
    setError("");
    setRecording(null);
    setStatus("requesting");

    // old permission responses and messages must not affect a newer session.
    const isCurrent = () =>
      sessionRef.current === session && requestIdRef.current === requestId;
    const fail = (message) => {
      if (!isCurrent()) return;
      releaseMicrophone();
      setError(message);
      setStatus("idle");
    };

    try {
      // resume during the user action and load the processor before creating its node.
      session.context = new AudioCtx();
      await session.context.resume();
      if (!isCurrent()) return;
      await session.context.audioWorklet.addModule("/audio/capture.worklet.js");
      if (!isCurrent()) return;

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!isCurrent()) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      session.stream = stream;
      session.source = session.context.createMediaStreamSource(stream);
      session.node = new AudioWorkletNode(
        session.context,
        "microphone-capture",
      );

      session.node.port.onmessage = async ({ data }) => {
        if (!isCurrent()) return;
        if (data.type === "samples") {
          // use the actual sample rate and trim any batch crossing the duration limit.
          const maximum = session.context.sampleRate * MAX_RECORDING_SECONDS;
          const remaining = maximum - session.sampleCount;
          if (remaining > 0) {
            const samples =
              data.samples.length <= remaining
                ? data.samples
                : data.samples.slice(0, remaining);
            session.chunks.push(samples);
            session.sampleCount += samples.length;
          }
          if (session.sampleCount >= maximum) stop();
        } else if (data.type === "stopped" && session.stopping && !session.preparing) {
          // the processor sends its final samples before this acknowledgement.
          const result = {
            chunks: session.chunks,
            sampleRate: session.context.sampleRate,
          };
          if (session.sampleCount === 0) {
            fail("No audio was captured. Please try recording again.");
            return;
          }

          // close the microphone while keeping this session's identity for conversion.
          session.preparing = true;
          disposeSession(session);
          setStatus("preparing");

          try {
            // combine, resample, and encode using the existing audio utility.
            const wavBlob = await createWavBlob(result);

            // cancelled or unmounted sessions must not publish late results.
            if (!isCurrent()) return;

            releaseMicrophone();
            setRecording({
              chunks: result.chunks,
              sampleRate: result.sampleRate,
              wavBlob,
            });
            setStatus("idle");
          } catch {
            fail("Could not prepare the recording. Please record again.");
          }
        }
      };
      session.node.onprocessorerror = () =>
        fail("Audio capture failed. Please record again.");
      stream.getTracks().forEach((track) => {
        track.onended = () =>
          fail(
            "Microphone disconnected or access was revoked. Please try again.",
          );
      });

      // the worklet outputs silence, so this does not play the mic through speakers.
      session.source.connect(session.node);
      session.node.connect(session.context.destination);
      session.started = true;
      setStatus("recording");
      session.limitTimer = setTimeout(stop, MAX_RECORDING_SECONDS * 1000);
    } catch (cause) {
      if (cause.name === "NotAllowedError") {
        fail(
          "Microphone access was denied. Open the site controls beside your browser’s address bar, " +
            "set Microphone to Allow, then reload this page and try again. " +
            "If access is still denied, check your device’s microphone privacy settings.",
        );
      } else {
        fail(
          "Could not start recording. Check your microphone and browser settings.",
        );
      }
    }
  }

  // leaving the page discards unfinished audio and releases its resources.
  useEffect(() => releaseMicrophone, [releaseMicrophone]);

  return { status, error, recording, start, stop };
}

export default useMicrophone;

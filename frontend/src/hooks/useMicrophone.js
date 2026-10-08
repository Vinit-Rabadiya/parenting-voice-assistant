import { useRef, useState, useEffect, useCallback } from "react";

// manage microphone access and share its status with the interface.
function useMicrophone() {
  // state changes update the status and error shown on screen.
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  // refs keep the stream and request details between renders.
  const streamRef = useRef(null);
  const requestIdRef = useRef(0);
  const requestingRef = useRef(false);

  // invalidate pending requests and release microphone access.
  const releaseMicrophone = useCallback(() => {
    requestIdRef.current += 1;
    requestingRef.current = false;

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  }, []);

  // request microphone access when the user presses start.
  async function start() {
    // avoid opening another microphone request or stream.
    if (requestingRef.current || streamRef.current) {
      return;
    }

    // check that microphone access is available in this browser context.
    if (!navigator.mediaDevices?.getUserMedia) {
      setError(
        "Microphone access requires a supported browser on HTTPS or localhost.",
      );
      return;
    }
    // mark the request as pending and clear the previous error.
    requestingRef.current = true;
    setError("");
    setStatus("requesting");
    // give this request an id so late results can be ignored.
    const requestId = ++requestIdRef.current;

    try {
      // wait for microphone permission and an audio stream.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // release the returned stream if this request is no longer current.
      if (requestId !== requestIdRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      } else {
        // keep the stream for later audio capture; recording has not started yet.
        streamRef.current = stream;
        setStatus("ready");
      }
    } catch (cause) {
      // report failures only if they belong to the current request.
      if (requestId === requestIdRef.current) {
        // explain how to restore access when permission is denied.
        if (cause.name === "NotAllowedError") {
          setError(
            "Microphone access was denied. Open the site controls beside your browser’s address bar, " +
              "set Microphone to Allow, then reload this page and click Enable Microphone. " +
              "If access is still denied, allow microphone access for your browser in your device’s privacy settings.",
          );
        } else {
          setError(
            "Could not access the microphone. Check permissions and your device.",
          );
        }
        setStatus("idle");
      }
    } finally {
      // finish this request without changing a newer request's pending state.
      if (requestId === requestIdRef.current) {
        requestingRef.current = false;
      }
    }
  }

  function stop() {
    releaseMicrophone();
    setStatus("idle");
  }

  // release the microphone when the component leaves the page.
  useEffect(() => {
    return () => {
      releaseMicrophone();
    };
  }, [releaseMicrophone]);
  // let components display state and request microphone access.
  return { status, error, start, stop };
}

export default useMicrophone;

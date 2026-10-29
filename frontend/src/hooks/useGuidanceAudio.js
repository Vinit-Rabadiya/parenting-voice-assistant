import { useCallback, useEffect, useRef, useState } from "react";

// Speech synthesis is shared by the browser. Only one answer can own it.
let currentPlayback = null;
export function stopGuidanceAudio() {
  currentPlayback?.stop();
}

function speechText(text) {
  // Remove presentation markers only from playback, preserving the saved answer.
  return text
    .replace(/\[([^\]]+)\]\(https?:\/\/[^\s)]+\)/g, "$1")
    .replace(/^[ \t]*[-*_]{3,}[ \t]*$/gm, "")
    .replace(/^[ \t]*(?:#{1,6}|>|[-*•]|\d+[.)])[ \t]+/gm, "")
    .replace(/\\([*`_])/g, "$1")
    .replace(/[*`]+/g, "")
    .replace(/(__|_)(\S(?:[\s\S]*?\S)?)\1/g, "$2")
    .trim();
}

export default function useGuidanceAudio(text, { automatic = false, ready = true, active = true } = {}) {
  const [state, setState] = useState("stopped");
  const [message, setMessage] = useState("");
  const [hint, setHint] = useState(false);
  const playback = useRef(null);
  const attempted = useRef(false);

  const stop = useCallback((notify = true) => {
    const attempt = playback.current;
    if (!attempt) return;
    attempted.current = true;
    playback.current = null;
    clearTimeout(attempt.timer);
    attempt.utterance.onstart = attempt.utterance.onend = attempt.utterance.onerror = attempt.utterance.onpause = null;
    if (currentPlayback === attempt) {
      currentPlayback = null;
      try { window.speechSynthesis?.cancel(); }
      catch { /* The text and manual replay remain available. */ }
    }
    if (notify) { setState("stopped"); setMessage(""); setHint(false); }
  }, []);

  const play = useCallback(() => {
    attempted.current = true;
    stopGuidanceAudio();
    setHint(false);
    setMessage("");
    const synth = window.speechSynthesis;
    if (typeof synth?.speak !== "function" || typeof window.SpeechSynthesisUtterance !== "function") {
      setState("error");
      setMessage("Audio playback is unavailable in this browser. You can still read the answer.");
      return;
    }
    let attempt;
    try {
      const utterance = new window.SpeechSynthesisUtterance(speechText(text));
      utterance.rate = 0.95;
      utterance.volume = 1;
      attempt = { utterance, stop: () => stop(), timer: null };
      playback.current = currentPlayback = attempt;
      const finish = (next, detail = "", showHint = false) => {
        if (playback.current !== attempt) return;
        stop(false);
        setState(next); setMessage(detail); setHint(showHint ? {} : false);
      };
      utterance.onstart = () => {
        if (playback.current !== attempt) return;
        clearTimeout(attempt.timer);
        // This is the utterance's volume, never the device's physical volume.
        if (utterance.volume === 0) finish("error", "Audio is muted. Select Listen to try again.", true);
        else setState("playing");
      };
      utterance.onend = () => finish("finished");
      utterance.onpause = () => finish("stopped", "Audio was interrupted. Select Listen to play again.", true);
      utterance.onerror = (event) => {
        if (event.error === "not-allowed") finish("error", "Playback was blocked. Select Listen to play the guidance.", true);
        else if (["canceled", "interrupted"].includes(event.error)) finish("stopped", "Audio was interrupted. Select Listen to play again.", true);
        else finish("error", "Audio could not be played. You can still read the answer or try Listen again.");
      };
      setState("preparing");
      // Some engines never emit an error when autoplay is denied.
      attempt.timer = setTimeout(() => finish("error", "Audio did not start. Select Listen to try again.", true), 8000);
      synth.speak(utterance);
    } catch {
      if (attempt) stop(false);
      setState("error");
      setMessage("Audio could not be played. You can still read the answer or try Listen again.");
    }
  }, [text, stop]);

  useEffect(() => {
    if (!active) {
      attempted.current = true;
      const timer = setTimeout(stop, 0);
      return () => clearTimeout(timer);
    }
    if (!automatic || !ready || attempted.current) return;
    // Scheduling lets StrictMode discard its first effect without double speech.
    const timer = setTimeout(() => { if (!attempted.current) play(); }, 0);
    return () => clearTimeout(timer);
  }, [automatic, ready, active, play, stop]);

  useEffect(() => {
    if (!hint) return;
    const timer = setTimeout(() => setHint(false), 5000);
    return () => clearTimeout(timer);
  }, [hint]);
  useEffect(() => () => stop(false), [text, stop]);

  return { state, message, hint, play, stop, dismissHint: () => setHint(false) };
}

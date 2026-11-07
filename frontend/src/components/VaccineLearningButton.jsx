import { useCallback, useEffect, useRef, useState } from "react";
import { stopGuidanceAudio } from "../hooks/useGuidanceAudio";

// Only this small launcher is part of the chat bundle. Content and styles load on click.
export default function VaccineLearningButton({ disabled, onAsk, askDisabled, hasDraft, onOpenChange }) {
  const [Panel, setPanel] = useState(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const trigger = useRef(null);
  const request = useRef(0);

  const close = useCallback(() => {
    stopGuidanceAudio();
    setOpen(false);
    onOpenChange(false);
    trigger.current?.focus();
  }, [onOpenChange]);

  useEffect(() => () => {
    request.current += 1;
    onOpenChange(false);
  }, [onOpenChange]);

  async function show() {
    stopGuidanceAudio();
    setError("");
    setOpen(true);
    onOpenChange(true);
    if (Panel) return;
    const attempt = ++request.current;
    setLoading(true);
    try {
      const module = await import("./VaccineLearning");
      if (attempt === request.current) setPanel(() => module.default);
    } catch {
      if (attempt !== request.current) return;
      setError("Vaccine explanations could not be loaded. Select Understand vaccines to retry.");
      close();
    } finally {
      if (attempt === request.current) setLoading(false);
    }
  }

  return <>
    <button type="button" ref={trigger} disabled={disabled || loading} aria-haspopup="dialog"
      aria-busy={loading} onClick={show}>Understand vaccines</button>
    {loading && <span role="status">Loading vaccine explanations…</span>}
    {error && <span role="alert">{error}</span>}
    {open && Panel && <Panel onClose={close} hasDraft={hasDraft} askDisabled={askDisabled}
      onAsk={(question) => { close(); onAsk(question); }} />}
  </>;
}

const INTERRUPTED = "Reply interrupted. Reopen this conversation to check for a reply before sending again.";

export async function readCoachingStream(response, { check, onEvent } = {}) {
  if (!response.body?.getReader) throw new Error(INTERRUPTED);
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let buffer = "", final = null, events = 0, characters = 0;
  function frame(value) {
    const lines = value.split(/\r?\n/);
    const type = lines.find(line => line.startsWith("event:"))?.slice(6).trim();
    const raw = lines.filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n");
    if (!raw) return; // Heartbeats carry no application data.
    if (++events > 4096 || final) throw new Error(INTERRUPTED);
    const data = JSON.parse(raw);
    if (type === "error") {
      const status = Number.isInteger(data.status) ? data.status : 502;
      const error = new Error(status >= 500 ? "Something went wrong. Please try again."
        : typeof data.detail === "string" ? data.detail : INTERRUPTED);
      error.status = status;
      throw error;
    }
    if (type === "delta") {
      if (typeof data.text !== "string" || (characters += data.text.length) > 16000) throw new Error(INTERRUPTED);
      onEvent?.({ type, text: data.text });
    } else if (type === "reset") {
      characters = 0;
      onEvent?.({ type });
    } else if (type === "status") {
      if (!["preparing", "writing", "saving"].includes(data.phase)) throw new Error(INTERRUPTED);
      onEvent?.({ type, phase: data.phase });
    } else if (type === "ready") {
      onEvent?.({ type, response: data.response });
    } else if (type === "done") {
      final = data.response;
    } else {
      throw new Error(INTERRUPTED);
    }
  }
  try {
    while (true) {
      check?.();
      const { value, done } = await reader.read();
      check?.();
      buffer += decoder.decode(value, { stream: !done });
      if (buffer.length > 65536) throw new Error(INTERRUPTED);
      let boundary;
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        frame(buffer.slice(0, boundary.index));
        buffer = buffer.slice(boundary.index + boundary[0].length);
      }
      if (done) break;
    }
    if (!final || buffer.trim()) throw new Error(INTERRUPTED);
    return final;
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

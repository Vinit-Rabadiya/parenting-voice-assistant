import { useEffect, useState } from "react";

function safeLink(value) {
  try { return ["http:", "https:"].includes(new URL(value).protocol); }
  catch { return false; }
}

export default function GuidanceText({ text, animate = false, active = true, onComplete }) {
  const [visible, setVisible] = useState(animate ? 0 : Infinity);
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const total = text.match(/\S+\s*/g)?.length || 0;
  const complete = visible >= total || !animate || !active || reducedMotion;
  useEffect(() => {
    const finish = () => { setVisible(Infinity); onComplete?.(); };
    if (!animate || !active || reducedMotion || !total) {
      const timer = setTimeout(finish, 0);
      return () => clearTimeout(timer);
    }
    const started = performance.now();
    const duration = Math.min(1400, Math.max(180, total * 14));
    const timer = setInterval(() => {
      const count = Math.ceil(total * (performance.now() - started) / duration);
      setVisible(Math.min(total, count));
      if (count >= total) { clearInterval(timer); onComplete?.(); }
    }, 25);
    return () => clearInterval(timer);
  }, [text, animate, active, reducedMotion, total, onComplete]);

  return <div className="guidance-text" aria-live="polite" aria-busy={!complete}>
    {renderContent(text, visible, complete)}
  </div>;
}

// Parse the complete answer, revealing words without changing final line wrapping.
// React text nodes never execute supplied HTML.
function renderContent(text, visible, complete) {
  let word = 0;
  function words(value) {
    if (complete) return value;
    return value.split(/(\S+\s*)/).filter(Boolean).map((part, index) => {
      if (!/\S/.test(part)) return part;
      word += 1;
      const pending = !complete && word > visible;
      return <span key={index} className={pending ? "guidance-word--pending" : undefined} aria-hidden={pending || undefined}>{part}</span>;
    });
  }
  function inline(value) {
    return value.split(/(\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g).map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{words(part.slice(2, -2))}</strong>;
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
      if (link && safeLink(link[2])) {
        const pending = !complete && word + 1 > visible;
        return <a key={index} href={link[2]} target="_blank" rel="noreferrer" tabIndex={pending ? -1 : undefined}>{words(link[1])}</a>;
      }
      return <span key={index}>{words(part)}</span>;
    });
  }
  const blocks = [];
  const lines = text.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) continue;
    const list = /^(?:\s*[-*•]\s+|\s*\d+[.)]\s+)/;
    if (list.test(line)) {
      const ordered = /^\s*\d/.test(line);
      const items = [];
      while (index < lines.length && list.test(lines[index]) && /^\s*\d/.test(lines[index]) === ordered) {
        items.push(<li key={index}>{inline(lines[index].replace(list, ""))}</li>);
        index += 1;
      }
      index -= 1;
      const List = ordered ? "ol" : "ul";
      blocks.push(<List key={`list-${index}`}>{items}</List>);
    } else if (/^#{1,6}\s+/.test(line)) {
      blocks.push(<h3 key={index}>{inline(line.replace(/^#{1,6}\s+/, ""))}</h3>);
    } else blocks.push(<p key={index}>{inline(line)}</p>);
  }
  return blocks;
}

function safeLink(value) {
  try { return ["http:", "https:"].includes(new URL(value).protocol); }
  catch { return false; }
}

export default function GuidanceText({ text }) {
  return <div className="guidance-text" aria-live="polite" aria-busy={false}>{renderContent(text)}</div>;
}

// Render checked text as it arrives. React text nodes never execute supplied HTML.
function renderContent(text) {
  function inline(value) {
    return value.split(/(\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g).map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
      if (link && safeLink(link[2])) {
        return <a key={index} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</a>;
      }
      return <span key={index}>{part}</span>;
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

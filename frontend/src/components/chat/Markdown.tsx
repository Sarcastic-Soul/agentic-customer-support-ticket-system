import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// Replies come from the LLM (or a human agent) with **bold**, lists and the
// odd table. Raw HTML is not rendered - react-markdown escapes it by default.
const COMPONENTS: Components = {
  p: ({ children }) => <p className="[&:not(:first-child)]:mt-2.5">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  ul: ({ children }) => <ul className="mt-2 list-disc space-y-1 pl-5 first:mt-0">{children}</ul>,
  ol: ({ children }) => <ol className="mt-2 list-decimal space-y-1 pl-5 first:mt-0">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5 marker:text-ink-4">{children}</li>,
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-medium text-accent-strong underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
    >
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded-[3px] bg-sunk px-1 py-px font-mono text-[0.88em] text-ink">{children}</code>
  ),
  h1: ({ children }) => <p className="mt-3 font-semibold text-ink first:mt-0">{children}</p>,
  h2: ({ children }) => <p className="mt-3 font-semibold text-ink first:mt-0">{children}</p>,
  h3: ({ children }) => <p className="mt-3 font-semibold text-ink first:mt-0">{children}</p>,
  table: ({ children }) => (
    <div className="mt-2.5 overflow-x-auto first:mt-0">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-b border-rule-strong px-2 py-1 text-left font-semibold text-ink-2">{children}</th>
  ),
  td: ({ children }) => <td className="border-b border-rule px-2 py-1 align-top">{children}</td>,
  hr: () => <hr className="my-3 border-rule" />,
};

export function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
      {text}
    </ReactMarkdown>
  );
}

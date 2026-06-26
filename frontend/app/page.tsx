'use client';

import { Fragment, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

const EXAMPLES = [
  'Find high-value customers likely to convert for a personal loan this month and draft personalized WhatsApp messages.',
  'Show me a top personal-loan prospect and explain why they rank so high.',
  'What is the best product to cross-sell to my highest-balance customer?',
  'List my top 10 customers by average balance.',
];

type ToolStep = {
  name: string;
  args: Record<string, unknown>;
  result: string | null;
};

type Message = {
  role: 'user' | 'assistant';
  content: string;
  trace?: ToolStep[];
  elapsedMs?: number;
};

function fmtVal(v: unknown): string {
  if (typeof v === 'string') return v.length > 24 ? `"${v.slice(0, 23)}…"` : `"${v}"`;
  if (Array.isArray(v)) return `[${v.length}]`;
  if (v && typeof v === 'object') return '{…}';
  return String(v);
}

function formatArgs(args: Record<string, unknown>): string {
  const s = Object.entries(args ?? {})
    .map(([k, v]) => `${k}: ${fmtVal(v)}`)
    .join(', ');
  return s.length > 100 ? `${s.slice(0, 99)}…` : s;
}

// Collapse consecutive calls to the same tool (e.g. generate_message per customer)
// into one group, so the path stays readable while keeping each call's detail.
function groupSteps(steps: ToolStep[]): { name: string; items: ToolStep[] }[] {
  const groups: { name: string; items: ToolStep[] }[] = [];
  for (const s of steps) {
    const last = groups[groups.length - 1];
    if (last && last.name === s.name) last.items.push(s);
    else groups.push({ name: s.name, items: [s] });
  }
  return groups;
}

// Post-response "agent path": the ordered tools the agent chose, each with its
// arguments and a short result summary. Collapsed by default to a one-line path;
// click the header to expand the per-step args + result detail. Repeated calls to
// the same tool are grouped (×N) with one sub-row per call.
function Trace({ steps, elapsedMs }: { steps: ToolStep[]; elapsedMs?: number }) {
  const [open, setOpen] = useState(false);
  const groups = groupSteps(steps);
  const meta =
    `${steps.length} tool call${steps.length > 1 ? 's' : ''}` +
    (elapsedMs ? ` · ${(elapsedMs / 1000).toFixed(1)}s` : '');
  return (
    <div className={`trace${open ? ' trace--open' : ''}`}>
      <button
        className="trace__head"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        title="Execution trace: the tools the agent called to answer, with their inputs and results"
      >
        <span className="trace__caret">{open ? '▾' : '▸'}</span>
        <span className="trace__label">agent path</span>
        <span className="trace__meta">{meta}</span>
      </button>
      <p className="trace__caption">
        Execution trace — surfaced for transparency: every tool the agent called to answer, with its inputs
        and result.
      </p>
      {!open && (
        <div className="trace__summary">
          {groups.map((g, j) => (
            <Fragment key={j}>
              {j > 0 && <span className="trace__arrow">→</span>}
              <span className="trace__tool">
                {g.name}
                {g.items.length > 1 && <span className="trace__count"> ×{g.items.length}</span>}
              </span>
            </Fragment>
          ))}
        </div>
      )}
      {open && (
        <ol className="trace__steps">
          {groups.map((g, j) => (
            <li key={j} className="trace__step">
              <span className="trace__num">{j + 1}</span>
              <div className="trace__bodycol">
                <div className="trace__line">
                  <span className="trace__tool">{g.name}</span>
                  {g.items.length > 1 ? (
                    <span className="trace__count">×{g.items.length}</span>
                  ) : (
                    formatArgs(g.items[0].args) && (
                      <code className="trace__args">{formatArgs(g.items[0].args)}</code>
                    )
                  )}
                </div>
                {g.items.length > 1 ? (
                  <ul className="trace__sub">
                    {g.items.map((it, k) => (
                      <li key={k} className="trace__subitem">
                        <span className="trace__subarrow">↳</span>
                        {formatArgs(it.args) && <code className="trace__args">{formatArgs(it.args)}</code>}
                        {it.result && <span className="trace__result">→ {it.result}</span>}
                      </li>
                    ))}
                  </ul>
                ) : (
                  g.items[0].result && <div className="trace__result">→ {g.items[0].result}</div>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default function Page() {
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  // One session id per browser tab, persisted so a reload keeps the thread
  // (multi-turn memory). A new tab starts a fresh conversation.
  useEffect(() => {
    let sid = sessionStorage.getItem('rm_session_id');
    if (!sid) {
      sid = crypto.randomUUID();
      sessionStorage.setItem('rm_session_id', sid);
    }
    setSessionId(sid);
  }, []);

  useEffect(() => {
    threadRef.current?.scrollTo(0, threadRef.current.scrollHeight);
  }, [messages, loading]);

  async function send(text?: string) {
    const content = (text ?? input).trim();
    if (!content || loading || !sessionId) return;

    setMessages((m) => [...m, { role: 'user', content }]);
    setInput('');
    setLoading(true);
    const started = Date.now();
    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: content }),
      });
      if (!res.ok) throw new Error(`request failed (HTTP ${res.status})`);
      const data = await res.json();
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: data.reply ?? '(no reply)',
          trace: (data.tool_calls ?? []) as ToolStep[],
          elapsedMs: Date.now() - started,
        },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: `Couldn't reach the assistant — ${String(e)}.` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="desk">
      <header className="desk__header">
        <div className="brand">
          <div className="brand__mark" aria-hidden />
          <div className="brand__name">
            Relationship Desk
            <small>Banking CRM assistant</small>
          </div>
        </div>
        <div className="status">
          <span className="status__dot" />
          Connected
        </div>
      </header>

      <div className="thread" ref={threadRef}>
        {messages.length === 0 && !loading && (
          <div className="empty">
            <h2>Ask about your book of clients.</h2>
            <p>
              Find high-potential customers, see exactly why they rank, recommend products, and draft outreach
              — in plain language.
            </p>
            <div className="empty__label">Try</div>
            <div className="chips">
              {EXAMPLES.map((ex) => (
                <button key={ex} className="chip" onClick={() => send(ex)}>
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="msg msg--user">
              {m.content}
            </div>
          ) : (
            <div key={i} className="msg msg--assistant">
              <div className="md">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
              </div>
              {m.trace && m.trace.length > 0 && <Trace steps={m.trace} elapsedMs={m.elapsedMs} />}
            </div>
          ),
        )}

        {loading && (
          <div className="thinking">
            <span className="thinking__dots">
              <i />
              <i />
              <i />
            </span>
            Reviewing clients and scoring…
          </div>
        )}
      </div>

      <div className="composer">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder="Ask about a client, a segment, or a product…"
          disabled={loading}
          aria-label="Ask the assistant"
        />
        <button onClick={() => send()} disabled={loading || !input.trim()}>
          Ask
        </button>
      </div>
    </div>
  );
}

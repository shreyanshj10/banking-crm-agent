'use client';

import { Fragment, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

const EXAMPLES = [
  'Find high-value customers likely to convert for a personal loan this month and draft personalized WhatsApp messages.',
  'Why did customer C00040 rank high for a personal loan?',
  'What is the best product to cross-sell to customer C00014?',
  'List my top 10 customers by average balance.',
];

type Message = {
  role: 'user' | 'assistant';
  content: string;
  tools?: string[];
};

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
          tools: (data.tool_calls ?? []).map((t: { name: string }) => t.name),
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
              {m.tools && m.tools.length > 0 && (
                <div className="trace">
                  <span className="trace__label">agent path</span>
                  {m.tools.map((t, j) => (
                    <Fragment key={j}>
                      {j > 0 && <span className="trace__arrow">→</span>}
                      <span className="trace__tool">{t}</span>
                    </Fragment>
                  ))}
                </div>
              )}
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

import React, { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from './App.jsx';

function formatTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export default function Chat({ messages, error, onRefresh }) {
  const [draft, setDraft] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamBody, setStreamBody] = useState('');
  const bottomRef = useRef(null);

  const ordered = [...(messages || [])].sort(
    (a, b) => new Date(a.timestamp || 0) - new Date(b.timestamp || 0)
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [ordered.length, streamBody]);

  async function handleSubmit(e) {
    e.preventDefault();
    const msg = draft.trim();
    if (!msg || streaming) return;

    setDraft('');
    setStreaming(true);
    setStreamBody('');

    try {
      const res = await fetch(`${API_BASE_URL}/dss/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = JSON.parse(line.slice(6));
          if (data.text) setStreamBody(b => b + data.text);
          if (data.done) onRefresh();
        }
      }
    } catch {
      setStreamBody('Could not reach the DSS LLM.');
    } finally {
      setStreaming(false);
      setStreamBody('');
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  return (
    <aside className="chat-pane">
      <div className="chat-header">
        <span>DSS Chat</span>
        {error && <small>{error}</small>}
      </div>

      <div className="chat-stream">
        {ordered.length === 0 && !streaming && (
          <div className="empty-chat">
            <p>Ask about vehicles, events, or mission state.</p>
          </div>
        )}

        {ordered.map((msg) => (
          <article
            key={msg.message_id}
            className={`chat-message ${msg.sender === 'operator' ? 'operator' : 'assistant'} sev-${msg.severity || 'none'}`}
          >
            <div className="message-meta">
              <span>{msg.sender === 'operator' ? 'You' : 'DSS'}</span>
              <time>{formatTime(msg.timestamp)}</time>
            </div>
            <p>{msg.body}</p>
          </article>
        ))}

        {streaming && (
          <article className="chat-message assistant sev-none">
            <div className="message-meta"><span>DSS</span></div>
            <p>{streamBody}<span className="cursor" /></p>
          </article>
        )}

        <div ref={bottomRef} />
      </div>

      <form className="chat-input" onSubmit={handleSubmit}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask the DSS… (Enter to send)"
          rows={3}
        />
        <button type="submit" disabled={streaming || !draft.trim()}>
          {streaming ? 'Thinking…' : 'Send'}
        </button>
      </form>
    </aside>
  );
}

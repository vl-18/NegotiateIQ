/**
 * NegotiationScreen — counterparty setup + live chat.
 *
 * Before session: single-column form (product → mode → persona → start).
 * During session: chat transcript with human input at bottom.
 */

import { useEffect, useRef, useState } from "react";
import { startSession, runTurn, openStream } from "../api.js";
import TurnMessage from "./TurnMessage.jsx";
import DealSummary from "./DealSummary.jsx";

const PERSONAS = [
  {
    value:   "budget_shopper",
    label:   "Budget Shopper",
    tagline: "Lowest price, always",
    desc:    "Pushes hard across up to 8 turns. Opens low, holds firm, walks away at the floor.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-6 h-6">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
        <path d="M12 6v6l4 2"/>
      </svg>
    ),
  },
  {
    value:   "premium_buyer",
    label:   "Premium Buyer",
    tagline: "Speed + perks over price",
    desc:    "Willing to pay more for express delivery and a loyalty voucher. Negotiates in 5 turns.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-6 h-6">
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
      </svg>
    ),
  },
  {
    value:   "bulk_purchaser",
    label:   "Bulk Purchaser",
    tagline: "Volume = leverage",
    desc:    "Negotiates 50+ units to unlock tier discounts. Switches quantity bracket as a power move.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-6 h-6">
        <path d="M20 7H4a2 2 0 00-2 2v10a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2z"/>
        <path d="M16 7V5a2 2 0 00-4 0v2M8 7V5a2 2 0 00-4 0v2"/>
      </svg>
    ),
  },
];


// ---------- Setup panel ----------

function SetupPanel({ product, onGoToProducts, onStart }) {
  // null = not chosen yet; "human" | "ai" once picked
  const [mode,    setMode]    = useState(null);
  const [persona, setPersona] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  const canStart = mode === "human" || (mode === "ai" && persona !== null);

  async function handleStart() {
    if (!canStart) return;
    setLoading(true);
    setError(null);
    try {
      await onStart({ mode, persona: mode === "ai" ? persona : undefined });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  if (!product) {
    return (
      <div className="flex items-center justify-center h-full min-h-96">
        <div className="text-center">
          <p className="text-sm text-[var(--text-2)] mb-3">No product selected.</p>
          <button onClick={onGoToProducts} className="text-xs text-[var(--accent)] hover:underline">
            ← Go to Products
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-8 py-10">
      <button
        onClick={onGoToProducts}
        className="text-xs text-[var(--text-2)] hover:text-[var(--text-1)] transition-colors mb-8 block"
      >
        ← Back to products
      </button>

      {/* Product summary row */}
      <div className="flex gap-4 mb-8 pb-8 border-b border-[var(--border)]">
        {product.imageUrl && (
          <img
            src={product.imageUrl}
            alt={product.name}
            /* old: className="w-20 h-20 object-cover rounded-lg flex-shrink-0 border border-[var(--border)]" */
            className="w-20 h-20 object-contain bg-white p-1 rounded-lg flex-shrink-0 border border-[var(--border)]"
          />
        )}
        <div>
          <p className="text-[10px] font-semibold text-[var(--accent)] uppercase tracking-widest mb-1">
            Negotiating
          </p>
          <h1 className="text-base font-semibold text-[var(--text-1)] tracking-tight leading-snug">
            {product.name}
          </h1>
          <div className="flex items-baseline gap-2 mt-1.5">
            <span className="text-xl font-bold text-[var(--text-1)] tabular-nums">
              ${product.listPrice.toFixed(2)}
            </span>
            <span className="text-xs text-[var(--text-2)]">/ unit · Negotiable</span>
          </div>
          <p className="text-[10px] text-[var(--text-3)] mt-1">
            Merchant agent: Alex · MadeinMind Commerce
          </p>
        </div>
      </div>

      {/* Step 1 — mode picker */}
      <div className="mb-6">
        <p className="text-xs font-semibold text-[var(--text-2)] uppercase tracking-widest mb-3">
          How would you like to negotiate?
        </p>
        <div className="grid grid-cols-2 gap-3">
          {/* Human */}
          <button
            onClick={() => { setMode("human"); setPersona(null); }}
            className={`flex flex-col items-start gap-2 p-4 rounded-lg border-2 text-left
              transition-colors
              ${mode === "human"
                ? "border-[var(--accent)] bg-[var(--accent-tint)]"
                : "border-[var(--border)] hover:border-[var(--accent)]"
              }`}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
              className={`w-6 h-6 ${mode === "human" ? "text-[var(--accent)]" : "text-[var(--text-2)]"}`}>
              <circle cx="12" cy="8" r="4"/>
              <path d="M4 20c0-4 3.58-7 8-7s8 3 8 7"/>
            </svg>
            <div>
              <p className={`text-sm font-semibold ${mode === "human" ? "text-[var(--accent)]" : "text-[var(--text-1)]"}`}>
                Negotiate yourself
              </p>
              <p className="text-[11px] text-[var(--text-2)] mt-0.5 leading-snug">
                Type each offer manually
              </p>
            </div>
          </button>

          {/* AI Agent */}
          <button
            onClick={() => setMode("ai")}
            className={`flex flex-col items-start gap-2 p-4 rounded-lg border-2 text-left
              transition-colors
              ${mode === "ai"
                ? "border-[var(--accent)] bg-[var(--accent-tint)]"
                : "border-[var(--border)] hover:border-[var(--accent)]"
              }`}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
              className={`w-6 h-6 ${mode === "ai" ? "text-[var(--accent)]" : "text-[var(--text-2)]"}`}>
              <rect x="3" y="11" width="18" height="10" rx="2"/>
              <path d="M12 3v4M8 7h8M7 11V9a5 5 0 0110 0v2"/>
              <circle cx="9" cy="16" r="1" fill="currentColor"/>
              <circle cx="15" cy="16" r="1" fill="currentColor"/>
            </svg>
            <div>
              <p className={`text-sm font-semibold ${mode === "ai" ? "text-[var(--accent)]" : "text-[var(--text-1)]"}`}>
                Use AI agent
              </p>
              <p className="text-[11px] text-[var(--text-2)] mt-0.5 leading-snug">
                Pick a persona, watch it negotiate
              </p>
            </div>
          </button>
        </div>
      </div>

      {/* Step 2 — persona picker (only when AI selected) */}
      {mode === "ai" && (
        <div className="mb-6">
          <p className="text-xs font-semibold text-[var(--text-2)] uppercase tracking-widest mb-3">
            Choose a negotiation style
          </p>
          <div className="grid grid-cols-1 gap-2">
            {PERSONAS.map((p) => (
              <button
                key={p.value}
                onClick={() => setPersona(p.value)}
                className={`flex items-start gap-4 p-4 rounded-lg border-2 text-left
                  transition-colors
                  ${persona === p.value
                    ? "border-[var(--accent)] bg-[var(--accent-tint)]"
                    : "border-[var(--border)] hover:border-[var(--accent)]"
                  }`}
              >
                <span className={`mt-0.5 flex-shrink-0
                  ${persona === p.value ? "text-[var(--accent)]" : "text-[var(--text-2)]"}`}>
                  {p.icon}
                </span>
                <div>
                  <div className="flex items-center gap-2">
                    <p className={`text-sm font-semibold
                      ${persona === p.value ? "text-[var(--accent)]" : "text-[var(--text-1)]"}`}>
                      {p.label}
                    </p>
                    <span className="text-[10px] text-[var(--text-3)] italic">{p.tagline}</span>
                  </div>
                  <p className="text-[11px] text-[var(--text-2)] mt-0.5 leading-relaxed">
                    {p.desc}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {error && (
        <p className="mb-4 text-xs text-[var(--red)] bg-[var(--red-tint)]
          border border-[var(--red-border)] rounded px-4 py-2">
          {error}
        </p>
      )}

      <button
        onClick={handleStart}
        disabled={!canStart || loading}
        className="w-full py-3 rounded text-sm font-semibold transition-colors
          bg-[var(--accent)] hover:bg-[var(--accent-hover)]
          disabled:opacity-30 disabled:cursor-not-allowed text-white"
      >
        {loading ? "Starting…" : "Start negotiation →"}
      </button>
    </div>
  );
}


// ---------- Live chat panel ----------

function ChatPanel({ session, product, onReset, onSessionComplete }) {
  const [messages,   setMessages]   = useState([]);
  const [status,     setStatus]     = useState("active");
  const [finalDeal,  setFinalDeal]  = useState(null);
  const [humanInput, setHumanInput] = useState("");
  const [sending,    setSending]    = useState(false);
  const [error,      setError]      = useState(null);
  const bottomRef    = useRef(null);
  const completedRef = useRef(false);

  function handleStatusChange(newStatus, deal) {
    setStatus(newStatus);
    setFinalDeal(deal ?? null);
    if (newStatus !== "active" && !completedRef.current) {
      completedRef.current = true;
      onSessionComplete?.({
        sessionId: session.session_id,
        status:    newStatus,
        finalDeal: deal ?? null,
        product,
        mode:      session.mode,
        persona:   session.persona,
      });
    }
  }

  useEffect(() => {
    const es = openStream(
      session.session_id,
      (event) => {
        if (event.type === "turn")   setMessages((prev) => [...prev, event]);
        if (event.type === "status") handleStatusChange(event.status, event.final_deal);
      },
      () => { if (!completedRef.current) handleStatusChange("expired", null); },
    );
    if (session.mode === "ai") fireAiTurn();
    return () => es.close();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function fireAiTurn() {
    setSending(true);
    setError(null);
    try {
      const result = await runTurn(session.session_id);
      if (result.session_status !== "active") {
        handleStatusChange(result.session_status, result.final_deal);
      } else {
        fireAiTurn();
      }
    } catch (e) { setError(e.message); }
    finally     { setSending(false); }
  }

  async function handleHumanSend() {
    const text = humanInput.trim();
    if (!text || sending) return;
    setHumanInput("");
    setSending(true);
    setError(null);
    try {
      const result = await runTurn(session.session_id, text);
      if (result.session_status !== "active") {
        handleStatusChange(result.session_status, result.final_deal);
      }
    } catch (e) { setError(e.message); }
    finally     { setSending(false); }
  }

  const isOver = status !== "active";

  const statusTextCls = {
    active:   "text-[var(--green)]",
    accepted: "text-[var(--green)]",
    rejected: "text-[var(--red)]",
    expired:  "text-[var(--amber)]",
  };

  return (
    <div className="max-w-2xl mx-auto px-8 py-10">
      {/* Session header */}
      <div className="flex items-center justify-between mb-6 pb-5 border-b border-[var(--border)]">
        <div>
          <h1 className="text-base font-semibold text-[var(--text-1)] tracking-tight">
            {product?.name}
          </h1>
          <p className="text-xs text-[var(--text-2)] mt-0.5">
            {session.mode === "ai"
              ? session.persona?.replace(/_/g, " ")
              : "Manual"}
            {" · "}
            <span className="font-mono text-[var(--text-3)]">{session.session_id.slice(0, 8)}</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs font-medium capitalize ${statusTextCls[status]}`}>
            {status === "active" && (
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-[var(--green)]
                mr-1.5 align-middle animate-pulse" />
            )}
            {status}
          </span>
          {isOver && (
            <button
              onClick={onReset}
              className="text-xs text-[var(--text-2)] hover:text-[var(--text-1)] transition-colors"
            >
              New session
            </button>
          )}
        </div>
      </div>

      {/* Side labels */}
      <div className="flex items-center justify-between mb-4">
        <span className="text-[10px] uppercase tracking-widest font-semibold text-[var(--text-2)]">
          Shopping Agent
        </span>
        <span className="text-[10px] uppercase tracking-widest font-semibold text-[var(--green)]">
          Merchant · MadeinMind
        </span>
      </div>

      {/* Chat area */}
      <div className="min-h-72 max-h-[55vh] overflow-y-auto pr-1 mb-4">
        {messages.length === 0 && (
          <p className="text-[var(--text-3)] text-sm text-center mt-12">
            {session.mode === "ai" ? "Connecting agents…" : "Type your first offer below."}
          </p>
        )}
        {messages.map((msg, i) => <TurnMessage key={i} message={msg} />)}
        {sending && (
          <div className="flex justify-center py-3">
            <span className="flex items-center gap-1.5">
              {[0, 150, 300].map((delay) => (
                <span
                  key={delay}
                  className="w-1 h-1 rounded-full bg-[var(--text-3)] animate-bounce"
                  style={{ animationDelay: `${delay}ms` }}
                />
              ))}
            </span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && (
        <p className="mb-3 text-xs text-[var(--red)] bg-[var(--red-tint)]
          border border-[var(--red-border)] rounded px-3 py-2">
          {error}
        </p>
      )}

      {/* Human input */}
      {session.mode === "human" && !isOver && (
        <div className="flex gap-2 border-t border-[var(--border)] pt-4">
          <input
            type="text"
            value={humanInput}
            onChange={(e) => setHumanInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleHumanSend()}
            placeholder="Type your offer…"
            disabled={sending}
            className="flex-1 bg-[var(--surface)] border border-[var(--border)] rounded px-4 py-2.5
              text-sm text-[var(--text-1)] placeholder-[var(--text-3)]
              focus:outline-none focus:border-[var(--accent)]
              disabled:opacity-50 transition-colors"
          />
          <button
            onClick={handleHumanSend}
            disabled={sending || !humanInput.trim()}
            className="px-5 py-2.5 bg-[var(--accent)] hover:bg-[var(--accent-hover)]
              disabled:opacity-40 text-white rounded text-sm font-medium transition-colors"
          >
            Send
          </button>
        </div>
      )}

      {isOver && <DealSummary status={status} finalDeal={finalDeal} onReset={onReset} />}
    </div>
  );
}


// ---------- Top-level screen ----------

export default function NegotiationScreen({
  product, session, onSessionStarted, onReset, onGoToProducts, onSessionComplete,
}) {
  async function handleStart({ mode, persona }) {
    const data = await startSession({ product_sku: product.sku, mode, persona });
    onSessionStarted(data);
  }

  if (session) {
    return (
      <ChatPanel
        session={session}
        product={product}
        onReset={onReset}
        onSessionComplete={onSessionComplete}
      />
    );
  }

  return (
    <SetupPanel
      product={product}
      onGoToProducts={onGoToProducts}
      onStart={handleStart}
    />
  );
}

/**
 * NegotiationPanel — the live negotiation chat screen.
 *
 * AI mode:  auto-fires turns via runTurn(); SSE stream feeds new messages in real time.
 * Human mode: shows a text input; user types each message which is sent as the shopping turn.
 *
 * EventSource is opened once on mount and closed when the session ends (server sends "event: close").
 */

import { useEffect, useRef, useState } from "react";
import { openStream, runTurn } from "../api.js";
import TurnMessage from "./TurnMessage.jsx";
import DealSummary from "./DealSummary.jsx";

export default function NegotiationPanel({ session, product, onReset }) {
  const [messages,   setMessages]   = useState([]);
  const [status,     setStatus]     = useState("active");   // active | accepted | rejected | expired
  const [finalDeal,  setFinalDeal]  = useState(null);
  const [humanInput, setHumanInput] = useState("");
  const [sending,    setSending]    = useState(false);
  const [error,      setError]      = useState(null);
  const bottomRef = useRef(null);

  // Open SSE stream on mount; close on unmount or when session ends
  useEffect(() => {
    const es = openStream(
      session.session_id,
      (event) => {
        if (event.type === "turn") {
          setMessages((prev) => [...prev, event]);
        } else if (event.type === "status") {
          // Session ended — server will follow with "event: close"
          setStatus(event.status);
          setFinalDeal(event.final_deal ?? null);
        }
      },
      () => {
        // Stream closed cleanly
        setStatus((s) => (s === "active" ? "expired" : s));
      }
    );

    // Kick off first AI turn immediately after stream is open
    if (session.mode === "ai") {
      fireAiTurn();
    }

    return () => es.close();
  }, []); // run once on mount

  // Auto-scroll to the latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function fireAiTurn() {
    setSending(true);
    setError(null);
    try {
      // The HTTP response also carries the messages, but SSE already pushed them.
      // We call runTurn() just to trigger the server-side processing.
      const result = await runTurn(session.session_id);
      // If session ended and SSE didn't fire status yet, reflect it from HTTP response
      if (result.session_status !== "active") {
        setStatus(result.session_status);
        setFinalDeal(result.final_deal ?? null);
      }
      // After each AI turn, fire the next one unless the session is over
      if (result.session_status === "active") {
        fireAiTurn();
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
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
        setStatus(result.session_status);
        setFinalDeal(result.final_deal ?? null);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  }

  const isOver = status !== "active";

  return (
    <div className="max-w-2xl mx-auto mt-8 px-4 pb-8">
      {/* Header bar */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-white">{product.name}</h2>
          <p className="text-xs text-gray-500">
            {session.mode === "ai"
              ? `AI mode · ${session.persona?.replace("_", " ")}`
              : "Human mode"}
            {" · "}Session {session.session_id.slice(0, 8)}…
          </p>
        </div>
        <span
          className={`text-xs px-3 py-1 rounded-full font-medium
            ${status === "active"   ? "bg-green-900 text-green-300" :
              status === "accepted" ? "bg-green-700 text-green-100" :
              status === "rejected" ? "bg-red-800 text-red-200"     :
                                      "bg-yellow-800 text-yellow-200"}`}
        >
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </span>
      </div>

      {/* Chat transcript */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 min-h-64 max-h-[60vh] overflow-y-auto">
        {messages.length === 0 && (
          <p className="text-gray-600 text-sm text-center mt-8">
            {session.mode === "ai" ? "Negotiation starting…" : "Type your opening offer below."}
          </p>
        )}
        {messages.map((msg, i) => (
          <TurnMessage key={i} message={msg} />
        ))}
        {sending && (
          <div className="text-center text-gray-600 text-xs animate-pulse py-2">Thinking…</div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Error banner */}
      {error && (
        <p className="mt-2 text-red-400 text-xs bg-red-950 border border-red-800 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {/* Human input — only shown in human mode when session is still active */}
      {session.mode === "human" && !isOver && (
        <div className="mt-3 flex gap-2">
          <input
            type="text"
            value={humanInput}
            onChange={(e) => setHumanInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleHumanSend()}
            placeholder="Type your offer or question…"
            disabled={sending}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2 text-sm text-gray-100
              placeholder-gray-600 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
          />
          <button
            onClick={handleHumanSend}
            disabled={sending || !humanInput.trim()}
            className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:text-gray-500
              text-white rounded-xl text-sm font-medium transition-colors"
          >
            Send
          </button>
        </div>
      )}

      {/* Deal summary shown when session ends */}
      {isOver && (
        <DealSummary status={status} finalDeal={finalDeal} onReset={onReset} />
      )}
    </div>
  );
}

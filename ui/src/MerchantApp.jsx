/**
 * MerchantApp.jsx — Merchant Portal root.
 *
 * Standalone app served on a separate port from the buyer portal.
 * Has its own login gate, sidebar, and screens.
 */

import { useState, useEffect } from "react";
import { fetchSessions, fetchProducts, fetchSession, normalizeProduct } from "./api.js";
import MerchantLogin             from "./components/MerchantLogin.jsx";
import MerchantDashboard         from "./components/MerchantDashboard.jsx";
import MerchantProductsScreen    from "./components/MerchantProductsScreen.jsx";
import MerchantConfigScreen      from "./components/MerchantConfigScreen.jsx";
import MerchantMetricsScreen     from "./components/MerchantMetricsScreen.jsx";
import ThemeToggle               from "./components/ThemeToggle.jsx";


// ---------------------------------------------------------------------------
// Merchant sidebar — structural border, single accent, no background fill
// ---------------------------------------------------------------------------

const MERCHANT_NAV = [
  {
    id: "m-dashboard",
    label: "Dashboard",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-4 h-4 flex-shrink-0">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </svg>
    ),
  },
  {
    id: "m-products",
    label: "Products",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-4 h-4 flex-shrink-0">
        <path d="M20 7H4a2 2 0 00-2 2v10a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2z" />
        <path d="M16 7V5a2 2 0 00-4 0v2M8 7V5a2 2 0 00-4 0v2" />
      </svg>
    ),
  },
  {
    id: "m-history",
    label: "Negotiations",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-4 h-4 flex-shrink-0">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
      </svg>
    ),
  },
  {
    id: "m-config",
    label: "Config",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-4 h-4 flex-shrink-0">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
      </svg>
    ),
  },
  {
    id: "m-metrics",
    label: "Metrics",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-4 h-4 flex-shrink-0">
        <path d="M3 3v18h18" />
        <path d="M7 16l4-6 4 4 4-8" />
      </svg>
    ),
  },
];

function MerchantSidebar({ activeTab, onTabChange, onRefresh, onLogout }) {
  return (
    <aside className="w-44 flex-shrink-0 flex flex-col border-r border-[var(--border)]">
      {/* Brand */}
      <div className="px-5 pt-6 pb-5 border-b border-[var(--border)]">
        <p className="text-[10px] font-bold text-[var(--accent)] uppercase tracking-widest">NegotiateIQ</p>
        <p className="text-[10px] text-[var(--text-3)] mt-0.5">Merchant portal</p>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3">
        {MERCHANT_NAV.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`relative w-full flex items-center gap-2.5 px-5 py-2 text-left transition-colors
                ${isActive
                  ? "text-[var(--accent)]"
                  : "text-[var(--text-2)] hover:text-[var(--text-1)]"
                }`}
            >
              {isActive && (
                <span className="absolute left-0 top-1 bottom-1 w-0.5 rounded-r bg-[var(--accent)]" />
              )}
              {item.icon}
              <span className="text-xs font-medium">{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Footer actions */}
      <div className="px-5 py-4 border-t border-[var(--border)] space-y-2">
        <button
          onClick={onRefresh}
          className="block text-[10px] text-[var(--text-3)] hover:text-[var(--text-2)] transition-colors"
        >
          Refresh sessions
        </button>
        <button
          onClick={onLogout}
          className="block text-[10px] text-[var(--text-3)] hover:text-[var(--red)] transition-colors"
        >
          Log out
        </button>
      </div>
    </aside>
  );
}


// ---------------------------------------------------------------------------
// Negotiation history — clean table + full chat drill-down
// ---------------------------------------------------------------------------

const STATUS_COLORS = {
  accepted: "var(--green)",
  rejected: "var(--red)",
  expired:  "var(--amber)",
};

/** Format an ISO timestamp to "Oct 11 · 14:32" — returns "—" if absent/invalid. */
function fmtDateTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const date = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const time = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
    return `${date} · ${time}`;
  } catch {
    return "—";
  }
}

const INTENT_LABELS = {
  counter_offer: { label: "Counter",  color: "var(--intent-counter)"  },
  final_offer:   { label: "Final",    color: "var(--accent)"          },
  accept:        { label: "Accepted", color: "var(--green)"           },
  reject:        { label: "Rejected", color: "var(--red)"             },
  query:         { label: "Inquiry",  color: "var(--text-2)"          },
};

function ChatTranscript({ sessionId, onBack }) {
  const [detail,  setDetail]  = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  useEffect(() => {
    fetchSession(sessionId)
      .then(setDetail)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-8 py-10">
        <button
          onClick={onBack}
          className="text-xs text-[var(--text-2)] hover:text-[var(--text-1)] mb-6 block"
        >
          ← Back to history
        </button>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i}
              className="h-16 rounded bg-[var(--surface)] border border-[var(--border)] animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto px-8 py-10">
        <button
          onClick={onBack}
          className="text-xs text-[var(--text-2)] hover:text-[var(--text-1)] mb-6 block"
        >
          ← Back
        </button>
        <p className="text-[var(--red)] text-sm">{error}</p>
      </div>
    );
  }

  const statusColor = STATUS_COLORS[detail.status] ?? "var(--text-2)";

  return (
    <div className="max-w-2xl mx-auto px-8 py-10">
      <button
        onClick={onBack}
        className="text-xs text-[var(--text-2)] hover:text-[var(--text-1)] mb-8 block"
      >
        ← Back to history
      </button>

      {/* Session header */}
      <div className="flex items-start justify-between mb-8 pb-6 border-b border-[var(--border)]">
        <div>
          <h1 className="text-base font-semibold text-[var(--text-1)] tracking-tight">
            {detail.product_sku}
          </h1>
          <p className="text-[10px] font-mono text-[var(--text-3)] mt-0.5">{detail.session_id}</p>
          <p className="text-xs text-[var(--text-2)] mt-1 capitalize">
            {detail.mode === "human" ? "Human buyer" : (detail.persona?.replace(/_/g, " ") ?? "AI agent")}
            {" · "}{detail.turn_count} turn{detail.turn_count !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="text-right">
          <span className="text-xs font-semibold capitalize" style={{ color: statusColor }}>
            {detail.status}
          </span>
          {detail.final_deal && (
            <p className="text-xs text-[var(--text-2)] mt-1 tabular-nums">
              ${Number(detail.final_deal.unit_price).toFixed(2)} × {detail.final_deal.quantity} units
            </p>
          )}
        </div>
      </div>

      {/* Transcript */}
      {detail.turns.length === 0 ? (
        <p className="text-center text-[var(--text-3)] text-sm py-8">No turns recorded.</p>
      ) : (
        <div className="space-y-4">
          {detail.turns.map((turn) => {
            const isMerchant = turn.sender === "merchant-agent";
            const intent     = INTENT_LABELS[turn.intent] ?? { label: turn.intent, color: "var(--text-2)" };
            const terms      = turn.proposed_terms;

            return (
              <div key={turn.turn} className={`flex ${isMerchant ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[75%] ${isMerchant ? "ml-16" : "mr-16"}`}>
                  {/* Meta row */}
                  <div className={`flex items-center gap-2 mb-1 ${isMerchant ? "flex-row-reverse" : ""}`}>
                    <span className={`text-[10px] font-semibold uppercase tracking-wide
                      ${isMerchant ? "text-[var(--green)]" : "text-[var(--text-2)]"}`}>
                      {isMerchant ? "Merchant" : "Shopping Agent"}
                    </span>
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded font-medium"
                      style={{ color: intent.color, backgroundColor: intent.color + "18" }}
                    >
                      {intent.label}
                    </span>
                    <span className="text-[10px] text-[var(--text-3)] ml-auto tabular-nums">
                      #{turn.turn}
                    </span>
                  </div>

                  {/* Bubble */}
                  <div className={`rounded-lg px-4 py-3 border text-sm text-[var(--text-1)] leading-relaxed
                    ${isMerchant
                      ? "bg-[var(--green-tint)] border-[var(--green-border)]"
                      : "bg-[var(--surface)] border-[var(--border)]"
                    }`}
                  >
                    {turn.display_text || <span className="text-[var(--text-3)] italic">—</span>}
                  </div>

                  {/* Terms */}
                  {terms && (
                    <div className={`mt-1.5 flex flex-wrap gap-3 text-[10px] text-[var(--text-2)]
                      ${isMerchant ? "justify-end" : ""}`}>
                      {terms.unit_price != null && (
                        <span className="tabular-nums">${Number(terms.unit_price).toFixed(2)}/unit</span>
                      )}
                      {terms.quantity != null && <span>qty {terms.quantity}</span>}
                      {terms.delivery_days != null && <span>{terms.delivery_days}d delivery</span>}
                      {terms.voucher_requested && (
                        <span className="text-[var(--amber)]">+voucher</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function NegotiationHistory({ sessions }) {
  const [selectedId, setSelectedId] = useState(null);

  if (selectedId) {
    return <ChatTranscript sessionId={selectedId} onBack={() => setSelectedId(null)} />;
  }

  return (
    <div className="max-w-4xl mx-auto px-8 py-10">
      <div className="mb-8">
        <h1 className="text-base font-semibold text-[var(--text-1)] tracking-tight">
          Negotiations
        </h1>
        <p className="text-xs text-[var(--text-2)] mt-1">
          {sessions.length === 0
            ? "No sessions yet."
            : `${sessions.length} session${sessions.length !== 1 ? "s" : ""} · click a row to view the full chat`}
        </p>
      </div>

      {sessions.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-sm text-[var(--text-3)]">
            Sessions appear after the buyer portal completes a negotiation.
          </p>
        </div>
      ) : (
        <div className="border border-[var(--border)] rounded overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[var(--text-3)] border-b border-[var(--border)]">
                <th className="text-left px-5 py-2.5 font-medium">#</th>
                <th className="text-left px-4 py-2.5 font-medium">Session</th>
                <th className="text-left px-4 py-2.5 font-medium">Date / Time</th>
                <th className="text-left px-4 py-2.5 font-medium">Product</th>
                <th className="text-left px-4 py-2.5 font-medium">Mode</th>
                <th className="text-left px-4 py-2.5 font-medium">Turns</th>
                <th className="text-left px-4 py-2.5 font-medium">Outcome</th>
                <th className="text-right px-5 py-2.5 font-medium">Final price</th>
                <th className="text-right px-5 py-2.5 font-medium">Qty</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {[...sessions].reverse().map((s, i) => (
                <tr
                  key={s.sessionId}
                  onClick={() => setSelectedId(s.sessionId)}
                  className="hover:bg-[var(--surface)] cursor-pointer"
                >
                  <td className="px-5 py-3 text-[var(--text-3)]">{sessions.length - i}</td>
                  <td className="px-4 py-3 font-mono text-[var(--text-3)]">{s.sessionId?.slice(0, 8)}</td>
                  <td className="px-4 py-3 text-[var(--text-3)] tabular-nums whitespace-nowrap">
                    {fmtDateTime(s.createdAt)}
                  </td>
                  <td className="px-4 py-3 text-[var(--text-2)]">{s.product?.name ?? "—"}</td>
                  <td className="px-4 py-3 text-[var(--text-2)] capitalize">
                    {s.mode === "human" ? "Human" : (s.persona?.replace(/_/g, " ") ?? "—")}
                  </td>
                  <td className="px-4 py-3 text-[var(--text-2)] tabular-nums">{s.turnCount ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span
                      className="text-[10px] font-semibold capitalize"
                      style={{ color: STATUS_COLORS[s.status] ?? "var(--text-2)" }}
                    >
                      {s.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-right text-[var(--text-1)] tabular-nums">
                    {s.finalDeal?.unit_price != null
                      ? `$${Number(s.finalDeal.unit_price).toFixed(2)}`
                      : "—"}
                  </td>
                  <td className="px-5 py-3 text-right text-[var(--text-2)] tabular-nums">
                    {s.finalDeal?.quantity ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Root component
// ---------------------------------------------------------------------------

export default function MerchantApp() {
  const [loggedIn,    setLoggedIn]   = useState(false);
  const [activeTab,   setActiveTab]  = useState("m-dashboard");
  const [sessions,    setSessions]   = useState([]);
  const [products,    setProducts]   = useState([]);
  const [loading,     setLoading]    = useState(false);
  const [fetchError,  setFetchError] = useState(null);

  async function loadSessions() {
    setLoading(true);
    setFetchError(null);
    try {
      const data = await fetchSessions();
      setSessions(data.sessions ?? []);
    } catch (e) {
      setFetchError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadProducts() {
    try {
      const data = await fetchProducts();
      setProducts((data.products ?? []).map(normalizeProduct));
    } catch {
      // non-fatal
    }
  }

  useEffect(() => {
    if (loggedIn) {
      loadSessions();
      loadProducts();
    }
  }, [loggedIn]); // eslint-disable-line react-hooks/exhaustive-deps

  const normalizedSessions = sessions.map((s) => ({
    sessionId: s.session_id,
    status:    s.status,
    finalDeal: s.final_deal,
    product:   { name: s.product?.name, listPrice: s.product?.list_price },
    mode:      s.mode,
    persona:   s.persona,
    turnCount: s.turn_count,
    createdAt: s.created_at ?? null,
  }));

  if (!loggedIn) {
    return (
      <div className="flex h-screen overflow-hidden bg-[var(--bg)] text-[var(--text-1)]">
        <ThemeToggle />
        <MerchantLogin onLogin={() => setLoggedIn(true)} />
      </div>
    );
  }

  const screens = {
    "m-dashboard": (
      <MerchantDashboard
        completedSessions={normalizedSessions}
        loading={loading}
        error={fetchError}
      />
    ),
    "m-products": <MerchantProductsScreen products={products} />,
    "m-history":  <NegotiationHistory sessions={normalizedSessions} />,
    "m-config":   <MerchantConfigScreen />,
    "m-metrics":  <MerchantMetricsScreen />,
  };

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg)] text-[var(--text-1)]">
      <ThemeToggle />
      <MerchantSidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onRefresh={loadSessions}
        onLogout={() => {
          setLoggedIn(false);
          setActiveTab("m-dashboard");
          setSessions([]);
        }}
      />
      <main className="flex-1 overflow-y-auto relative">
        {loading && (
          <div className="fixed top-4 right-16 text-[10px] text-[var(--text-2)]
            bg-[var(--surface)] border border-[var(--border)] px-3 py-1.5 rounded">
            Loading…
          </div>
        )}
        {screens[activeTab]}
      </main>
    </div>
  );
}

/**
 * MerchantDashboard — aggregate stats from completed sessions.
 */

/** Format an ISO timestamp to "Oct 11 · 14:32". */
function fmtDateTime(iso) {
  if (!iso) return "—";
  try {
    const d   = new Date(iso);
    const date = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const time = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
    return `${date} · ${time}`;
  } catch {
    return "—";
  }
}

const STATUS_COLORS = {
  accepted: "var(--green)",
  rejected: "var(--red)",
  expired:  "var(--amber)",
};

const STATUS_LABELS = {
  accepted: "Accepted",
  rejected: "Rejected",
  expired:  "Expired",
};

function Metric({ label, value, sub, accent }) {
  return (
    <div className="px-5 py-5">
      <p className="text-[10px] uppercase tracking-widest text-[var(--text-3)] mb-2">{label}</p>
      <p className="text-2xl font-bold tabular-nums" style={{ color: accent ?? "var(--text-1)" }}>
        {value}
      </p>
      {sub && <p className="text-[10px] text-[var(--text-3)] mt-1">{sub}</p>}
    </div>
  );
}

export default function MerchantDashboard({ completedSessions, loading, error }) {
  const total    = completedSessions.length;
  const accepted = completedSessions.filter((s) => s.status === "accepted").length;
  const rejected = completedSessions.filter((s) => s.status === "rejected").length;
  const expired  = completedSessions.filter((s) => s.status === "expired").length;
  const winRate  = total > 0 ? Math.round((accepted / total) * 100) : 0;

  const closedDeals = completedSessions.filter(
    (s) => s.status === "accepted" && s.finalDeal?.unit_price && s.product?.listPrice
  );
  const avgDiscount =
    closedDeals.length > 0
      ? closedDeals.reduce((sum, s) => {
          return sum + ((s.product.listPrice - s.finalDeal.unit_price) / s.product.listPrice) * 100;
        }, 0) / closedDeals.length
      : null;

  return (
    <div className="max-w-4xl mx-auto px-8 py-10">
      <div className="mb-8">
        <h1 className="text-base font-semibold text-[var(--text-1)] tracking-tight">Dashboard</h1>
        <p className="text-xs text-[var(--text-2)] mt-1">MadeinMind Commerce · Session overview</p>
      </div>

      {error && (
        <div className="mb-6 px-4 py-3 rounded border border-[var(--red-border)]
          bg-[var(--red-tint)] text-xs text-[var(--red)]">
          Failed to load sessions: {error}
        </div>
      )}

      {total === 0 ? (
        <div className="py-16 text-center">
          <p className="text-sm text-[var(--text-3)]">No sessions yet.</p>
          <p className="text-xs text-[var(--text-3)] mt-1">
            Sessions appear here after the buyer portal completes a negotiation.
          </p>
        </div>
      ) : (
        <>
          {/* Metrics row */}
          <div className="grid grid-cols-4 border border-[var(--border)] rounded mb-8
            divide-x divide-[var(--border)]">
            <Metric label="Total" value={total} />
            <Metric label="Win rate" value={`${winRate}%`} sub="deals accepted" accent="var(--green)" />
            <Metric
              label="Avg discount"
              value={avgDiscount !== null ? `${avgDiscount.toFixed(1)}%` : "—"}
              sub="on closed deals"
              accent="var(--amber)"
            />
            <Metric
              label="No deal"
              value={rejected + expired}
              sub={`${expired} expired`}
              accent="var(--red)"
            />
          </div>

          {/* Outcome bars */}
          <div className="border border-[var(--border)] rounded p-5 mb-6">
            <p className="text-[10px] uppercase tracking-widest text-[var(--text-3)] mb-4">
              Outcome breakdown
            </p>
            <div className="space-y-3">
              {[
                { key: "accepted", count: accepted },
                { key: "rejected", count: rejected },
                { key: "expired",  count: expired  },
              ].map(({ key, count }) => (
                <div key={key} className="flex items-center gap-4">
                  <span
                    className="text-xs font-medium w-16 flex-shrink-0"
                    style={{ color: STATUS_COLORS[key] }}
                  >
                    {STATUS_LABELS[key]}
                  </span>
                  <div className="flex-1 h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: total > 0 ? `${(count / total) * 100}%` : "0%",
                        backgroundColor: STATUS_COLORS[key],
                      }}
                    />
                  </div>
                  <span className="text-xs text-[var(--text-2)] w-6 text-right tabular-nums flex-shrink-0">
                    {count}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Recent sessions — last 24 hours */}
          {(() => {
            const cutoff = Date.now() - 24 * 60 * 60 * 1000;
            const recent = [...completedSessions]
              .reverse()
              .filter((s) => {
                if (!s.createdAt) return true; // include if date unknown
                return new Date(s.createdAt).getTime() >= cutoff;
              });

            return (
              <div className="border border-[var(--border)] rounded overflow-hidden">
                <div className="px-5 py-3 border-b border-[var(--border)] flex items-center justify-between">
                  <p className="text-[10px] uppercase tracking-widest text-[var(--text-3)]">
                    Recent sessions
                  </p>
                  <p className="text-[10px] text-[var(--text-3)]">last 24 h</p>
                </div>

                {recent.length === 0 ? (
                  <div className="px-5 py-8 text-center">
                    <p className="text-sm text-[var(--text-3)]">No sessions in the last 24 hours.</p>
                  </div>
                ) : (
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-[var(--text-3)] border-b border-[var(--border)]">
                        <th className="text-left px-5 py-2.5 font-medium">Session</th>
                        <th className="text-left px-4 py-2.5 font-medium">Date / Time</th>
                        <th className="text-left px-4 py-2.5 font-medium">Product</th>
                        <th className="text-left px-4 py-2.5 font-medium">Persona</th>
                        <th className="text-left px-4 py-2.5 font-medium">Outcome</th>
                        <th className="text-right px-5 py-2.5 font-medium">Final price</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border)]">
                      {recent.map((s) => (
                        <tr key={s.sessionId} className="hover:bg-[var(--surface)]">
                          <td className="px-5 py-3 font-mono text-[var(--text-3)]">
                            {s.sessionId?.slice(0, 8)}
                          </td>
                          <td className="px-4 py-3 text-[var(--text-3)] tabular-nums whitespace-nowrap">
                            {fmtDateTime(s.createdAt)}
                          </td>
                          <td className="px-4 py-3 text-[var(--text-2)]">{s.product?.name ?? "—"}</td>
                          <td className="px-4 py-3 text-[var(--text-2)] capitalize">
                            {s.mode === "human" ? "Human" : (s.persona?.replace(/_/g, " ") ?? "—")}
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className="text-[10px] font-semibold capitalize"
                              style={{ color: STATUS_COLORS[s.status] ?? "var(--text-2)" }}
                            >
                              {STATUS_LABELS[s.status] ?? s.status}
                            </span>
                          </td>
                          <td className="px-5 py-3 text-right text-[var(--text-1)] tabular-nums">
                            {s.finalDeal?.unit_price != null
                              ? `$${Number(s.finalDeal.unit_price).toFixed(2)}`
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            );
          })()}
        </>
      )}
    </div>
  );
}

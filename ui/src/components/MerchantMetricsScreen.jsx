/**
 * MerchantMetricsScreen.jsx — LLM performance metrics dashboard for the merchant portal.
 *
 * Shows live stats from GET /metrics: latency, token usage, per-agent breakdown,
 * and a sparkline of recent calls. Auto-refreshes every 10 seconds.
 */

import { useState, useEffect, useCallback } from "react";
import { fetchMetrics } from "../api.js";

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function fmtMs(ms) {
  if (ms == null || ms === 0) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

function fmtTokens(n) {
  if (n == null || n === 0) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function fmtTime(isoStr) {
  if (!isoStr) return "—";
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return isoStr;
  }
}


// ---------------------------------------------------------------------------
// KPI tile
// ---------------------------------------------------------------------------

function KpiTile({ label, value, sub, accent }) {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg px-5 py-4">
      <p className="text-[10px] text-[var(--text-3)] uppercase tracking-wide font-medium mb-1">{label}</p>
      <p
        className="text-2xl font-semibold tabular-nums"
        style={{ color: accent ?? "var(--text-1)" }}
      >
        {value}
      </p>
      {sub && <p className="text-[10px] text-[var(--text-3)] mt-1">{sub}</p>}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Agent summary card
// ---------------------------------------------------------------------------

function AgentCard({ title, data, accentColor, borderColor, bgColor }) {
  return (
    <div
      className="flex-1 rounded-lg border px-5 py-4"
      style={{ borderColor, backgroundColor: bgColor }}
    >
      <p className="text-xs font-semibold mb-4" style={{ color: accentColor }}>
        {title}
      </p>
      <div className="grid grid-cols-2 gap-x-6 gap-y-3">
        <div>
          <p className="text-[10px] text-[var(--text-3)] uppercase tracking-wide">Calls</p>
          <p className="text-lg font-semibold text-[var(--text-1)] tabular-nums mt-0.5">
            {data.calls ?? 0}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-[var(--text-3)] uppercase tracking-wide">Avg latency</p>
          <p className="text-lg font-semibold text-[var(--text-1)] tabular-nums mt-0.5">
            {fmtMs(data.avg_latency_ms)}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-[var(--text-3)] uppercase tracking-wide">Prompt tokens</p>
          <p className="text-sm font-medium text-[var(--text-1)] tabular-nums mt-0.5">
            {fmtTokens(data.prompt_tokens)}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-[var(--text-3)] uppercase tracking-wide">Output tokens</p>
          <p className="text-sm font-medium text-[var(--text-1)] tabular-nums mt-0.5">
            {fmtTokens(data.output_tokens)}
          </p>
        </div>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Latency sparkline (inline SVG, no library needed)
// ---------------------------------------------------------------------------

const CHART_H   = 72;
const BAR_W     = 14;
const BAR_GAP   = 3;
const MERCHANT_COLOR = "var(--green)";
const SHOPPING_COLOR = "var(--accent)";

function LatencyChart({ calls }) {
  const recent = calls.slice(-24);
  if (recent.length === 0) return null;

  const maxLatency = Math.max(...recent.map((c) => c.latency_ms ?? 0), 1);
  const totalW     = recent.length * (BAR_W + BAR_GAP) - BAR_GAP;

  return (
    <div>
      <div className="overflow-x-auto">
        <svg
          width={totalW}
          height={CHART_H}
          viewBox={`0 0 ${totalW} ${CHART_H}`}
          style={{ display: "block" }}
          aria-label="Latency bar chart"
        >
          {recent.map((call, i) => {
            const latency = call.latency_ms ?? 0;
            const h       = Math.max(2, (latency / maxLatency) * CHART_H);
            const x       = i * (BAR_W + BAR_GAP);
            const color   = call.agent === "merchant" ? MERCHANT_COLOR : SHOPPING_COLOR;
            return (
              <g key={i}>
                <title>{`${call.agent} · ${latency}ms`}</title>
                <rect
                  x={x}
                  y={CHART_H - h}
                  width={BAR_W}
                  height={h}
                  fill={color}
                  rx={2}
                  opacity={0.85}
                />
              </g>
            );
          })}
        </svg>
      </div>

      {/* X-axis labels: first, mid, last */}
      <div className="flex justify-between mt-1 text-[9px] text-[var(--text-3)]">
        <span>{fmtTime(recent[0]?.ts)}</span>
        <span>{fmtTime(recent[Math.floor(recent.length / 2)]?.ts)}</span>
        <span>{fmtTime(recent[recent.length - 1]?.ts)}</span>
      </div>

      {/* Legend */}
      <div className="flex gap-4 mt-3">
        {[
          { color: MERCHANT_COLOR, label: "Merchant agent" },
          { color: SHOPPING_COLOR, label: "Shopping agent" },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5">
            <span
              className="inline-block w-2.5 h-2.5 rounded-sm"
              style={{ backgroundColor: color }}
            />
            <span className="text-[10px] text-[var(--text-3)]">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Recent calls table
// ---------------------------------------------------------------------------

function RecentCallsTable({ calls }) {
  const recent = [...calls].reverse().slice(0, 30);

  if (recent.length === 0) {
    return (
      <p className="text-center text-[var(--text-3)] text-sm py-8">No calls yet.</p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="text-[var(--text-3)] border-b border-[var(--border)]">
            <th className="text-left px-3 py-2 font-medium">Time</th>
            <th className="text-left px-3 py-2 font-medium">Agent</th>
            <th className="text-left px-3 py-2 font-medium">Model</th>
            <th className="text-right px-3 py-2 font-medium">Latency</th>
            <th className="text-right px-3 py-2 font-medium">Prompt tkns</th>
            <th className="text-right px-3 py-2 font-medium">Output tkns</th>
            <th className="text-right px-3 py-2 font-medium">Total tkns</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border)]">
          {recent.map((call, i) => {
            const isMerchant  = call.agent === "merchant";
            const agentColor  = isMerchant ? "var(--green)" : "var(--accent)";
            const totalTokens = (call.prompt_tokens ?? 0) + (call.output_tokens ?? 0);
            const isSlowCall  = call.latency_ms > 5000;

            return (
              <tr key={i} className="hover:bg-[var(--surface)]">
                <td className="px-3 py-2 text-[var(--text-3)] tabular-nums font-mono">
                  {fmtTime(call.ts)}
                </td>
                <td className="px-3 py-2">
                  <span
                    className="text-[10px] font-semibold px-1.5 py-0.5 rounded"
                    style={{ color: agentColor, backgroundColor: agentColor + "18" }}
                  >
                    {isMerchant ? "Merchant" : "Shopping"}
                  </span>
                </td>
                <td className="px-3 py-2 text-[var(--text-2)] font-mono">{call.model ?? "—"}</td>
                <td
                  className="px-3 py-2 text-right tabular-nums font-medium"
                  style={{ color: isSlowCall ? "var(--red)" : "var(--text-1)" }}
                >
                  {fmtMs(call.latency_ms)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-[var(--text-2)]">
                  {call.prompt_tokens ?? "—"}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-[var(--text-2)]">
                  {call.output_tokens ?? "—"}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-[var(--text-1)] font-medium">
                  {totalTokens > 0 ? totalTokens : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Root screen
// ---------------------------------------------------------------------------

export default function MerchantMetricsScreen() {
  const [data,        setData]       = useState(null);
  const [loading,     setLoading]    = useState(true);
  const [error,       setError]      = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true);
    setError(null);
    try {
      const d = await fetchMetrics();
      setData(d);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + auto-refresh every 10 seconds
  useEffect(() => {
    load(true);
    const id = setInterval(() => load(false), 10_000);
    return () => clearInterval(id);
  }, [load]);

  const summary  = data?.summary  ?? {};
  const byAgent  = data?.by_agent ?? {};
  const calls    = data?.calls    ?? [];
  const merchant = byAgent.merchant ?? {};
  const shopping = byAgent.shopping ?? {};

  return (
    <div className="max-w-5xl mx-auto px-8 py-10">

      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-base font-semibold text-[var(--text-1)] tracking-tight">Metrics</h1>
          <p className="text-xs text-[var(--text-2)] mt-1">
            LLM latency &amp; token usage · auto-refreshes every 10 s
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-[10px] text-[var(--text-3)]">
              Updated {fmtTime(lastRefresh.toISOString())}
            </span>
          )}
          <button
            onClick={() => load(true)}
            disabled={loading}
            className="text-xs px-3 py-1.5 rounded border border-[var(--border)]
              text-[var(--text-2)] hover:text-[var(--text-1)] hover:border-[var(--text-2)]
              transition-colors disabled:opacity-40"
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 border border-[var(--border)] rounded-lg px-5 py-4 space-y-2">
          <p className="text-sm font-medium text-[var(--red)]">Could not reach /metrics endpoint</p>
          <p className="text-xs text-[var(--text-2)]">Error: {error}</p>
          <p className="text-xs text-[var(--text-3)]">
            Make sure the backend server is running on port 8001 and was restarted after the latest
            code changes. The <code className="font-mono">/metrics</code> route was added recently —
            restart with{" "}
            <code className="font-mono">venv\Scripts\uvicorn main:app --app-dir src --port 8001</code>
            {" "}from the <code className="font-mono">orchestrator/</code> directory.
          </p>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && summary.total_calls === 0 && (
        <div className="py-16 text-center border border-[var(--border)] rounded-lg space-y-2">
          <p className="text-sm text-[var(--text-2)]">No LLM calls recorded yet.</p>
          <p className="text-xs text-[var(--text-3)]">
            Run a negotiation in the buyer portal — metrics appear here after the first turn.
          </p>
          <p className="text-xs text-[var(--text-3)]">
            Metrics reset on server restart. If you just restarted, run a new negotiation.
          </p>
        </div>
      )}

      {/* Content — shown once we have at least one call */}
      {summary.total_calls > 0 && (
        <>
          {/* KPI tiles */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 mb-8">
            <KpiTile
              label="Total LLM calls"
              value={summary.total_calls}
              sub={`${summary.merchant_calls} merchant · ${summary.shopping_calls} shopping`}
            />
            <KpiTile
              label="Avg latency"
              value={fmtMs(summary.avg_latency_ms)}
              sub={`P50 ${fmtMs(summary.p50_latency_ms)}`}
            />
            <KpiTile
              label="P95 latency"
              value={fmtMs(summary.p95_latency_ms)}
              sub={`Max ${fmtMs(summary.max_latency_ms)}`}
              accent={summary.p95_latency_ms > 5000 ? "var(--red)" : undefined}
            />
            <KpiTile
              label="Total tokens"
              value={fmtTokens(summary.total_tokens)}
              sub={`${fmtTokens(summary.total_prompt_tokens)} prompt · ${fmtTokens(summary.total_output_tokens)} output`}
            />
          </div>

          {/* Per-agent breakdown */}
          <div className="flex gap-4 mb-8">
            <AgentCard
              title="Merchant Agent"
              data={merchant}
              accentColor="var(--green)"
              borderColor="var(--green-border)"
              bgColor="var(--green-tint)"
            />
            <AgentCard
              title="Shopping Agent"
              data={shopping}
              accentColor="var(--accent)"
              borderColor="var(--accent)"
              bgColor="var(--accent-tint)"
            />
          </div>

          {/* Latency sparkline */}
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg px-5 py-4 mb-6">
            <p className="text-xs font-medium text-[var(--text-2)] mb-4">
              Latency — last {Math.min(calls.length, 24)} calls (ms)
            </p>
            <LatencyChart calls={calls} />
          </div>

          {/* Recent calls table */}
          <div className="border border-[var(--border)] rounded-lg overflow-hidden">
            <div className="px-5 py-3 border-b border-[var(--border)]">
              <p className="text-xs font-medium text-[var(--text-2)]">
                Recent calls
                <span className="text-[var(--text-3)] font-normal ml-2">
                  (latest {Math.min(calls.length, 30)} of {summary.total_calls})
                </span>
              </p>
            </div>
            <RecentCallsTable calls={calls} />
          </div>
        </>
      )}
    </div>
  );
}

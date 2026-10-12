/**
 * SessionSetup — opening screen.
 * User picks a product, mode (AI or Human), and persona (AI only).
 * Calls startSession() then passes session data up to App.
 */

import { useState } from "react";
import { startSession } from "../api.js";

const PRODUCTS = [
  { sku: "SKU-001", name: "Sony WH-1000XM6",     desc: "Wireless noise-cancelling headphones" },
  { sku: "SKU-002", name: "Logitech MX Master 3S", desc: "Ergonomic wireless mouse"             },
  { sku: "SKU-003", name: "Samsung T7 SSD 1TB",   desc: "Portable USB-C SSD"                  },
  { sku: "SKU-004", name: 'LG 27" 4K Monitor',    desc: "IPS UHD display with USB-C hub"      },
];

const PERSONAS = [
  { value: "budget_shopper",  label: "Budget Shopper",  desc: "Pushes hard for the lowest unit price" },
  { value: "premium_buyer",   label: "Premium Buyer",   desc: "Prioritises fast delivery, less price-sensitive" },
  { value: "bulk_purchaser",  label: "Bulk Purchaser",  desc: "Wants 50+ units with a 15%+ discount" },
];

export default function SessionSetup({ onSessionStarted }) {
  const [sku,     setSku]     = useState(PRODUCTS[0].sku);
  const [mode,    setMode]    = useState("ai");
  const [persona, setPersona] = useState(PERSONAS[0].value);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  async function handleStart() {
    setLoading(true);
    setError(null);
    try {
      const session = await startSession({
        product_sku: sku,
        mode,
        persona: mode === "ai" ? persona : undefined,
      });
      onSessionStarted(session, PRODUCTS.find((p) => p.sku === sku));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-xl mx-auto mt-16 px-4">
      {/* Header */}
      <div className="text-center mb-10">
        <h1 className="text-3xl font-bold text-[var(--accent)] uppercase tracking-widest">NegotiateIQ</h1>
        <p className="text-gray-400 mt-2 text-sm">Agent-to-Agent Negotiation Demo — Google Cloud</p>
      </div>

      <div className="bg-gray-900 rounded-2xl p-6 space-y-6 border border-gray-800">
        {/* Product picker */}
        <div>
          <label className="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">
            Product
          </label>
          <div className="space-y-2">
            {PRODUCTS.map((p) => (
              <label
                key={p.sku}
                className={`flex items-start gap-3 p-3 rounded-xl cursor-pointer border transition-colors
                  ${sku === p.sku
                    ? "border-indigo-500 bg-indigo-950"
                    : "border-gray-700 hover:border-gray-600 bg-gray-800"
                  }`}
              >
                <input
                  type="radio" name="product" value={p.sku}
                  checked={sku === p.sku}
                  onChange={() => setSku(p.sku)}
                  className="mt-0.5 accent-indigo-400"
                />
                <div>
                  <div className="text-sm font-medium text-gray-100">{p.name}</div>
                  <div className="text-xs text-gray-500">{p.desc}</div>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Mode picker */}
        <div>
          <label className="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">
            Shopping Agent Mode
          </label>
          <div className="flex gap-3">
            {["ai", "human"].map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`flex-1 py-2 rounded-xl text-sm font-medium border transition-colors
                  ${mode === m
                    ? "border-indigo-500 bg-indigo-900 text-indigo-200"
                    : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600"
                  }`}
              >
                {m === "ai" ? "🤖 AI Persona" : "🧑 Human"}
              </button>
            ))}
          </div>
        </div>

        {/* Persona picker — only for AI mode */}
        {mode === "ai" && (
          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">
              AI Persona
            </label>
            <div className="space-y-2">
              {PERSONAS.map((p) => (
                <label
                  key={p.value}
                  className={`flex items-start gap-3 p-3 rounded-xl cursor-pointer border transition-colors
                    ${persona === p.value
                      ? "border-indigo-500 bg-indigo-950"
                      : "border-gray-700 hover:border-gray-600 bg-gray-800"
                    }`}
                >
                  <input
                    type="radio" name="persona" value={p.value}
                    checked={persona === p.value}
                    onChange={() => setPersona(p.value)}
                    className="mt-0.5 accent-indigo-400"
                  />
                  <div>
                    <div className="text-sm font-medium text-gray-100">{p.label}</div>
                    <div className="text-xs text-gray-500">{p.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>
        )}

        {error && (
          <p className="text-red-400 text-sm bg-red-950 border border-red-800 rounded-lg px-4 py-2">
            {error}
          </p>
        )}

        <button
          onClick={handleStart}
          disabled={loading}
          className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:text-gray-500
            text-white font-semibold rounded-xl transition-colors text-sm"
        >
          {loading ? "Starting…" : "Start Negotiation →"}
        </button>
      </div>
    </div>
  );
}

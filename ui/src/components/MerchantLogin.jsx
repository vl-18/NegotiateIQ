/**
 * MerchantLogin — simple password gate for the merchant dashboard.
 * Demo-only: hardcoded password.
 */

import { useState } from "react";

const DEMO_PASSWORD = "merchant123";

export default function MerchantLogin({ onLogin }) {
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState(false);

  function handleSubmit(e) {
    e.preventDefault();
    if (password === DEMO_PASSWORD) {
      onLogin();
    } else {
      setError(true);
      setPassword("");
    }
  }

  return (
    <div className="flex-1 flex items-center justify-center relative min-h-screen">
      <div className="w-72">
        {/* Brand */}
        <div className="mb-8 text-center">
          <p className="text-base font-bold text-[var(--accent)] uppercase tracking-widest mb-2">
            NegotiateIQ
          </p>
          <h1 className="text-xl font-semibold text-[var(--text-1)] tracking-tight">
            Merchant portal
          </h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-[var(--text-2)] mb-1.5">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setError(false); }}
              placeholder="Enter password"
              autoFocus
              className={`w-full bg-[var(--surface)] border rounded px-3 py-2.5 text-sm
                text-[var(--text-1)] placeholder-[var(--text-3)]
                focus:outline-none transition-colors
                ${error
                  ? "border-[var(--red)]"
                  : "border-[var(--border)] focus:border-[var(--accent)]"
                }`}
            />
            {error && (
              <p className="text-xs text-[var(--red)] mt-1.5">Incorrect password.</p>
            )}
          </div>

          <button
            type="submit"
            disabled={!password}
            className="w-full py-2.5 rounded text-sm font-medium transition-colors
              bg-[var(--accent)] hover:bg-[var(--accent-hover)]
              disabled:opacity-40 disabled:cursor-not-allowed text-white"
          >
            Sign in
          </button>
        </form>

        <p className="text-center text-[10px] text-[var(--text-3)] mt-8">
          Demo: <span className="font-mono">merchant123</span>
        </p>
      </div>

      {/* Footer — centred at screen bottom */}
      <p className="absolute bottom-6 left-0 right-0 text-center text-[10px] text-[var(--text-3)]">
        MadeinMind Commerce · Internal
      </p>
    </div>
  );
}

/**
 * MerchantProductsScreen — full product catalogue for the internal merchant view.
 * Shows all pricing fields (list price, price floor, bulk tiers) in a dense list.
 * Includes product images and a live search filter.
 */

import { useState } from "react";

export default function MerchantProductsScreen({ products }) {
  const [query, setQuery] = useState("");

  const filtered = query.trim()
    ? products.filter((p) =>
        p.name.toLowerCase().includes(query.toLowerCase()) ||
        p.sku.toLowerCase().includes(query.toLowerCase())
      )
    : products;

  return (
    <div className="max-w-4xl mx-auto px-8 py-10">
      <div className="mb-6">
        <h1 className="text-base font-semibold text-[var(--text-1)] tracking-tight">Products</h1>
        <p className="text-xs text-[var(--text-2)] mt-1">Internal view — all pricing rules visible.</p>
      </div>

      {/* Search */}
      <div className="relative mb-6">
        <svg
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
          className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-3)] pointer-events-none"
        >
          <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
        </svg>
        <input
          type="text"
          placeholder="Search by name or SKU…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full pl-9 pr-4 py-2 text-xs rounded border border-[var(--border)]
            bg-[var(--surface)] text-[var(--text-1)] placeholder-[var(--text-3)]
            focus:outline-none focus:border-[var(--accent)]"
        />
      </div>

      {products.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-sm text-[var(--text-3)]">No products. Add them via the Config screen.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center border border-[var(--border)] rounded">
          <p className="text-sm text-[var(--text-3)]">No products match "{query}".</p>
        </div>
      ) : (
        <div className="border border-[var(--border)] rounded divide-y divide-[var(--border)]">
          {filtered.map((p) => (
            <div key={p.sku} className="px-5 py-5 flex gap-5">
              {/* Product image */}
              {p.imageUrl && (
                <img
                  src={p.imageUrl}
                  alt={p.name}
                  className="w-24 h-16 object-cover rounded border border-[var(--border)] flex-shrink-0 self-start mt-1"
                  onError={(e) => { e.target.style.display = "none"; }}
                />
              )}

              <div className="flex-1 min-w-0">
                {/* Name + SKU row */}
                <div className="flex items-center gap-3 mb-4">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded
                    border border-[var(--border)] bg-[var(--surface)] text-[var(--text-3)] flex-shrink-0">
                    {p.sku}
                  </span>
                  <h2 className="text-sm font-semibold text-[var(--text-1)] truncate">{p.name}</h2>
                  {p.vouchersEligible && (
                    <span className="ml-auto text-[10px] px-2 py-0.5 rounded border
                      border-[var(--amber)] text-[var(--amber)] flex-shrink-0"
                      style={{ opacity: 0.8 }}>
                      Voucher eligible
                    </span>
                  )}
                </div>

                {/* Pricing */}
                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-[var(--text-3)] mb-1">
                      List price
                    </p>
                    <p className="text-lg font-semibold text-[var(--text-1)] tabular-nums">
                      ${p.listPrice.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-[var(--text-3)] mb-1">
                      Price floor
                    </p>
                    <p className="text-lg font-semibold text-[var(--green)] tabular-nums">
                      ${p.priceFloor.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-widest text-[var(--text-3)] mb-1">
                      Margin room
                    </p>
                    <p className="text-lg font-semibold text-[var(--text-2)] tabular-nums">
                      ${(p.listPrice - p.priceFloor).toFixed(2)}
                    </p>
                  </div>
                </div>

                {/* Tiers + delivery */}
                <div className="flex items-start gap-8">
                  {p.bulkTiers.length > 0 && (
                    <div>
                      <p className="text-[10px] uppercase tracking-widest text-[var(--text-3)] mb-1.5">
                        Volume tiers
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {p.bulkTiers.map((t) => (
                          <span key={t.minQty}
                            className="text-[10px] px-2 py-0.5 rounded border
                              border-[var(--border)] text-[var(--text-2)]">
                            {t.minQty}+ → {t.discountPct}% off
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {p.delivery.length > 0 && (
                    <div>
                      <p className="text-[10px] uppercase tracking-widest text-[var(--text-3)] mb-1.5">
                        Delivery
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {p.delivery.map((d) => (
                          <span key={d}
                            className="text-[10px] px-2 py-0.5 rounded border
                              border-[var(--border)] text-[var(--text-2)]">
                            {d}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

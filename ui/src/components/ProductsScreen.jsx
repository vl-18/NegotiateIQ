/**
 * ProductsScreen — Google Shopping-style buyer catalogue.
 * Grid layout with product images, search bar, filter chips, and per-card Negotiate button.
 */

import { useState, useMemo } from "react";

function formatDelivery(options = []) {
  return options.map((d) => {
    if (d.toLowerCase().includes("next"))     return "Next day";
    if (d.toLowerCase().includes("express"))  return "Express 2d";
    if (d.toLowerCase().includes("standard")) return "Standard 5d";
    return d;
  });
}

const FILTER_DEFS = [
  { key: "voucher",  label: "Voucher eligible" },
  { key: "express",  label: "Express delivery" },
  { key: "bulk",     label: "Bulk discount"    },
];

function FilterChip({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors whitespace-nowrap
        ${active
          ? "bg-[var(--accent)] border-[var(--accent)] text-white"
          : "border-[var(--border)] text-[var(--text-2)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
        }`}
    >
      {label}
    </button>
  );
}

function ProductCard({ product, onNegotiate }) {
  const [imgError, setImgError] = useState(false);
  const deliveryLabels = formatDelivery(product.delivery ?? []);
  const hasExpress     = (product.delivery ?? []).some((d) => d.includes("express"));
  const hasBulk        = product.bulkTiers?.length > 0;

  return (
    <div className="flex flex-col border border-[var(--border)] rounded-lg overflow-hidden
      bg-[var(--surface)] hover:border-[var(--accent)] transition-colors group">

      {/* Product image */}
      {/* old: <div className="w-full aspect-[4/3] bg-[var(--surface-hover)] overflow-hidden flex-shrink-0"> */}
      {/* new: white box, image centred with padding so the whole product shows */}
      <div className="w-full aspect-[4/3] bg-white flex items-center justify-center p-3 overflow-hidden flex-shrink-0">
        {product.imageUrl && !imgError ? (
          <img
            src={product.imageUrl}
            alt={product.name}
            onError={() => setImgError(true)}
            /* old: className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" */
            className="max-w-full max-h-full object-contain group-hover:scale-105 transition-transform duration-300"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <svg viewBox="0 0 48 48" fill="none" stroke="var(--border)" strokeWidth="1.5"
              className="w-12 h-12 opacity-40">
              <rect x="6" y="6" width="36" height="36" rx="4" />
              <circle cx="18" cy="18" r="4" />
              <path d="M6 32l10-10 8 8 6-6 12 12" />
            </svg>
          </div>
        )}
      </div>

      {/* Card body */}
      <div className="flex flex-col flex-1 p-4">
        {/* SKU badge */}
        <span className="text-[10px] font-mono text-[var(--text-3)] mb-1">{product.sku}</span>

        {/* Product name */}
        <p className="text-sm font-semibold text-[var(--text-1)] leading-snug mb-2 line-clamp-2">
          {product.name}
        </p>

        {/* Price row */}
        <div className="flex items-baseline gap-1.5 mb-3">
          <span className="text-xl font-bold text-[var(--text-1)] tabular-nums">
            ${product.listPrice.toFixed(2)}
          </span>
          <span className="text-[10px] text-[var(--accent)] font-medium">Negotiable</span>
        </div>

        {/* Feature badges */}
        <div className="flex flex-wrap gap-1.5 mb-4 min-h-[20px]">
          {hasExpress && (
            <span className="text-[10px] px-2 py-0.5 rounded-full border
              border-[var(--green-border)] text-[var(--green)] bg-[var(--green-tint)]">
              Express delivery
            </span>
          )}
          {product.vouchersEligible && (
            <span className="text-[10px] px-2 py-0.5 rounded-full border
              border-[var(--border)] text-[var(--amber)]">
              Voucher
            </span>
          )}
          {hasBulk && (
            <span className="text-[10px] px-2 py-0.5 rounded-full border
              border-[var(--border)] text-[var(--text-2)]">
              Bulk discounts
            </span>
          )}
          {!hasExpress && !product.vouchersEligible && !hasBulk && (
            <span className="text-[10px] text-[var(--text-3)]">
              {deliveryLabels[0] ?? "Standard delivery"}
            </span>
          )}
        </div>

        {/* Negotiate button — pushes to bottom */}
        <div className="mt-auto">
          <button
            onClick={() => onNegotiate(product)}
            className="w-full py-2 rounded text-xs font-semibold tracking-wide uppercase
              bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white
              transition-colors"
          >
            Negotiate
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ProductsScreen({ products, loading, onSelect }) {
  const [query,   setQuery]   = useState("");
  const [filters, setFilters] = useState(new Set());

  function toggleFilter(key) {
    setFilters((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  const visible = useMemo(() => {
    let list = products;

    // Text search — name or SKU
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      list = list.filter(
        (p) => p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q)
      );
    }

    // Active filters
    if (filters.has("voucher"))  list = list.filter((p) => p.vouchersEligible);
    if (filters.has("express"))  list = list.filter((p) =>
      (p.delivery ?? []).some((d) => d.includes("express"))
    );
    if (filters.has("bulk"))     list = list.filter((p) => p.bulkTiers?.length > 0);

    return list;
  }, [products, query, filters]);

  return (
    <div className="px-8 py-8 max-w-6xl mx-auto">

      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-base font-semibold text-[var(--text-1)] tracking-tight">
          Products
        </h1>
        <p
          className="text-sm text-[var(--text-2)] mt-1.5"
          style={{ fontFamily: "'Lora', Georgia, serif", fontStyle: "italic" }}
        >
          Every price is negotiable, pick a product and make your move...
        </p>
      </div>

      {/* Search + filters bar */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        {/* Search input */}
        <div className="relative flex-1 min-w-48 max-w-sm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
            className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-3)]">
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search products…"
            className="w-full pl-9 pr-4 py-2 rounded border border-[var(--border)]
              bg-[var(--surface)] text-sm text-[var(--text-1)]
              placeholder-[var(--text-3)] focus:outline-none
              focus:border-[var(--accent)] transition-colors"
          />
        </div>

        {/* Filter chips */}
        <div className="flex items-center gap-2 flex-wrap">
          {FILTER_DEFS.map(({ key, label }) => (
            <FilterChip
              key={key}
              label={label}
              active={filters.has(key)}
              onClick={() => toggleFilter(key)}
            />
          ))}
          {filters.size > 0 && (
            <button
              onClick={() => setFilters(new Set())}
              className="text-[10px] text-[var(--text-3)] hover:text-[var(--red)] transition-colors ml-1"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Loading skeletons */}
      {loading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="border border-[var(--border)] rounded-lg overflow-hidden">
              <div className="aspect-[4/3] bg-[var(--surface)] animate-pulse" />
              <div className="p-4 space-y-2">
                <div className="h-3 bg-[var(--surface)] rounded animate-pulse w-1/3" />
                <div className="h-4 bg-[var(--surface)] rounded animate-pulse" />
                <div className="h-4 bg-[var(--surface)] rounded animate-pulse w-2/3" />
                <div className="h-8 bg-[var(--surface)] rounded animate-pulse mt-4" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && visible.length === 0 && (
        <div className="py-24 text-center">
          <p className="text-sm text-[var(--text-3)]">
            {products.length === 0 ? "No products available." : "No products match your filters."}
          </p>
          {filters.size > 0 || query ? (
            <button
              onClick={() => { setFilters(new Set()); setQuery(""); }}
              className="mt-2 text-xs text-[var(--accent)] hover:underline"
            >
              Clear filters
            </button>
          ) : null}
        </div>
      )}

      {/* Results count */}
      {!loading && visible.length > 0 && (products.length !== visible.length) && (
        <p className="text-[10px] text-[var(--text-3)] mb-4">
          {visible.length} of {products.length} products
        </p>
      )}

      {/* Product grid */}
      {!loading && visible.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {visible.map((p) => (
            <ProductCard key={p.sku} product={p} onNegotiate={onSelect} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * api.js — thin wrappers around the NegotiateIQ FastAPI backend.
 *
 * VITE_API_URL defaults to /api which the Vite dev proxy rewrites to localhost:8000.
 * In production (Cloud Run URL injected at build time) set VITE_API_URL directly.
 */

const BASE = import.meta.env.VITE_API_URL ?? "/api";

/** POST /session/start — returns { session_id, mode, persona, status } */
export async function startSession({ product_sku, mode, persona }) {
  const res = await fetch(`${BASE}/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_sku, mode, persona }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

/** POST /session/{id}/turn — returns { shopping_turn, merchant_turn, session_status } */
export async function runTurn(sessionId, messageText = null) {
  const body = messageText ? { message_text: messageText } : {};
  const res = await fetch(`${BASE}/session/${sessionId}/turn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

/** GET /session/{id}/status — full session state including all turns. */
export async function fetchSession(sessionId) {
  const res = await fetch(`${BASE}/session/${sessionId}/status`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

/** GET /sessions — returns { sessions: [...] } for the merchant dashboard. */
export async function fetchSessions() {
  const res = await fetch(`${BASE}/sessions`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Normalize a raw API product (snake_case) → camelCase shape used by UI components.
 * delivery_options keys are kept as-is; ProductsScreen.jsx formats them for display.
 */
export function normalizeProduct(p) {
  return {
    sku:              p.sku,
    name:             p.name,
    desc:             p.description ?? "",
    listPrice:        p.list_price,
    priceFloor:       p.price_floor,
    bulkTiers:        (p.bulk_tiers ?? []).map((t) => ({
      minQty:      t.min_qty,
      discountPct: t.discount_pct,
    })),
    delivery:         p.delivery_options ?? [],
    vouchersEligible: p.vouchers_eligible ?? false,
    imageUrl:         p.image_url ?? null,
  };
}

/** GET /products — returns { products: [...] } for the merchant config screen. */
export async function fetchProducts() {
  const res = await fetch(`${BASE}/products`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * POST /products/upload — upload a CSV or Excel file for bulk create/update.
 * Returns { summary, created, updated, errors }.
 */
export async function uploadProductCatalogue(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/products/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

/** POST /products — create a new product. Returns { product } or throws on duplicate SKU. */
export async function createProduct(data) {
  const res = await fetch(`${BASE}/products`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

/** DELETE /products/{sku} — permanently remove a product. Returns nothing (204). */
export async function deleteProduct(sku) {
  const res = await fetch(`${BASE}/products/${sku}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
}

/** PUT /products/{sku} — patch a product's pricing/delivery. Returns { product }. */
export async function updateProduct(sku, data) {
  const res = await fetch(`${BASE}/products/${sku}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

/** GET /metrics — returns { summary, by_agent, calls } for the merchant metrics screen. */
export async function fetchMetrics() {
  const res = await fetch(`${BASE}/metrics`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * openStream(sessionId, onEvent, onClose) — opens an EventSource to the SSE endpoint.
 * onEvent(event: object) is called for each "data:" line.
 * onClose() is called when the server sends the "event: close" sentinel.
 * Returns the EventSource so the caller can close it on unmount.
 */
export function openStream(sessionId, onEvent, onClose) {
  const es = new EventSource(`${BASE}/session/${sessionId}/stream`);

  es.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data));
    } catch {
      // ignore malformed frames
    }
  };

  // Server sends "event: close" when the session ends
  es.addEventListener("close", () => {
    es.close();
    onClose();
  });

  es.onerror = () => {
    // Connection dropped — treat as stream end
    es.close();
    onClose();
  };

  return es;
}

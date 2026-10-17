/**
 * MerchantConfigScreen — editable merchant configuration.
 * Product catalogue with per-product price editor, bulk import, and delete.
 */

import { useState, useEffect, useRef } from "react";
import {
  fetchProducts, createProduct, updateProduct, deleteProduct, uploadProductCatalogue,
} from "../api.js";


// ---------------------------------------------------------------------------
// Delivery option labels
// ---------------------------------------------------------------------------

const DELIVERY_OPTIONS = [
  { key: "standard_5d", label: "Standard (5d)" },
  { key: "express_2d",  label: "Express (2d)"  },
  { key: "next_day",    label: "Next day (1d)"  },
];


// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

function Field({ label, hint, children }) {
  return (
    <div className="mb-3">
      <label className="text-[10px] text-[var(--text-2)] uppercase tracking-widest block mb-1">
        {label}
      </label>
      {children}
      {hint && <p className="text-[10px] text-[var(--text-3)] mt-0.5">{hint}</p>}
    </div>
  );
}

function NumberInput({ value, onChange, prefix, step = "0.01" }) {
  return (
    <div className="flex items-center gap-1.5">
      {prefix && <span className="text-[var(--text-2)] text-sm flex-shrink-0">{prefix}</span>}
      <input
        type="number"
        value={value}
        step={step}
        onChange={(e) => onChange(e.target.value)}
        className="bg-[var(--bg)] border border-[var(--border)] rounded px-3 py-1.5 text-sm
          text-[var(--text-1)] focus:outline-none focus:border-[var(--accent)] w-full transition-colors"
      />
    </div>
  );
}

function TextInput({ value, onChange, placeholder }) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full bg-[var(--bg)] border border-[var(--border)] rounded px-3 py-1.5 text-sm
        text-[var(--text-1)] placeholder-[var(--text-3)]
        focus:outline-none focus:border-[var(--accent)] transition-colors"
    />
  );
}

function SaveButton({ saving, saved, error, onClick, label = "Save changes" }) {
  return (
    <div className="flex items-center gap-3 mt-4">
      <button
        onClick={onClick}
        disabled={saving}
        className="px-4 py-1.5 rounded bg-[var(--accent)] hover:bg-[var(--accent-hover)]
          disabled:opacity-50 text-white text-xs font-medium transition-colors"
      >
        {saving ? "Saving…" : label}
      </button>
      {saved && <span className="text-xs text-[var(--green)]">Saved</span>}
      {error && <span className="text-xs text-[var(--red)]">{error}</span>}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Per-product accordion editor
// ---------------------------------------------------------------------------

function ProductEditor({ product: initial, selected, onToggleSelect }) {
  const [p,      setP]      = useState(initial);
  const [open,   setOpen]   = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved,  setSaved]  = useState(false);
  const [error,  setError]  = useState(null);

  function patchField(key) {
    return (val) => setP((prev) => ({ ...prev, [key]: val }));
  }

  function setTierField(idx, key, val) {
    setP((prev) => {
      const tiers = [...(prev.bulk_tiers ?? [])];
      tiers[idx] = { ...tiers[idx], [key]: Number(val) };
      return { ...prev, bulk_tiers: tiers };
    });
  }

  function addTier() {
    setP((prev) => ({
      ...prev,
      bulk_tiers: [...(prev.bulk_tiers ?? []), { min_qty: 10, discount_pct: 5 }],
    }));
  }

  function removeTier(idx) {
    setP((prev) => ({ ...prev, bulk_tiers: prev.bulk_tiers.filter((_, i) => i !== idx) }));
  }

  function toggleDelivery(key) {
    setP((prev) => {
      const cur = prev.delivery_options ?? [];
      return {
        ...prev,
        delivery_options: cur.includes(key)
          ? cur.filter((d) => d !== key)
          : [...cur, key],
      };
    });
  }

  async function save() {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const result = await updateProduct(p.sku, {
        list_price:        Number(p.list_price),
        price_floor:       Number(p.price_floor),
        bulk_tiers:        p.bulk_tiers,
        delivery_options:  p.delivery_options,
        vouchers_eligible: p.vouchers_eligible,
        image_url:         p.image_url || null,
      });
      setP(result.product);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  const listPrice   = Number(p.list_price)  || 0;
  const priceFloor  = Number(p.price_floor) || 0;
  const maxDiscount = listPrice > 0
    ? ((listPrice - priceFloor) / listPrice * 100).toFixed(1)
    : "0.0";

  return (
    <div className={`mb-2 overflow-hidden border rounded transition-colors
      ${selected
        ? "border-[var(--red-border)] bg-[var(--red-tint)]"
        : "border-[var(--border)]"}`}
    >
      {/* Header */}
      <div className="flex items-stretch">
        {/* Select checkbox */}
        <button
          onClick={(e) => { e.stopPropagation(); onToggleSelect(p.sku); }}
          className={`flex items-center justify-center px-4 border-r transition-colors
            ${selected
              ? "border-[var(--red-border)] hover:bg-[var(--red-tint)]"
              : "border-[var(--border)] hover:bg-[var(--surface)]"
            }`}
          title={selected ? "Deselect" : "Select for deletion"}
        >
          <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-colors
            ${selected
              ? "border-[var(--red)] bg-[var(--red)]"
              : "border-[var(--text-3)]"}`}
          >
            {selected && (
              <svg viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2" className="w-2.5 h-2.5">
                <path d="M2 6l3 3 5-5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </div>
        </button>

        {/* Accordion toggle */}
        <button
          className="flex-1 flex items-center justify-between px-5 py-4 text-left
            hover:bg-[var(--surface)] transition-colors"
          onClick={() => setOpen((v) => !v)}
        >
          <div className="flex items-center gap-3">
            <span className="text-[10px] font-mono px-2 py-0.5 rounded border
              border-[var(--border)] text-[var(--text-3)]">
              {p.sku}
            </span>
            <span className="text-sm font-medium text-[var(--text-1)]">{p.name}</span>
          </div>
          <div className="flex items-center gap-4 text-xs text-[var(--text-2)]">
            <span className="tabular-nums">
              ${listPrice.toFixed(2)} →{" "}
              <span className="text-[var(--green)]">${priceFloor.toFixed(2)}</span>
            </span>
            <span className="text-[var(--amber)] tabular-nums">max {maxDiscount}%</span>
            <span className={`transition-transform duration-200 text-[var(--text-3)]
              ${open ? "rotate-180" : ""}`}>
              ▾
            </span>
          </div>
        </button>
      </div>

      {/* Expandable body */}
      {open && (
        <div className="px-5 pb-5 border-t border-[var(--border)]">
          <div className="grid grid-cols-2 gap-4 mt-4">
            <Field label="List price" hint="Starting price shown to buyer">
              <NumberInput value={p.list_price} onChange={patchField("list_price")} prefix="$" />
            </Field>
            <Field label="Final price (floor)" hint="Agent never accepts below this">
              <NumberInput value={p.price_floor} onChange={patchField("price_floor")} prefix="$" />
            </Field>
          </div>

          <Field label="Product image URL" hint="Shown on the buyer product grid">
            <div className="flex gap-3 items-start">
              <TextInput
                value={p.image_url ?? ""}
                onChange={patchField("image_url")}
                placeholder="https://…"
              />
              {p.image_url && (
                <img
                  src={p.image_url}
                  alt="preview"
                  /* old: className="w-14 h-14 object-cover rounded border border-[var(--border)] flex-shrink-0" */
                  className="w-14 h-14 object-contain bg-white p-1 rounded border border-[var(--border)] flex-shrink-0"
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
              )}
            </div>
          </Field>

          <Field label="Bulk discount tiers">
            <div className="space-y-2 mb-2">
              {(p.bulk_tiers ?? []).map((t, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-xs text-[var(--text-3)] w-5 flex-shrink-0">{i + 1}.</span>
                  <div className="w-24">
                    <NumberInput
                      value={t.min_qty}
                      onChange={(v) => setTierField(i, "min_qty", v)}
                      step="1"
                    />
                  </div>
                  <span className="text-xs text-[var(--text-3)] whitespace-nowrap">+ units →</span>
                  <div className="w-20">
                    <NumberInput
                      value={t.discount_pct}
                      onChange={(v) => setTierField(i, "discount_pct", v)}
                      step="1"
                    />
                  </div>
                  <span className="text-xs text-[var(--text-3)]">% off</span>
                  <button
                    onClick={() => removeTier(i)}
                    className="text-[var(--red)] text-xs hover:opacity-70 ml-1 flex-shrink-0"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <button onClick={addTier} className="text-xs text-[var(--accent)] hover:opacity-70">
              + Add tier
            </button>
          </Field>

          <Field label="Delivery options">
            <div className="flex gap-4 flex-wrap">
              {DELIVERY_OPTIONS.map(({ key, label }) => {
                const checked = (p.delivery_options ?? []).includes(key);
                return (
                  <label key={key}
                    className="flex items-center gap-1.5 text-xs text-[var(--text-2)] cursor-pointer">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleDelivery(key)}
                      className="accent-[var(--accent)] cursor-pointer"
                    />
                    {label}
                  </label>
                );
              })}
            </div>
          </Field>

          <Field label="Loyalty voucher">
            <label className="flex items-center gap-2 text-sm text-[var(--text-2)] cursor-pointer">
              <input
                type="checkbox"
                checked={!!p.vouchers_eligible}
                onChange={(e) => setP((prev) => ({ ...prev, vouchers_eligible: e.target.checked }))}
                className="accent-[var(--accent)] cursor-pointer"
              />
              <span className="text-xs">Buyer receives LOYALTY10 voucher at FINAL_OFFER</span>
            </label>
          </Field>

          <SaveButton saving={saving} saved={saved} error={error} onClick={save} label="Save product" />
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// CSV / Excel column spec
// ---------------------------------------------------------------------------

const COLUMN_SPEC = [
  { col: "sku",                required: true,  example: "SKU-005",               desc: "Unique product ID (auto-uppercased)" },
  { col: "name",               required: true,  example: "Sony WH-1000XM6",       desc: "Product display name" },
  { col: "list_price",         required: true,  example: "99.99",                 desc: "Starting price shown to buyer" },
  { col: "price_floor",        required: true,  example: "79.99",                 desc: "Agent never accepts below this" },
  { col: "delivery_options",   required: false, example: "standard_5d,express_2d",desc: "Comma-separated. Default: standard_5d" },
  { col: "vouchers_eligible",  required: false, example: "true",                  desc: "true/false/yes/no/1/0. Default: false" },
  { col: "tier1_min_qty",      required: false, example: "10",                    desc: "Min qty for bulk tier 1" },
  { col: "tier1_discount_pct", required: false, example: "8",                     desc: "Discount % for bulk tier 1" },
  { col: "tier2_min_qty",      required: false, example: "50",                    desc: "Min qty for bulk tier 2" },
  { col: "tier2_discount_pct", required: false, example: "15",                    desc: "Discount % for bulk tier 2" },
  { col: "tier3_min_qty",      required: false, example: "100",                   desc: "Min qty for bulk tier 3" },
  { col: "tier3_discount_pct", required: false, example: "20",                    desc: "Discount % for bulk tier 3" },
  { col: "image_url",          required: false, example: "https://…/img.jpg",     desc: "Product image URL shown in buyer grid" },
];

const TEMPLATE_CSV = [
  COLUMN_SPEC.map((c) => c.col).join(","),
  `SKU-005,Example Product,99.99,79.99,"standard_5d,express_2d",true,10,8,50,15,,,https://picsum.photos/seed/product/400/280`,
].join("\n");


// ---------------------------------------------------------------------------
// Catalogue bulk import
// ---------------------------------------------------------------------------

function CatalogueUpload({ onUploaded }) {
  const [open,      setOpen]      = useState(false);
  const [dragging,  setDragging]  = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result,    setResult]    = useState(null);
  const [error,     setError]     = useState(null);
  const inputRef = useRef(null);

  async function handleFile(file) {
    if (!file) return;
    setUploading(true);
    setResult(null);
    setError(null);
    try {
      const data = await uploadProductCatalogue(file);
      setResult(data);
      onUploaded();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  function onDrop(e) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function downloadTemplate() {
    const blob = new Blob([TEMPLATE_CSV], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url;
    a.download = "product_catalogue_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="border border-[var(--border)] rounded mb-6 overflow-hidden">
      {/* Toggle header */}
      <button
        className="w-full flex items-center justify-between px-5 py-4 text-left
          hover:bg-[var(--surface)] transition-colors"
        onClick={() => { setOpen((v) => !v); setResult(null); setError(null); }}
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-[var(--text-1)]">Bulk import</span>
          <span className="text-[10px] px-2 py-0.5 rounded border border-[var(--green-border)]
            text-[var(--green)] bg-[var(--green-tint)]">
            CSV / Excel
          </span>
        </div>
        <span className={`text-[var(--text-3)] transition-transform duration-200 ${open ? "rotate-180" : ""}`}>
          ▾
        </span>
      </button>

      {open && (
        <div className="px-5 pb-6 border-t border-[var(--border)]">
          {/* Column spec */}
          <div className="mt-4 mb-5">
            <p className="text-xs text-[var(--text-2)] mb-3">
              Existing SKUs are updated; new SKUs are created. Each row is processed independently.
            </p>
            <div className="border border-[var(--border)] rounded overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-[var(--surface)] text-[var(--text-3)]">
                    <th className="text-left px-3 py-2 font-medium">Column</th>
                    <th className="text-left px-3 py-2 font-medium">Required</th>
                    <th className="text-left px-3 py-2 font-medium">Example</th>
                    <th className="text-left px-3 py-2 font-medium">Description</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {COLUMN_SPEC.map(({ col, required, example, desc }) => (
                    <tr key={col}>
                      <td className="px-3 py-2 font-mono text-[var(--text-2)]">{col}</td>
                      <td className="px-3 py-2">
                        {required
                          ? <span className="text-[var(--red)] font-semibold">Yes</span>
                          : <span className="text-[var(--text-3)]">No</span>
                        }
                      </td>
                      <td className="px-3 py-2 font-mono text-[var(--text-3)]">{example}</td>
                      <td className="px-3 py-2 text-[var(--text-2)]">{desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button
              onClick={downloadTemplate}
              className="mt-2 text-xs text-[var(--accent)] hover:opacity-70"
            >
              Download template CSV
            </button>
          </div>

          {/* Drop zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className={`border border-dashed rounded p-8 text-center cursor-pointer transition-colors
              ${dragging
                ? "border-[var(--accent)] bg-[var(--accent-tint)]"
                : "border-[var(--text-3)] hover:border-[var(--accent)] hover:bg-[var(--surface)]"
              }`}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              className="hidden"
              onChange={(e) => handleFile(e.target.files[0])}
            />
            {uploading ? (
              <p className="text-sm text-[var(--text-2)]">Uploading…</p>
            ) : (
              <>
                <p className="text-sm text-[var(--text-2)] mb-1">
                  Drag & drop, or{" "}
                  <span className="text-[var(--accent)]">click to browse</span>
                </p>
                <p className="text-xs text-[var(--text-3)]">.csv · .xlsx · .xls</p>
              </>
            )}
          </div>

          {error && (
            <div className="mt-3 border border-[var(--red-border)] bg-[var(--red-tint)] rounded
              px-4 py-3 text-xs text-[var(--red)]">
              {error}
            </div>
          )}

          {result && (
            <div className="mt-4 space-y-3">
              {/* Count chips */}
              <div className="flex gap-3">
                {[
                  { label: "Created",    value: result.summary.created,    color: "var(--green)" },
                  { label: "Updated",    value: result.summary.updated,    color: "var(--amber)" },
                  { label: "Errors",
                    value: result.summary.errors,
                    color: result.summary.errors > 0 ? "var(--red)" : "var(--text-3)" },
                  { label: "Total rows", value: result.summary.total_rows, color: "var(--text-2)" },
                ].map(({ label, value, color }) => (
                  <div key={label}
                    className="flex-1 border border-[var(--border)] rounded px-3 py-2 text-center">
                    <p className="text-lg font-bold tabular-nums" style={{ color }}>{value}</p>
                    <p className="text-[10px] text-[var(--text-3)]">{label}</p>
                  </div>
                ))}
              </div>

              {result.errors.length > 0 && (
                <div className="border border-[var(--red-border)] bg-[var(--red-tint)] rounded overflow-hidden">
                  <p className="text-[10px] text-[var(--red)] font-semibold px-3 py-2
                    border-b border-[var(--red-border)] uppercase tracking-widest">
                    Row errors
                  </p>
                  <table className="w-full text-xs">
                    <tbody>
                      {result.errors.map((e, i) => (
                        <tr key={i} className="border-b border-[var(--red-border)] last:border-0">
                          <td className="px-3 py-1.5 text-[var(--text-3)] w-16">Row {e.row}</td>
                          <td className="px-3 py-1.5 font-mono text-[var(--text-2)]">{e.sku}</td>
                          <td className="px-3 py-1.5 text-[var(--red)]">{e.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// New product inline form
// ---------------------------------------------------------------------------

const EMPTY_PRODUCT = {
  sku:               "",
  name:              "",
  list_price:        "",
  price_floor:       "",
  bulk_tiers:        [],
  delivery_options:  ["standard_5d"],
  vouchers_eligible: false,
  image_url:         "",
};

function NewProductForm({ onCreated }) {
  const [form,   setForm]   = useState(EMPTY_PRODUCT);
  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState(null);

  function patch(key) {
    return (val) => setForm((f) => ({ ...f, [key]: val }));
  }

  function setTierField(idx, key, val) {
    setForm((f) => {
      const tiers = [...f.bulk_tiers];
      tiers[idx] = { ...tiers[idx], [key]: Number(val) };
      return { ...f, bulk_tiers: tiers };
    });
  }

  function addTier() {
    setForm((f) => ({
      ...f,
      bulk_tiers: [...f.bulk_tiers, { min_qty: 10, discount_pct: 5 }],
    }));
  }

  function removeTier(idx) {
    setForm((f) => ({ ...f, bulk_tiers: f.bulk_tiers.filter((_, i) => i !== idx) }));
  }

  function toggleDelivery(key) {
    setForm((f) => {
      const cur = f.delivery_options;
      return {
        ...f,
        delivery_options: cur.includes(key)
          ? cur.filter((d) => d !== key)
          : [...cur, key],
      };
    });
  }

  async function submit(e) {
    e.preventDefault();
    setError(null);

    if (!form.sku.trim() || !form.name.trim()) {
      setError("SKU and name are required.");
      return;
    }
    const listPrice  = Number(form.list_price);
    const priceFloor = Number(form.price_floor);
    if (!listPrice || !priceFloor) {
      setError("List price and final price must be valid numbers.");
      return;
    }
    if (priceFloor > listPrice) {
      setError("Final price cannot exceed list price.");
      return;
    }

    setSaving(true);
    try {
      const result = await createProduct({
        ...form,
        sku:         form.sku.trim().toUpperCase(),
        name:        form.name.trim(),
        list_price:  listPrice,
        price_floor: priceFloor,
      });
      onCreated(result.product);
      setForm(EMPTY_PRODUCT);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="border border-dashed border-[var(--accent)] rounded p-5 mb-3 bg-[var(--accent-tint)]"
    >
      <p className="text-[10px] font-semibold text-[var(--accent)] uppercase tracking-widest mb-4">
        New product
      </p>

      <div className="grid grid-cols-2 gap-4 mb-3">
        <Field label="SKU (unique ID)">
          <TextInput value={form.sku} onChange={patch("sku")} placeholder="SKU-005" />
        </Field>
        <Field label="Product name">
          <TextInput value={form.name} onChange={patch("name")} placeholder="Sony WH-1000XM6" />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-3">
        <Field label="List price" hint="Starting price shown to buyer">
          <NumberInput value={form.list_price} onChange={patch("list_price")} prefix="$" />
        </Field>
        <Field label="Final price (floor)" hint="Agent never accepts below this">
          <NumberInput value={form.price_floor} onChange={patch("price_floor")} prefix="$" />
        </Field>
      </div>

      <Field label="Product image URL" hint="Shown on the buyer product grid (optional)">
        <div className="flex gap-3 items-start">
          <TextInput
            value={form.image_url}
            onChange={patch("image_url")}
            placeholder="https://…"
          />
          {form.image_url && (
            <img
              src={form.image_url}
              alt="preview"
              /* old: className="w-14 h-14 object-cover rounded border border-[var(--border)] flex-shrink-0" */
              className="w-14 h-14 object-contain bg-white p-1 rounded border border-[var(--border)] flex-shrink-0"
              onError={(e) => { e.currentTarget.style.display = "none"; }}
            />
          )}
        </div>
      </Field>

      <Field label="Bulk discount tiers">
        <div className="space-y-2 mb-2">
          {form.bulk_tiers.map((t, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-3)] w-5 flex-shrink-0">{i + 1}.</span>
              <div className="w-24">
                <NumberInput
                  value={t.min_qty}
                  onChange={(v) => setTierField(i, "min_qty", v)}
                  step="1"
                />
              </div>
              <span className="text-xs text-[var(--text-3)] whitespace-nowrap">+ units →</span>
              <div className="w-20">
                <NumberInput
                  value={t.discount_pct}
                  onChange={(v) => setTierField(i, "discount_pct", v)}
                  step="1"
                />
              </div>
              <span className="text-xs text-[var(--text-3)]">% off</span>
              <button
                type="button"
                onClick={() => removeTier(i)}
                className="text-[var(--red)] text-xs hover:opacity-70 ml-1 flex-shrink-0"
              >
                ×
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={addTier}
          className="text-xs text-[var(--accent)] hover:opacity-70"
        >
          + Add tier
        </button>
      </Field>

      <Field label="Delivery options">
        <div className="flex gap-4 flex-wrap">
          {DELIVERY_OPTIONS.map(({ key, label }) => (
            <label key={key}
              className="flex items-center gap-1.5 text-xs text-[var(--text-2)] cursor-pointer">
              <input
                type="checkbox"
                checked={form.delivery_options.includes(key)}
                onChange={() => toggleDelivery(key)}
                className="accent-[var(--accent)] cursor-pointer"
              />
              {label}
            </label>
          ))}
        </div>
      </Field>

      <Field label="Loyalty voucher">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={form.vouchers_eligible}
            onChange={(e) => patch("vouchers_eligible")(e.target.checked)}
            className="accent-[var(--accent)] cursor-pointer"
          />
          <span className="text-xs text-[var(--text-2)]">
            Eligible for LOYALTY10 voucher at FINAL_OFFER
          </span>
        </label>
      </Field>

      {error && <p className="text-xs text-[var(--red)] mb-3">{error}</p>}

      <button
        type="submit"
        disabled={saving}
        className="px-4 py-1.5 rounded bg-[var(--accent)] hover:bg-[var(--accent-hover)]
          disabled:opacity-50 text-white text-xs font-medium transition-colors"
      >
        {saving ? "Creating…" : "Create product"}
      </button>
    </form>
  );
}


// ---------------------------------------------------------------------------
// Root component
// ---------------------------------------------------------------------------

export default function MerchantConfigScreen() {
  const [products,        setProducts]        = useState([]);
  const [loading,         setLoading]         = useState(true);
  const [loadError,       setLoadError]       = useState(null);
  const [showCatalogue,   setShowCatalogue]   = useState(false);
  const [showNewForm,     setShowNewForm]     = useState(false);
  const [selectedSkus,    setSelectedSkus]    = useState(new Set());
  const [deleting,        setDeleting]        = useState(false);
  const [catalogueQuery,  setCatalogueQuery]  = useState("");

  function loadProducts() {
    return fetchProducts()
      .then((data) => setProducts(data.products ?? []))
      .catch((e) => setLoadError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => { loadProducts(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handleCreated(newProduct) {
    setProducts((prev) => [...prev, newProduct]);
    setShowNewForm(false);
  }

  function toggleSelect(sku) {
    setSelectedSkus((prev) => {
      const next = new Set(prev);
      next.has(sku) ? next.delete(sku) : next.add(sku);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelectedSkus((prev) =>
      prev.size === products.length ? new Set() : new Set(products.map((p) => p.sku))
    );
  }

  async function handleDeleteSelected() {
    const skus = [...selectedSkus];
    if (!window.confirm(
      `Permanently delete ${skus.length} product${skus.length > 1 ? "s" : ""}?\n\n${skus.join(", ")}`
    )) return;

    setDeleting(true);
    await Promise.all(skus.map((sku) => deleteProduct(sku).catch(() => null)));
    setSelectedSkus(new Set());
    await loadProducts();
    setDeleting(false);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-[var(--text-3)] text-sm">
        Loading…
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="max-w-3xl mx-auto px-8 py-10">
        <div className="border border-[var(--red-border)] bg-[var(--red-tint)] rounded p-5
          text-[var(--red)] text-sm">
          Failed to load config: {loadError}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-8 py-10">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-base font-semibold text-[var(--text-1)] tracking-tight">Configuration</h1>
        <p className="text-xs text-[var(--text-2)] mt-1">Changes take effect on the next negotiation turn.</p>
      </div>

      {/* Negotiation behaviour — informational */}
      <div className="border border-[var(--border)] rounded p-5 mb-6">
        <p className="text-[10px] uppercase tracking-widest text-[var(--text-3)] mb-3">
          Negotiation behaviour
        </p>
        <div className="divide-y divide-[var(--border)]">
          {[
            ["Final offer trigger",  "Within $0.50 of price floor (FINAL_OFFER_EPSILON)"],
            ["Safety backstop",      "50 turns max (bug guard, not user-visible)"],
            ["Infinite loop guard",  "Auto-reject if buyer counters after FINAL_OFFER"],
            ["AI model",             "Gemini 3.8 Flash — COUNTER_OFFER prose only"],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between py-2.5">
              <span className="text-xs text-[var(--text-2)]">{label}</span>
              <span className="text-xs text-[var(--text-3)] text-right max-w-xs">{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Bulk import */}
      <CatalogueUpload onUploaded={loadProducts} />

      {/* Product catalogue — collapsible */}
      <div className="border border-[var(--border)] rounded overflow-hidden">
        {/* Dropdown toggle header */}
        <button
          className="w-full flex items-center justify-between px-5 py-4 text-left
            hover:bg-[var(--surface)] transition-colors"
          onClick={() => setShowCatalogue((v) => !v)}
        >
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-[var(--text-1)]">Product catalogue</span>
            <span className="text-[10px] px-2 py-0.5 rounded border border-[var(--border)]
              text-[var(--text-3)]">
              {products.length} product{products.length !== 1 ? "s" : ""}
            </span>
          </div>
          <span className={`text-[var(--text-3)] transition-transform duration-200
            ${showCatalogue ? "rotate-180" : ""}`}>
            ▾
          </span>
        </button>

        {showCatalogue && (
          <div className="border-t border-[var(--border)] px-5 pb-5 pt-4">
            {/* Search */}
            <div className="relative mb-3">
              <svg
                viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
                className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-3)] pointer-events-none"
              >
                <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
              </svg>
              <input
                type="text"
                placeholder="Search by name or SKU…"
                value={catalogueQuery}
                onChange={(e) => setCatalogueQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-1.5 text-xs rounded border border-[var(--border)]
                  bg-[var(--bg)] text-[var(--text-1)] placeholder-[var(--text-3)]
                  focus:outline-none focus:border-[var(--accent)]"
              />
            </div>

            {/* Toolbar: select-all + actions */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <button onClick={toggleSelectAll} title="Select all / deselect all">
                  <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-colors
                    ${selectedSkus.size > 0
                      ? "border-[var(--red)] bg-[var(--red)]"
                      : "border-[var(--text-3)] hover:border-[var(--red)]"
                    }`}
                  >
                    {selectedSkus.size > 0 && (
                      selectedSkus.size === products.length
                        ? <svg viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2" className="w-2.5 h-2.5">
                            <path d="M2 6l3 3 5-5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        : <div className="w-2 h-0.5 bg-white rounded" />
                    )}
                  </div>
                </button>
                <p className="text-[10px] uppercase tracking-widest text-[var(--text-3)]">
                  Click a row to edit
                </p>
              </div>

              <div className="flex items-center gap-2">
                {selectedSkus.size > 0 && (
                  <button
                    onClick={handleDeleteSelected}
                    disabled={deleting}
                    className="text-xs font-medium px-3 py-1.5 rounded transition-colors
                      bg-[var(--red-tint)] text-[var(--red)] hover:bg-[var(--red-border)]
                      disabled:opacity-50"
                  >
                    {deleting ? "Deleting…" : `Delete (${selectedSkus.size})`}
                  </button>
                )}
                <button
                  onClick={() => setShowNewForm((v) => !v)}
                  className={`text-xs font-medium px-3 py-1.5 rounded transition-colors
                    ${showNewForm
                      ? "bg-[var(--surface)] text-[var(--text-2)] hover:text-[var(--text-1)]"
                      : "bg-[var(--accent-tint)] text-[var(--accent)] hover:bg-[var(--accent-tint)]"
                    }`}
                >
                  {showNewForm ? "Cancel" : "Add product"}
                </button>
              </div>
            </div>

            {showNewForm && <NewProductForm onCreated={handleCreated} />}

            {(() => {
              const q = catalogueQuery.trim().toLowerCase();
              const visible = q
                ? products.filter((p) =>
                    p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q)
                  )
                : products;

              if (visible.length === 0 && !showNewForm) {
                return (
                  <div className="py-12 text-center border border-[var(--border)] rounded">
                    <p className="text-sm text-[var(--text-3)]">
                      {q ? `No products match "${catalogueQuery}".` : "No products. Add one or import via CSV."}
                    </p>
                  </div>
                );
              }

              return visible.map((p) => (
                <ProductEditor
                  key={p.sku}
                  product={p}
                  selected={selectedSkus.has(p.sku)}
                  onToggleSelect={toggleSelect}
                />
              ));
            })()}
          </div>
        )}
      </div>
    </div>
  );
}

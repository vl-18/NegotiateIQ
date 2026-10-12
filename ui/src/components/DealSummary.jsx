/**
 * DealSummary — outcome panel shown when a session ends.
 * Typographic hierarchy, no emoji icons.
 */

const STATUS_CONFIG = {
  accepted: {
    label:   "Deal closed",
    sub:     "Both parties reached an agreement.",
    headCls: "text-[var(--green)]",
  },
  rejected: {
    label:   "No deal",
    sub:     "The negotiation ended without agreement.",
    headCls: "text-[var(--red)]",
  },
  expired: {
    label:   "Session expired",
    sub:     "Closed without an agreement.",
    headCls: "text-[var(--amber)]",
  },
};

export default function DealSummary({ status, finalDeal, onReset }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.expired;

  return (
    <div className="mt-6 border border-[var(--border)] rounded-md p-5">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className={`text-base font-semibold ${cfg.headCls}`}>{cfg.label}</h2>
          <p className="text-xs text-[var(--text-2)] mt-0.5">{cfg.sub}</p>
        </div>
        <button
          onClick={onReset}
          className="px-3 py-1.5 text-xs text-[var(--text-2)] hover:text-[var(--text-1)]
            border border-[var(--border)] rounded transition-colors flex-shrink-0"
        >
          New session
        </button>
      </div>

      {finalDeal && status === "accepted" && (
        <div className="grid grid-cols-2 gap-x-8 gap-y-2 pt-4 border-t border-[var(--border)]">
          {finalDeal.unit_price != null && (
            <>
              <span className="text-xs text-[var(--text-2)]">Unit price</span>
              <span className="text-xs font-semibold text-[var(--text-1)] tabular-nums text-right">
                ${finalDeal.unit_price.toFixed(2)}
              </span>
            </>
          )}
          {finalDeal.quantity != null && (
            <>
              <span className="text-xs text-[var(--text-2)]">Quantity</span>
              <span className="text-xs font-semibold text-[var(--text-1)] text-right">
                {finalDeal.quantity} units
              </span>
            </>
          )}
          {finalDeal.delivery_days != null && (
            <>
              <span className="text-xs text-[var(--text-2)]">Delivery</span>
              <span className="text-xs font-semibold text-[var(--text-1)] text-right">
                {finalDeal.delivery_days} days
              </span>
            </>
          )}
          {finalDeal.voucher_requested && (
            <>
              <span className="text-xs text-[var(--text-2)]">Voucher</span>
              <span className="text-xs font-semibold text-[var(--amber)] text-right">Included</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}

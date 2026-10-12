/**
 * TurnMessage — single negotiation message bubble.
 * Merchant: right-aligned. Shopping agent / human: left-aligned.
 */

const SENDER_LABELS = {
  "shopping-agent": "Shopping Agent",
  "merchant-agent": "Merchant",
  human:            "You",
};

const INTENT_BADGE = {
  counter_offer: { label: "Counter",     cls: "bg-[var(--intent-counter-bg)] text-[var(--intent-counter)]" },
  accept:        { label: "Accepted",    cls: "bg-[var(--green-tint)] text-[var(--green)]" },
  reject:        { label: "Rejected",    cls: "bg-[var(--red-tint)] text-[var(--red)]" },
  final_offer:   { label: "Final Offer", cls: "bg-[var(--intent-counter-bg)] text-[var(--accent)]" },
  query:         { label: "Inquiry",     cls: "bg-[var(--surface)] text-[var(--text-2)]" },
};

export default function TurnMessage({ message }) {
  const isMerchant = message.sender === "merchant-agent";
  const label      = SENDER_LABELS[message.sender] ?? message.sender;
  const badge      = INTENT_BADGE[message.intent];
  const terms      = message.proposed_terms;

  return (
    <div className={`flex ${isMerchant ? "justify-end" : "justify-start"} mb-4`}>
      <div className={`max-w-sm ${isMerchant ? "ml-16" : "mr-16"}`}>
        {/* Label row */}
        <div className={`flex items-center gap-2 mb-1 ${isMerchant ? "flex-row-reverse" : ""}`}>
          <span className={`text-[10px] font-semibold tracking-wide uppercase
            ${isMerchant ? "text-[var(--green)]" : "text-[var(--text-2)]"}`}>
            {label}
          </span>
          {badge && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${badge.cls}`}>
              {badge.label}
            </span>
          )}
          <span className="text-[10px] text-[var(--text-3)] ml-auto tabular-nums">
            {message.turn}
          </span>
        </div>

        {/* Bubble */}
        <div className={`rounded-lg px-4 py-3 text-sm leading-relaxed text-[var(--text-1)]
          ${isMerchant
            ? "bg-[var(--green-tint)] border border-[var(--green-border)]"
            : "bg-[var(--surface)] border border-[var(--border)]"
          }`}
        >
          {message.display_text || <span className="text-[var(--text-3)] italic">—</span>}
        </div>

        {/* Proposed terms */}
        {terms && (
          <div className={`mt-1.5 flex flex-wrap gap-3 text-[10px] text-[var(--text-2)]
            ${isMerchant ? "justify-end" : ""}`}>
            {terms.unit_price    != null && (
              <span className="tabular-nums">${terms.unit_price.toFixed(2)}/unit</span>
            )}
            {terms.quantity      != null && <span>qty {terms.quantity}</span>}
            {terms.delivery_days != null && <span>{terms.delivery_days}d delivery</span>}
            {terms.voucher_requested      && <span className="text-[var(--amber)]">+voucher</span>}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Sidebar — buyer portal navigation.
 * Structural left rail: border-only separation, single accent, no background fill.
 */

const NAV_ITEMS = [
  {
    id: "products",
    label: "Products",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-4 h-4 flex-shrink-0">
        <path d="M20 7H4a2 2 0 00-2 2v10a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2z" />
        <path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2" />
      </svg>
    ),
  },
  {
    id: "negotiate",
    label: "Negotiate",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-4 h-4 flex-shrink-0">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
      </svg>
    ),
  },
];

export default function Sidebar({ activeTab, onTabChange, hasActiveSession }) {
  return (
    <aside className="w-44 flex-shrink-0 flex flex-col border-r border-[var(--border)]">
      {/* Brand */}
      <div className="px-5 pt-6 pb-5 border-b border-[var(--border)]">
        <p className="text-[10px] font-bold text-[var(--accent)] uppercase tracking-widest">NegotiateIQ</p>
        <p className="text-[10px] text-[var(--text-3)] mt-0.5">Agents × Humans</p>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3">
        {NAV_ITEMS.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`relative w-full flex items-center gap-2.5 px-5 py-2 text-left transition-colors
                ${isActive
                  ? "text-[var(--accent)]"
                  : "text-[var(--text-2)] hover:text-[var(--text-1)]"
                }`}
            >
              {isActive && (
                <span className="absolute left-0 top-1 bottom-1 w-0.5 rounded-r bg-[var(--accent)]" />
              )}
              {item.icon}
              <span className="text-xs font-medium">{item.label}</span>
              {item.id === "negotiate" && hasActiveSession && (
                <span className="ml-auto w-1.5 h-1.5 rounded-full bg-[var(--green)] flex-shrink-0" />
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-[var(--border)]">
        <p className="text-[10px] text-[var(--text-3)]">© 2026 MadeinMind</p>
      </div>
    </aside>
  );
}

import type { FC } from "react";

interface Props {
  alertsCount: number;
  scheduleGeneratedAt?: string;
}

const navLinks = [
  {
    label: "PRD",
    href: "https://github.com/alexha11/Junction-2025/blob/main/docs/PRD.md",
  },
  {
    label: "Testing",
    href: "https://github.com/alexha11/Junction-2025/blob/main/docs/testing.md",
  },
  {
    label: "Backend",
    href: "https://github.com/alexha11/Junction-2025/tree/main/backend",
  },
  {
    label: "Agents",
    href: "https://github.com/alexha11/Junction-2025/tree/main/agents",
  },
];

const TopBar: FC<Props> = ({ alertsCount, scheduleGeneratedAt }) => {
  const refreshLabel = scheduleGeneratedAt
    ? new Date(scheduleGeneratedAt).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Pending";

  return (
    <header className="flex flex-col gap-4 rounded-[28px] border border-white/10 bg-brand-surface/80 p-4 shadow-card backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-hsy to-brand-valmet text-lg font-semibold text-white">
            HSY
          </span>
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-slate-400">
              Blominmäki Control
            </p>
            <p className="text-xl font-semibold text-white">
              Multi-Agent Pumping Copilot
            </p>
          </div>
        </div>
        <div className="flex items-center gap-6 text-sm text-slate-300">
          <div>
            <p className="text-xs uppercase tracking-widest text-slate-500">
              Alerts open
            </p>
            <p className="text-lg font-semibold text-white">{alertsCount}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-widest text-slate-500">
              Last AI update
            </p>
            <p className="text-lg font-semibold text-white">{refreshLabel}</p>
          </div>
        </div>
      </div>
      <nav className="flex flex-wrap items-center gap-3 text-sm text-slate-200">
        {navLinks.map((link) => (
          <a
            key={link.label}
            href={link.href}
            target="_blank"
            rel="noreferrer"
            className="rounded-full border border-white/10 px-4 py-1.5 transition hover:border-brand-accent/40 hover:text-white"
          >
            {link.label}
          </a>
        ))}
      </nav>
    </header>
  );
};

export default TopBar;

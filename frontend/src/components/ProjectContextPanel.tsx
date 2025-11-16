const missionPoints = [
  {
    title: "Energy impact",
    detail:
      "Reduce pumping spend without pushing tunnel level outside 0.5–8.0 m safety band.",
  },
  {
    title: "Evidence-first decisions",
    detail:
      "Blend weather, inflow, price, and physics agents so each recommendation ships with traceable context.",
  },
  {
    title: "Human control",
    detail:
      "Manual overrides, justifications, and audit trails remain first-class to maintain operator trust.",
  },
];

const stack = [
  {
    label: "Frontend",
    detail: "React · Vite · Tailwind UI with React Query for live data",
  },
  {
    label: "Backend",
    detail: "FastAPI + APScheduler exposing /system and /alerts surfaces",
  },
  {
    label: "Agents",
    detail:
      "Weather, price, inflow, status, and optimizer services exposed over MCP",
  },
];

const metrics = [
  {
    label: "Cost reduction target",
    value: ">15% vs baseline",
    caption: "Validated over 14-day simulator window",
  },
  {
    label: "Constraint breaches",
    value: "0 tolerated",
    caption: "Tunnel level + pump cooldown limits",
  },
  {
    label: "Operator trust",
    value: "Explainable plans",
    caption: "Override log + justification",
  },
];

function ProjectContextPanel() {
  return (
    <div className="glass-card space-y-5">
      <div>
        <p className="section-title mb-1">Project context</p>
        <h3 className="text-xl font-semibold text-white">
          HSY x Valmet Blominmäki flow optimization charter
        </h3>
        <p className="mt-2 text-sm text-slate-300">
          Snapshot from the PRD and testing plan so every stakeholder
          understands scope, architecture, and KPIs.
        </p>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">
          Mission priorities
        </p>
        <ul className="mt-2 space-y-3 text-sm text-slate-200">
          {missionPoints.map((point) => (
            <li
              key={point.title}
              className="rounded-2xl border border-white/5 bg-white/5 px-3 py-2 transition-all duration-300 hover:-translate-y-0.5 hover:border-white/20 hover:bg-white/10 hover:shadow-[0_6px_16px_rgba(4,25,20,0.4)]"
            >
              <p className="text-xs uppercase tracking-[0.25em] text-slate-400">
                {point.title}
              </p>
              <p className="mt-1 text-sm text-slate-100">{point.detail}</p>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">
          Architecture snapshot
        </p>
        <div className="mt-2 space-y-3">
          {stack.map((item) => (
            <div
              key={item.label}
              className="rounded-2xl border border-white/5 bg-brand-surface/60 px-3 py-2 transition-all duration-300 hover:-translate-y-0.5 hover:border-white/10 hover:bg-brand-surface/80 hover:shadow-[0_8px_20px_rgba(4,25,20,0.5)]"
            >
              <p className="text-xs uppercase tracking-widest text-slate-400">
                {item.label}
              </p>
              <p className="text-sm text-slate-200">{item.detail}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {metrics.map((metric) => (
          <div
            key={metric.label}
            className="rounded-2xl border border-brand-accent/10 bg-gradient-to-br from-brand-accent/5 to-brand-accent/10 px-3 py-2 transition-all duration-300 hover:-translate-y-0.5 hover:border-brand-accent/30 hover:shadow-[0_10px_24px_rgba(0,180,157,0.35)]"
          >
            <p className="text-xs uppercase tracking-widest text-slate-300">
              {metric.label}
            </p>
            <p className="text-lg font-semibold text-white">{metric.value}</p>
            <p className="text-xs text-slate-200/80">{metric.caption}</p>
          </div>
        ))}
      </div>
      <div className="rounded-2xl border border-white/5 bg-brand-surface/70 px-4 py-3 text-xs text-slate-300">
        Reference:{" "}
        <a
          className="text-brand-accent hover:underline"
          href="https://github.com/alexha11/Junction-2025/blob/main/docs/PRD.MD"
          target="_blank"
          rel="noreferrer"
        >
          PRD
        </a>
        &nbsp;·&nbsp;
        <a
          className="text-brand-accent hover:underline"
          href="https://github.com/alexha11/Junction-2025/blob/main/docs/TESTING.MD"
          target="_blank"
          rel="noreferrer"
        >
          Testing guide
        </a>
      </div>
    </div>
  );
}

export default ProjectContextPanel;

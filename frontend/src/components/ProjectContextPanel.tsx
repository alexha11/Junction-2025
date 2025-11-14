const missionPoints = [
  "Lower pumping energy spend while respecting tunnel safety bounds",
  "Blend weather, inflow, and price signals into a trusted AI copilot",
  "Keep operators in charge with transparent recommendations and overrides",
];

const stack = [
  {
    label: "Frontend",
    detail: "React + Vite + Tailwind powering the operator cockpit",
  },
  {
    label: "Backend",
    detail: "FastAPI orchestrates agents, scheduler, and telemetry APIs",
  },
  {
    label: "Agents",
    detail: "Weather, price, inflow, status, and optimization agents via MCP",
  },
];

const metrics = [
  {
    label: "Cost reduction target",
    value: ">15% vs baseline",
  },
  {
    label: "Constraint breaches",
    value: "0 tolerated",
  },
  {
    label: "Operator trust",
    value: "Explainable plans",
  },
];

function ProjectContextPanel() {
  return (
    <div className="glass-card space-y-5">
      <div>
        <p className="section-title mb-1">Project context</p>
        <h3 className="text-xl font-semibold text-white">
          HSY Blominmäki optimization charter
        </h3>
        <p className="mt-2 text-sm text-slate-300">
          Direct pull from the PRD so every stakeholder sees why the dashboard
          exists and what success looks like.
        </p>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">
          Mission priorities
        </p>
        <ul className="mt-2 space-y-2 text-sm text-slate-200">
          {missionPoints.map((point) => (
            <li key={point} className="rounded-2xl border border-white/5 bg-white/5 px-3 py-2">
              {point}
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
            <div key={item.label} className="rounded-2xl border border-white/5 bg-slate-900/60 px-3 py-2">
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
          <div key={metric.label} className="rounded-2xl border border-brand-accent/10 bg-brand-accent/5 px-3 py-2">
            <p className="text-xs uppercase tracking-widest text-slate-300">
              {metric.label}
            </p>
            <p className="text-lg font-semibold text-white">{metric.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ProjectContextPanel;

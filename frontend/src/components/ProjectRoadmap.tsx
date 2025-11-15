const phases = [
  {
    label: "Now",
    focus: "Stabilise telemetry & AI recommendations",
    owner: "Ops + Backend",
    status: "In progress",
    checklist: [
      "Verify FastAPI health + /system endpoints",
      "Close the loop with simulator adapter",
      "Keep operator override log flowing back to backend",
    ],
  },
  {
    label: "Next",
    focus: "Automate quality gates",
    owner: "QA + Frontend",
    status: "Planned",
    checklist: [
      "Add Vitest + Playwright runs to CI",
      "Property-test optimization constraints",
      "Record synthetic schedules for regression diffing",
    ],
  },
  {
    label: "Later",
    focus: "Production hardening",
    owner: "Platform",
    status: "Backlog",
    checklist: [
      "Redis-backed caching & audit trails",
      "Role-based access and notifications",
      "Chaos tests for agent outages",
    ],
  },
];

function ProjectRoadmap() {
  return (
    <section className="glass-card">
      <div className="flex flex-col gap-2">
        <p className="section-title mb-0">Execution roadmap</p>
        <h3 className="text-2xl font-semibold text-white">
          What it takes to ship confidently
        </h3>
        <p className="text-sm text-slate-300">
          Mirrors the testing guide so operators, engineers, and stakeholders
          can align on what is already live and what is coming next.
        </p>
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-3">
        {phases.map((phase) => (
          <div
            key={phase.label}
            className="rounded-3xl border border-white/10 bg-brand-surface/60 px-4 py-4"
          >
            <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-widest text-slate-400">
              <span>{phase.label}</span>
              <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-slate-200">
                {phase.status}
              </span>
            </div>
            <h4 className="mt-1 text-lg font-semibold text-white">
              {phase.focus}
            </h4>
            <p className="text-xs text-slate-400">Owner: {phase.owner}</p>
            <ul className="mt-3 space-y-2 text-sm text-slate-200">
              {phase.checklist.map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <span className="mt-1 inline-block h-2.5 w-2.5 rounded-full bg-brand-accent" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

export default ProjectRoadmap;

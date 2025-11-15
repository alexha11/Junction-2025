const checklist = [
  {
    label: "Telemetry feeds healthy",
    detail: "/system/state responds < 150 ms (FastAPI health)",
    status: "Operational",
  },
  {
    label: "Scheduler cadence",
    detail: "Optimization agent invoked every 15 minutes",
    status: "Monitoring",
  },
  {
    label: "Override logging",
    detail: "Manual interventions mirrored to backend",
    status: "Pending",
  },
];

const statusColor: Record<string, string> = {
  Operational: "text-emerald-300",
  Monitoring: "text-amber-300",
  Pending: "text-slate-300",
};

function DeliveryChecklist() {
  return (
    <div className="glass-card space-y-4">
      <div>
        <p className="section-title mb-1">Delivery governance</p>
        <h3 className="text-xl font-semibold text-white">
          Run-readiness checklist
        </h3>
        <p className="text-sm text-slate-300">
          Mirrors the testing guide to highlight which operational controls are
          live versus tracking.
        </p>
      </div>
      <ul className="space-y-3 text-sm text-slate-100">
        {checklist.map((item) => (
          <li
            key={item.label}
            className="rounded-2xl border border-white/5 bg-white/5 px-4 py-3"
          >
            <div className="flex items-center justify-between text-xs uppercase tracking-widest text-slate-400">
              <span>{item.label}</span>
              <span className={statusColor[item.status] ?? "text-slate-200"}>
                {item.status}
              </span>
            </div>
            <p className="mt-1 text-sm text-slate-200">{item.detail}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default DeliveryChecklist;

type Alert = {
  id: string;
  level: "info" | "warning" | "critical";
  message: string;
};

interface Props {
  alerts: Alert[];
}

const badgeStyles: Record<Alert["level"], string> = {
  info: "border-sky-400/30 bg-sky-400/5 text-sky-200",
  warning: "border-amber-400/30 bg-amber-400/5 text-amber-100",
  critical: "border-red-500/30 bg-red-500/5 text-red-100",
};

function AlertsBanner({ alerts }: Props) {
  if (!alerts || alerts.length === 0) {
    return null;
  }

  return (
    <div className="glass-card space-y-4">
      <div className="flex items-center justify-between text-xs uppercase tracking-wide text-slate-400">
        <span>Active Alerts</span>
        <span className="rounded-full border border-white/10 px-3 py-1 text-white/80">
          {alerts.length}
        </span>
      </div>
      <div className="space-y-3">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={`flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm shadow-inner ${badgeStyles[alert.level]}`}
          >
            <span className="mt-0.5 text-xs font-semibold uppercase">
              {alert.level}
            </span>
            <p className="flex-1 text-base text-white">{alert.message}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default AlertsBanner;

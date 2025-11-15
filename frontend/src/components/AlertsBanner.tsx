type Alert = {
  id: string;
  level: "info" | "warning" | "critical";
  message: string;
};

interface Props {
  alerts: Alert[];
}

const badgeStyles: Record<Alert["level"], string> = {
  info: "border-brand-accent/40 bg-brand-accent/10 text-brand-accent",
  warning: "border-brand-warn/40 bg-brand-warn/10 text-brand-warn",
  critical: "border-brand-critical/40 bg-brand-critical/10 text-brand-critical",
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
            className={`flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm shadow-inner ${
              badgeStyles[alert.level]
            }`}
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

type Alert = {
  id: string;
  level: "info" | "warning" | "critical";
  message: string;
};

const levelColor: Record<Alert["level"], string> = {
  info: "#2563eb",
  warning: "#d97706",
  critical: "#dc2626"
};

interface Props {
  alerts: Alert[];
}

function AlertsBanner({ alerts }: Props) {
  if (!alerts || alerts.length === 0) {
    return null;
  }

  return (
    <div className="card" style={{ gridColumn: "1 / -1" }}>
      {alerts.map((alert) => (
        <div
          key={alert.id}
          style={{
            background: levelColor[alert.level],
            padding: "0.75rem",
            borderRadius: "0.5rem",
            marginBottom: "0.5rem"
          }}
        >
          {alert.message}
        </div>
      ))}
    </div>
  );
}

export default AlertsBanner;

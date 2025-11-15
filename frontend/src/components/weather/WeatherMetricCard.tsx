interface Props {
  label: string;
  value: string;
  description?: string;
  trend?: "up" | "down" | "flat";
}

const trendColors: Record<NonNullable<Props["trend"]>, string> = {
  up: "text-brand-valmet",
  down: "text-brand-critical",
  flat: "text-slate-300",
};

const trendLabels: Record<NonNullable<Props["trend"]>, string> = {
  up: "rising",
  down: "falling",
  flat: "steady",
};

const WeatherMetricCard = ({
  label,
  value,
  description,
  trend = "flat",
}: Props) => (
  <div className="glass-card space-y-3">
    <p className="text-xs uppercase tracking-widest text-slate-400">{label}</p>
    <div className="flex items-end gap-2">
      <span className="text-3xl font-semibold text-white">{value}</span>
      <span
        className={`text-xs font-semibold uppercase tracking-widest ${trendColors[trend]}`}
      >
        {trendLabels[trend]}
      </span>
    </div>
    {description && (
      <p className="text-sm text-slate-400">{description}</p>
    )}
  </div>
);

export default WeatherMetricCard;

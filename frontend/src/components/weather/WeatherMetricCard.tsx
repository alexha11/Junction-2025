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
  <div className="glass-card group space-y-3 transition-all duration-300 ease-out hover:-translate-y-1 hover:bg-white/10 hover:ring-1 hover:ring-white/20">
    <p className="text-xs uppercase tracking-widest text-slate-400 transition-colors duration-300 group-hover:text-white">
      {label}
    </p>
    <div className="flex items-end gap-2">
      <span className="text-3xl font-semibold text-white transition-colors duration-300 group-hover:text-brand-valmet">
        {value}
      </span>
      <span
        className={`text-xs font-semibold uppercase tracking-widest transition-colors duration-300 ${trendColors[trend]}`}
      >
        {trendLabels[trend]}
      </span>
    </div>
    {description && (
      <p className="text-sm text-slate-400 transition-colors duration-300 group-hover:text-slate-200">
        {description}
      </p>
    )}
  </div>
);

export default WeatherMetricCard;

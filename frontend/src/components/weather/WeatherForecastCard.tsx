import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { WeatherPoint } from "../../hooks/useWeatherForecast";

interface Props {
  title: string;
  subtitle: string;
  data?: WeatherPoint[];
  loading: boolean;
  horizonLabel: string;
}

const WeatherForecastCard = ({
  title,
  subtitle,
  data,
  loading,
  horizonLabel,
}: Props) => {
  if (loading && !data) {
    return (
      <div className="glass-card h-full animate-pulse text-sm text-slate-400">
        <div className="h-full rounded-3xl border border-white/5 bg-white/5" />
      </div>
    );
  }

  const formatted = data?.map((point) => ({
    timestamp: point.timestamp,
    label: new Date(point.timestamp).toLocaleTimeString([], {
      hour: "2-digit",
    }),
    temperature: Number(point.temperature_c.toFixed(2)),
    precipitation: Number(point.precipitation_mm.toFixed(2)),
  }));

  const temperatureHigh = formatted?.reduce(
    (max, point) => Math.max(max, point.temperature),
    -Infinity
  );
  const temperatureLow = formatted?.reduce(
    (min, point) => Math.min(min, point.temperature),
    Infinity
  );
  const precipitationTotal =
    formatted?.reduce((sum, point) => sum + point.precipitation, 0) ?? 0;

  return (
    <div className="glass-card space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="section-title">{title}</p>
          <h2 className="text-2xl font-semibold text-white">{subtitle}</h2>
        </div>
        <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">
          {horizonLabel}
        </span>
      </div>
      {formatted && formatted.length > 0 ? (
        <>
          <div className="grid gap-3 rounded-3xl border border-white/5 bg-white/5 px-4 py-3 text-sm text-slate-200 md:grid-cols-3">
            <div>
              <p className="text-xs uppercase tracking-widest text-slate-400">
                High
              </p>
              <p className="text-lg font-semibold text-white">
                {temperatureHigh?.toFixed(1)}°C
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-widest text-slate-400">
                Low
              </p>
              <p className="text-lg font-semibold text-white">
                {temperatureLow?.toFixed(1)}°C
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-widest text-slate-400">
                Precip.
              </p>
              <p className="text-lg font-semibold text-white">
                {precipitationTotal.toFixed(1)} mm
              </p>
            </div>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={formatted} margin={{ left: 12, right: 12 }}>
                <defs>
                  <linearGradient
                    id="precipGradient"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop offset="0%" stopColor="#00b49d" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#041914" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#1a342c" strokeDasharray="3 3" />
                <XAxis
                  dataKey="label"
                  tick={{ fill: "#6b8a7f", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  yAxisId="temperature"
                  orientation="left"
                  tick={{ fill: "#6b8a7f", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  yAxisId="precipitation"
                  orientation="right"
                  tick={{ fill: "#6b8a7f", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "#031511",
                    borderRadius: 16,
                    border: "1px solid rgba(0,180,157,0.25)",
                    color: "white",
                  }}
                />
                <Bar
                  yAxisId="precipitation"
                  dataKey="precipitation"
                  fill="url(#precipGradient)"
                  radius={[6, 6, 0, 0]}
                />
                <Area
                  yAxisId="precipitation"
                  type="monotone"
                  dataKey="precipitation"
                  fill="url(#precipGradient)"
                  stroke="#00b49d"
                  strokeWidth={2}
                />
                <Line
                  yAxisId="temperature"
                  type="monotone"
                  dataKey="temperature"
                  stroke="#5ab946"
                  strokeWidth={3}
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : (
        <div className="rounded-3xl border border-dashed border-white/10 px-4 py-12 text-center text-sm text-slate-400">
          Weather data not available yet.
        </div>
      )}
    </div>
  );
};

export default WeatherForecastCard;

import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { LegendProps, TooltipProps } from "recharts";
import type { WeatherPoint } from "../../hooks/useWeatherForecast";
import { BRAND_COLORS, brandColorWithOpacity } from "../../theme/colors";

interface Props {
  title: string;
  subtitle: string;
  data?: WeatherPoint[];
  loading: boolean;
  horizonLabel: string;
}

type FormattedPoint = {
  timestamp: string;
  label: string;
  fullLabel: string;
  temperature: number;
  precipitation: number;
};

const formatTimestamp = (value: string) =>
  new Date(value).toLocaleString([], {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

const CustomTooltip = ({ active, payload }: TooltipProps<number, string>) => {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0]?.payload as FormattedPoint | undefined;
  if (!point) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/80 p-3 text-xs text-white shadow-xl">
      <p className="text-[11px] uppercase tracking-wide text-slate-400">
        {point.fullLabel}
      </p>
      <div className="mt-2 space-y-1.5">
        <div className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-2 text-slate-300">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: BRAND_COLORS.valmet }}
            />
            Temperature
          </span>
          <span className="font-semibold">
            {point.temperature.toFixed(1)}°C
          </span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-2 text-slate-300">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: BRAND_COLORS.accent }}
            />
            Precipitation
          </span>
          <span className="font-semibold">
            {point.precipitation.toFixed(1)} mm
          </span>
        </div>
      </div>
    </div>
  );
};

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

  const formatted: FormattedPoint[] | undefined = data?.map((point) => ({
    timestamp: point.timestamp,
    label: new Date(point.timestamp).toLocaleTimeString([], {
      hour: "2-digit",
    }),
    fullLabel: formatTimestamp(point.timestamp),
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

  const startPoint = formatted?.[0];
  const endPoint =
    formatted && formatted.length > 0
      ? formatted[formatted.length - 1]
      : undefined;
  const timelineStart = startPoint?.fullLabel;
  const timelineEnd = endPoint?.fullLabel;
  const legendPayload: LegendProps["payload"] = [
    {
      id: "temperature",
      type: "line",
      value: "Temperature (°C)",
      color: BRAND_COLORS.valmet,
    },
    {
      id: "precipitation",
      type: "rect",
      value: "Precipitation (mm)",
      color: BRAND_COLORS.accent,
    },
  ];

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
          {timelineStart && timelineEnd && (
            <div className="rounded-3xl border border-white/5 bg-slate-900/30 px-4 py-2 text-xs text-slate-300">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-slate-500">
                    Forecast Start
                  </p>
                </div>
                <div className="h-8 w-px bg-white/10" />
                <div className="text-right">
                  <p className="text-[10px] uppercase tracking-widest text-slate-500">
                    Forecast End
                  </p>
                </div>
              </div>
            </div>
          )}
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
                    <stop
                      offset="0%"
                      stopColor={BRAND_COLORS.accent}
                      stopOpacity={0.45}
                    />
                    <stop
                      offset="100%"
                      stopColor={BRAND_COLORS.base}
                      stopOpacity={0}
                    />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  stroke={BRAND_COLORS.gridMuted}
                  strokeDasharray="3 3"
                />
                <Legend
                  verticalAlign="top"
                  align="right"
                  wrapperStyle={{ paddingBottom: 8 }}
                  payload={legendPayload}
                  iconSize={10}
                />
                <XAxis
                  dataKey="label"
                  tick={{ fill: BRAND_COLORS.textMuted, fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  yAxisId="temperature"
                  orientation="left"
                  tick={{ fill: BRAND_COLORS.textMuted, fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  label={{
                    value: "°C",
                    angle: -90,
                    position: "insideLeft",
                    fill: BRAND_COLORS.textMuted,
                    fontSize: 11,
                  }}
                />
                <YAxis
                  yAxisId="precipitation"
                  orientation="right"
                  tick={{ fill: BRAND_COLORS.textMuted, fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  label={{
                    value: "mm",
                    angle: 90,
                    position: "insideRight",
                    fill: BRAND_COLORS.textMuted,
                    fontSize: 11,
                  }}
                />
                <Tooltip
                  content={<CustomTooltip />}
                  cursor={{
                    stroke: brandColorWithOpacity("gridStrong", 0.35),
                    strokeWidth: 1,
                  }}
                />
                {startPoint?.label && (
                  <ReferenceLine
                    x={startPoint.label}
                    yAxisId="temperature"
                    stroke={brandColorWithOpacity("gridStrong", 0.75)}
                    strokeDasharray="6 6"
                    label={{
                      value: "Now",
                      position: "insideTop",
                      fill: BRAND_COLORS.textMuted,
                      fontSize: 11,
                    }}
                  />
                )}
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
                  stroke={BRAND_COLORS.accent}
                  strokeWidth={2}
                />
                <Line
                  yAxisId="temperature"
                  type="monotone"
                  dataKey="temperature"
                  stroke={BRAND_COLORS.valmet}
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

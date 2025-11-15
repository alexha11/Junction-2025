import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  BRAND_COLORS,
  brandColorWithOpacity,
  withOpacity,
} from "../theme/colors";

type Series = {
  metric: string;
  unit: string;
  points: { timestamp: string; value: number }[];
};

interface Props {
  inflow?: Series;
  prices?: Series;
}

type ChartSection = {
  id: string;
  label: string;
  badge: string;
  badgeClass: string;
  lineColor: string;
  series: Series;
};

const ForecastPanel = ({ prices }: Props) => {
  const chartSections: ChartSection[] = [];

  if (prices) {
    chartSections.push({
      id: "price",
      label: `Electricity price (${prices.unit ?? "EUR"})`,
      badge: "market",
      badgeClass: "text-brand-valmet",
      lineColor: BRAND_COLORS.valmet,
      series: prices,
    });
  }

  return (
    <div className="glass-card">
      <div className="flex items-center justify-between">
        <div>
          <p className="section-title">Forecast horizon</p>
          <h2 className="text-2xl font-semibold text-white">Next 24 hours</h2>
        </div>
        <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">
          auto-refreshing
        </span>
      </div>
      <div className="mt-6 space-y-8">
        {chartSections.length > 0 ? (
          chartSections.map(({ id, ...rest }) => (
            <SeriesChartCard key={id} {...rest} />
          ))
        ) : (
          <div className="flex h-32 items-center justify-center rounded-3xl border border-dashed border-white/10 text-sm text-slate-400">
            Waiting for forecast stream...
          </div>
        )}
      </div>
    </div>
  );
};

type SeriesChartProps = Omit<ChartSection, "id">;

const SeriesChartCard = ({
  label,
  badge,
  badgeClass,
  lineColor,
  series,
}: SeriesChartProps) => {
  const data = useMemo(() => formatSeriesPoints(series.points), [series]);

  if (data.length === 0) {
    return (
      <div className="flex h-44 items-center justify-center rounded-3xl border border-dashed border-white/10 text-sm text-slate-400">
        {`Waiting for ${series.metric.toLowerCase()} data...`}
      </div>
    );
  }

  const firstPoint = data[0];
  const lastPoint = data[data.length - 1];

  return (
    <div>
      <div className="mb-3 flex items-center justify-between text-sm text-slate-400">
        <span>{label}</span>
        <span className={badgeClass}>{badge}</span>
      </div>
      <div className="h-52">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 12, bottom: 6, left: 2, right: 12 }}
          >
            <CartesianGrid
              stroke={brandColorWithOpacity("gridMuted", 0.8)}
              strokeDasharray="3 3"
            />
            <XAxis
              dataKey="timestamp"
              axisLine={false}
              tickLine={false}
              tick={{ fill: BRAND_COLORS.textMuted, fontSize: 12 }}
              tickFormatter={formatAxisTick}
              interval="preserveStartEnd"
              minTickGap={18}
            />
            <YAxis
              width={36}
              axisLine={false}
              tickLine={false}
              tick={{ fill: BRAND_COLORS.textMuted, fontSize: 12 }}
              tickFormatter={(value: number) => value.toFixed(1)}
              stroke={BRAND_COLORS.gridStrong}
            />
            <Tooltip
              labelFormatter={formatTooltipLabel}
              formatter={(value: number) => [
                `${value.toFixed(2)} ${series.unit}`,
                series.metric,
              ]}
              contentStyle={{
                background: BRAND_COLORS.surfaceAlt,
                borderRadius: 16,
                border: `1px solid ${withOpacity(lineColor, 0.35)}`,
                color: "white",
              }}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={lineColor}
              strokeWidth={3}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 0 }}
              strokeLinecap="round"
            />
            <ReferenceDot
              x={firstPoint.timestamp}
              y={firstPoint.value}
              r={10}
              fill={lineColor}
              stroke={BRAND_COLORS.surface}
              strokeWidth={2}
              label={{
                value: "Now",
                fill: BRAND_COLORS.textMuted,
                fontSize: 10,
                position: "top",
              }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-slate-400">
        {`Start ${formatAxisTick(firstPoint.timestamp)} · End ${formatAxisTick(
          lastPoint.timestamp
        )}`}
      </p>
    </div>
  );
};

type ChartPoint = Series["points"][number] & { label: string };

const formatSeriesPoints = (points: Series["points"]): ChartPoint[] =>
  [...points]
    .sort(
      (a, b) =>
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )
    .map((point) => ({
      ...point,
      label: formatAxisTick(point.timestamp),
    }));

const formatAxisTick = (value: string) =>
  new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

const formatTooltipLabel = (value: string) =>
  new Date(value).toLocaleString([], {
    hour: "2-digit",
    minute: "2-digit",
    weekday: "short",
  });

export default ForecastPanel;

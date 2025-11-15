import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Series = {
  metric: string;
  unit: string;
  points: { timestamp: string; value: number }[];
};

interface Props {
  inflow?: Series;
  prices?: Series;
}

const ForecastPanel = ({ inflow, prices }: Props) => (
  <div className="glass-card">
    <div className="flex items-center justify-between">
      <div>
        <p className="section-title">Forecast horizon</p>
        <h2 className="text-2xl font-semibold text-white">Next 12 hours</h2>
      </div>
      <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">
        auto-refreshing
      </span>
    </div>
    <div className="mt-6 space-y-8">
      <div>
        <div className="mb-3 flex items-center justify-between text-sm text-slate-400">
          <span>Inflow F1 ({inflow?.unit ?? "m³/s"})</span>
          <span className="text-brand-accent">hydrology</span>
        </div>
        <div className="h-56">
          {inflow ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={inflow.points}>
                <XAxis dataKey="timestamp" hide />
                <YAxis
                  domain={[0, "dataMax + 1"]}
                  width={32}
                  stroke="#475569"
                />
                <Tooltip
                  labelFormatter={(value) =>
                    new Date(value).toLocaleTimeString()
                  }
                  contentStyle={{
                    background: "#0f172a",
                    borderRadius: 16,
                    border: "1px solid rgba(148,163,184,0.3)",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#38bdf8"
                  strokeWidth={3}
                  dot={false}
                  strokeLinecap="round"
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">
              Loading inflow forecast...
            </div>
          )}
        </div>
      </div>
      <div>
        <div className="mb-3 flex items-center justify-between text-sm text-slate-400">
          <span>Electricity price ({prices?.unit ?? "EUR"})</span>
          <span className="text-brand-warn">market</span>
        </div>
        <div className="h-52">
          {prices ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={prices.points}>
                <XAxis dataKey="timestamp" hide />
                <YAxis width={32} stroke="#475569" />
                <Tooltip
                  labelFormatter={(value) =>
                    new Date(value).toLocaleTimeString()
                  }
                  contentStyle={{
                    background: "#0f172a",
                    borderRadius: 16,
                    border: "1px solid rgba(148,163,184,0.3)",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#f97316"
                  strokeWidth={3}
                  dot={false}
                  strokeLinecap="round"
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">
              Loading price forecast...
            </div>
          )}
        </div>
      </div>
    </div>
  </div>
);

export default ForecastPanel;

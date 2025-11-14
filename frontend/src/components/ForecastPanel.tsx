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
  <div className="card">
    <h2>12h Forecast</h2>
    <div style={{ height: 240 }}>
      {inflow ? (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={inflow.points}>
            <XAxis dataKey="timestamp" hide />
            <YAxis domain={[0, "dataMax + 1"]} width={40} />
            <Tooltip
              labelFormatter={(value) => new Date(value).toLocaleTimeString()}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#38bdf8"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div>Loading inflow forecast...</div>
      )}
    </div>
    <div style={{ height: 200, marginTop: "1rem" }}>
      {prices ? (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={prices.points}>
            <XAxis dataKey="timestamp" hide />
            <YAxis width={40} />
            <Tooltip
              labelFormatter={(value) => new Date(value).toLocaleTimeString()}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#f97316"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div>Loading price forecast...</div>
      )}
    </div>
  </div>
);

export default ForecastPanel;

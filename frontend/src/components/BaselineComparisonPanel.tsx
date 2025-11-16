import type { FC } from "react";
import { SystemState } from "../hooks/system";

interface Props {
  state?: SystemState;
  loading?: boolean;
}

const BaselineComparisonPanel: FC<Props> = ({ state, loading }) => {
  if (loading || !state || !state.baseline || !state.optimized) {
    return null; // Don't show if no baseline data
  }

  const baseline = state.baseline;
  const optimized = state.optimized;
  const savings = state.savings;

  const formatValue = (value?: number, unit: string = "") => {
    if (value === undefined || value === null) return "--";
    return `${value.toFixed(2)} ${unit}`;
  };

  const formatPercent = (value?: number) => {
    if (value === undefined || value === null) return "--";
    const sign = value >= 0 ? "+" : "";
    return `${sign}${value.toFixed(1)}%`;
  };

  const comparisonRows = [
    {
      label: "Energy consumption",
      baseline: formatValue(baseline.energy_kwh, "kWh"),
      optimized: formatValue(optimized.energy_kwh, "kWh"),
      savings: savings?.energy_percent ? formatPercent(savings.energy_percent) : "--",
      isPositive: (savings?.energy_percent || 0) > 0,
    },
    {
      label: "Cost",
      baseline: formatValue(baseline.cost_eur, "€"),
      optimized: formatValue(optimized.cost_eur, "€"),
      savings: savings?.cost_percent ? formatPercent(savings.cost_percent) : "--",
      isPositive: (savings?.cost_percent || 0) > 0,
    },
  ];

  return (
    <div className="glass-card">
      <p className="section-title">Performance comparison</p>
      <h2 className="text-2xl font-semibold text-white">Optimized vs Baseline</h2>
      
      <div className="mt-6 overflow-x-auto">
        <table className="w-full text-sm text-slate-300">
          <thead className="bg-white/5 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3 text-left">Metric</th>
              <th className="px-4 py-3 text-right">Baseline</th>
              <th className="px-4 py-3 text-right">Optimized</th>
              <th className="px-4 py-3 text-right">Savings</th>
            </tr>
          </thead>
          <tbody>
            {comparisonRows.map((row) => (
              <tr
                key={row.label}
                className="border-t border-white/5 text-white/90 last:border-b-0 transition-colors duration-500 hover:bg-white/5"
              >
                <td className="px-4 py-3 font-medium">{row.label}</td>
                <td className="px-4 py-3 text-right text-slate-400">{row.baseline}</td>
                <td className="px-4 py-3 text-right text-white">{row.optimized}</td>
                <td className={`px-4 py-3 text-right font-semibold ${
                  row.isPositive ? "text-green-400" : "text-slate-400"
                }`}>
                  {row.savings}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {state.violation_count !== undefined && (
        <div className="mt-4 rounded-2xl border border-white/5 bg-white/5 px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-300">Constraint violations</span>
            <span className={`text-sm font-semibold ${
              state.violation_count === 0 ? "text-green-400" : "text-red-400"
            }`}>
              {state.violation_count === 0 ? "0 ✅" : `${state.violation_count} ⚠️`}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default BaselineComparisonPanel;


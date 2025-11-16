import type { FC } from "react";
import { SystemState } from "hooks/system";

interface Props {
  state?: SystemState;
  loading: boolean;
}

const Stat = ({ label, value }: { label: string; value: string }) => (
  <div className="flex flex-col gap-1 rounded-2xl border border-white/5 bg-white/5 px-4 py-3">
    <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
      {label}
    </span>
    <span className="text-2xl font-semibold text-white">{value}</span>
  </div>
);

const SystemOverviewCard: FC<Props> = ({ state, loading }) => {
  const tunnelVolumeM3 = 19950;

  const formatMeters = (value?: number) =>
    typeof value === "number" && Number.isFinite(value)
      ? value.toFixed(2)
      : "--";

  const formatVolume = (value?: number) =>
    typeof value === "number" && Number.isFinite(value)
      ? `${Math.round(value).toLocaleString()} m³`
      : "--";

  return (
    <div className="glass-card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="section-title">System overview</p>
          <h2 className="text-2xl font-semibold text-white">Realtime health</h2>
        </div>
        {!loading && state && (
          <span className="text-xs text-slate-400">
            Simulation current time: {state.timestamp}
          </span>
        )}
      </div>
      {loading || !state ? (
        <div className="mt-6 animate-pulse rounded-2xl border border-white/5 px-4 py-6 text-center text-sm text-slate-400">
          Loading latest telemetry...
        </div>
      ) : (
        <div className="mt-6 grid w-full gap-4 md:grid-cols-2">
          <Stat
            label="Tunnel level L2 (m)"
            value={state.tunnel_level_l2_m.toFixed(2)}
          />
          <Stat
            label="Water volume in tunnel L1 (m³)"
            value={formatVolume(state.tunnel_water_volume_l1_m3)}
          />
          <Stat label="Inflow F1 (m³/s)" value={state.inflow_m3_s.toFixed(2)} />
          <Stat
            label="Outflow F2 (m³/s)"
            value={state.outflow_m3_s.toFixed(2)}
          />
          <Stat
            label="Price (cents (€)/kWh)"
            value={state.electricity_price_eur_cents_kwh.toFixed(2)}
          />
        </div>
      )}
      <div className="mt-6 max-h-64 overflow-auto rounded-2xl border border-white/5 scroll-glow">
        <table className="w-full text-sm text-slate-300">
          <thead className="bg-white/5 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3 text-left">Pump</th>
              <th className="px-4 py-3 text-left">State</th>
              <th className="px-4 py-3 text-right">Hz</th>
              <th className="px-4 py-3 text-right">kW</th>
            </tr>
          </thead>
          <tbody>
            {state?.pumps?.map((pump) => (
              <tr
                key={pump.pump_id}
                className="border-t border-white/5 text-white/90 last:border-b-0 hover:bg-white/5"
              >
                <td className="px-4 py-2 font-semibold">{pump.pump_id}</td>
                <td className="px-4 py-2 capitalize text-slate-300">
                  {pump.state}
                </td>
                <td className="px-4 py-2 text-right">
                  {pump.frequency_hz.toFixed(2)}
                </td>
                <td className="px-4 py-2 text-right">
                  {pump.power_kw.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default SystemOverviewCard;

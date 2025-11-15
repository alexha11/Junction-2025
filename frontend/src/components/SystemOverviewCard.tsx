import type { FC } from "react";

interface PumpStatus {
  pump_id: string;
  state: string;
  frequency_hz: number;
  power_kw: number;
}

interface Props {
  state?: {
    tunnel_level_m: number;
    tunnel_level_l2_m: number;
    inflow_m3_s: number;
    outflow_m3_s: number;
    electricity_price_eur_mwh: number;
    pumps: PumpStatus[];
  };
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

const SystemOverviewCard: FC<Props> = ({ state, loading }) => (
  <div className="glass-card">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="section-title">System overview</p>
        <h2 className="text-2xl font-semibold text-white">Realtime health</h2>
      </div>
      {!loading && state && (
        <span className="text-xs text-slate-400">
          {new Date().toLocaleTimeString()}
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
          label="Tunnel level L1/L2 (m)"
          value={`L1 ${state.tunnel_level_m.toFixed(
            2
          )} / L2 ${state.tunnel_level_l2_m.toFixed(2)}`}
        />
        <Stat label="Inflow F1 (m³/s)" value={state.inflow_m3_s.toFixed(2)} />
        <Stat label="Outflow F2 (m³/s)" value={state.outflow_m3_s.toFixed(2)} />
        <Stat
          label="Price (C/kWh)"
          value={state.electricity_price_eur_mwh.toFixed(1)}
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
                {pump.frequency_hz.toFixed(1)}
              </td>
              <td className="px-4 py-2 text-right">
                {pump.power_kw.toFixed(0)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

export default SystemOverviewCard;

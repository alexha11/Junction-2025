import type { FC } from "react";
import { SystemState } from "../hooks/system";
import useAnimatedNumber from "../hooks/useAnimatedNumber";
import System3DScene from "./System3DScene";

interface Props {
  state?: SystemState;
  loading: boolean;
}

const Stat = ({ label, value }: { label: string; value: string }) => (
  <div className="flex flex-col gap-1 rounded-2xl border border-white/5 bg-white/5 px-4 py-3 shadow-inner shadow-black/20 transition duration-500">
    <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
      {label}
    </span>
    <span className="text-2xl font-semibold text-white">{value}</span>
  </div>
);

const TUNNEL_CAPACITY_M3 = 19950;

const SystemOverviewCard: FC<Props> = ({ state, loading }) => {
  const animatedTunnelVolume = useAnimatedNumber(
    state?.tunnel_water_volume_l1_m3
  );
  const animatedInflow = useAnimatedNumber(state?.inflow_m3_s);
  const animatedOutflow = useAnimatedNumber(state?.outflow_m3_s);
  const animatedPrice = useAnimatedNumber(
    state?.electricity_price_eur_cents_kwh,
    { duration: 1000 }
  );

  const formatMeters = (value?: number) =>
    typeof value === "number" && Number.isFinite(value)
      ? value.toFixed(2)
      : "--";

  const formatVolume = (value?: number) =>
    typeof value === "number" && Number.isFinite(value)
      ? `${Math.round(value).toLocaleString()} m³`
      : "--";

  const pumpStateAccent = (value?: string) => {
    if (!value) return "bg-slate-600";
    const normalized = value.toLowerCase();
    if (normalized.includes("fault")) return "bg-rose-400";
    if (normalized.includes("run") || normalized.includes("on"))
      return "bg-cyan-400";
    return "bg-amber-400";
  };

  const tunnelFillRatio = state
    ? Math.min(
        Math.max(state.tunnel_water_volume_l1_m3 / TUNNEL_CAPACITY_M3, 0),
        1
      )
    : undefined;

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
            label="Water volume in tunnel L1 (m³)"
            value={formatVolume(animatedTunnelVolume)}
          />
          <Stat label="Inflow F1 (m³/s)" value={formatMeters(animatedInflow)} />
          <Stat
            label="Outflow F2 (m³/s)"
            value={formatMeters(animatedOutflow)}
          />
          <Stat
            label="Price (cents (€)/kWh)"
            value={formatMeters(animatedPrice)}
          />
          {state?.total_run_hours !== undefined && (
            <Stat
              label="Total run hours"
              value={`${state.total_run_hours.toFixed(2)} h`}
            />
          )}
          {state?.violation_count !== undefined && (
            <Stat
              label="Constraint violations"
              value={state.violation_count === 0 ? "0 ✅" : `${state.violation_count} ⚠️`}
            />
          )}
          {state?.energy_kwh !== undefined && (
            <Stat
              label="Energy consumption"
              value={`${state.energy_kwh.toFixed(2)} kWh`}
            />
          )}
          {state?.cost_eur !== undefined && (
            <Stat
              label="Cost"
              value={`€${state.cost_eur.toFixed(2)}`}
            />
          )}
          {state?.savings && (state.savings.cost_eur !== undefined || state.savings.energy_kwh !== undefined) && (
            <Stat
              label="Savings vs baseline"
              value={
                state.savings.cost_percent !== undefined
                  ? `€${state.savings.cost_eur?.toFixed(2) || 0} (${state.savings.cost_percent.toFixed(1)}%)`
                  : `${state.savings.energy_kwh?.toFixed(2) || 0} kWh (${state.savings.energy_percent?.toFixed(1) || 0}%)`
              }
            />
          )}
          {state?.specific_energy_kwh_m3 !== undefined && (
            <Stat
              label="Specific energy"
              value={`${state.specific_energy_kwh_m3.toFixed(2)} kWh/m³`}
            />
          )}
        </div>
      )}
      <div className="mt-6 max-h-64 overflow-auto rounded-2xl border border-white/5 scroll-glow">
        <table className="w-full text-sm text-slate-300">
          <thead className="bg-white/5 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3 text-left">Pump</th>
              <th className="px-4 py-3 text-left">State</th>
              <th className="px-4 py-3 text-right">Hz</th>
              <th className="px-4 py-3 text-right">Run Hours</th>
            </tr>
          </thead>
          <tbody>
            {state?.pumps?.map((pump) => (
              <tr
                key={pump.pump_id}
                className="group border-t border-white/5 text-white/90 last:border-b-0 transition-colors duration-500 hover:bg-white/5"
              >
                <td className="px-4 py-2 font-semibold">
                  <span
                    className={`mr-2 inline-flex h-2 w-2 rounded-full transition duration-500 ${pumpStateAccent(
                      pump.state
                    )}`}
                  />
                  <span className="align-middle">{pump.pump_id}</span>
                  {/* Show pump type (big/small) from simulation data */}
                  {(pump as any).type && (
                    <span className={`ml-2 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                      (pump as any).type === "big" 
                        ? "bg-blue-400/15 text-blue-200" 
                        : "bg-green-400/15 text-green-200"
                    }`}>
                      {(pump as any).type === "big" ? "Big" : "Small"}
                    </span>
                  )}
                </td>
                <td className="px-4 py-2 capitalize text-slate-300">
                  {pump.state}
                </td>
                <td className="px-4 py-2 text-right">
                  {pump.frequency_hz.toFixed(2)}
                </td>
                <td className="px-4 py-2 text-right text-slate-400">
                  {pump.running_hours !== undefined ? pump.running_hours.toFixed(2) : "--"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4">
        <System3DScene
          pumps={state?.pumps}
          inflow={state?.inflow_m3_s}
          outflow={state?.outflow_m3_s}
          tunnelFillRatio={tunnelFillRatio}
          tunnelLevelL1={state?.tunnel_level_l1_m ?? (state?.tunnel_water_volume_l1_m3 ? state.tunnel_water_volume_l1_m3 / 6250 : 0)} // Use L1 level directly, or calculate from volume
          tunnelLevelL2={state?.tunnel_level_l2_m ?? 0}
          loading={loading || !state}
        />
      </div>
    </div>
  );
};

export default SystemOverviewCard;

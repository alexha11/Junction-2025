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
    inflow_m3_s: number;
    outflow_m3_s: number;
    electricity_price_eur_mwh: number;
    pumps: PumpStatus[];
  };
  loading: boolean;
}

const Stat = ({ label, value }: { label: string; value: string }) => (
  <div>
    <div
      style={{ fontSize: "0.75rem", textTransform: "uppercase", opacity: 0.7 }}
    >
      {label}
    </div>
    <div style={{ fontSize: "1.75rem", fontWeight: 600 }}>{value}</div>
  </div>
);

const SystemOverviewCard: FC<Props> = ({ state, loading }) => (
  <div className="card">
    <h2>System Overview</h2>
    {loading || !state ? (
      <div>Loading...</div>
    ) : (
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        <Stat
          label="Tunnel Level (m)"
          value={state.tunnel_level_m.toFixed(2)}
        />
        <Stat label="Inflow (m³/s)" value={state.inflow_m3_s.toFixed(2)} />
        <Stat label="Outflow (m³/s)" value={state.outflow_m3_s.toFixed(2)} />
        <Stat
          label="Price (EUR/MWh)"
          value={state.electricity_price_eur_mwh.toFixed(1)}
        />
      </div>
    )}
    <div style={{ marginTop: "1rem", maxHeight: 160, overflow: "auto" }}>
      <table width="100%">
        <thead>
          <tr>
            <th align="left">Pump</th>
            <th align="left">State</th>
            <th align="right">Hz</th>
            <th align="right">kW</th>
          </tr>
        </thead>
        <tbody>
          {state?.pumps?.map((pump) => (
            <tr key={pump.pump_id}>
              <td>{pump.pump_id}</td>
              <td>{pump.state}</td>
              <td align="right">{pump.frequency_hz.toFixed(1)}</td>
              <td align="right">{pump.power_kw.toFixed(0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

export default SystemOverviewCard;

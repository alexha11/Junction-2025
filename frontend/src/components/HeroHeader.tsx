import type { FC } from "react";

interface PumpStatus {
  pump_id: string;
  state: string;
  frequency_hz: number;
  power_kw: number;
}

interface ScheduleEntry {
  pump_id: string;
  target_frequency_hz: number;
  start_time: string;
  end_time: string;
}

interface Schedule {
  generated_at?: string;
  entries?: ScheduleEntry[];
  justification?: string;
}

interface Props {
  state?: {
    tunnel_level_m: number;
    inflow_m3_s: number;
    outflow_m3_s: number;
    electricity_price_eur_mwh: number;
    pumps: PumpStatus[];
  };
  schedule?: Schedule;
  alertsCount: number;
}

const insightPills = [
  "Realtime risk posture",
  "Optimization cadence: 15 min",
  "Operator in-the-loop guarantees",
];

const HeroHeader: FC<Props> = ({ state, schedule, alertsCount }) => {
  const pumpCount = state?.pumps?.length ?? 0;
  const pumpsActive = state?.pumps
    ? state.pumps.filter((pump) => ["running", "on"].includes(pump.state))
        .length
    : undefined;

  const lastPlanWindow = schedule?.entries?.[0]
    ? `${new Date(
        schedule.entries[0].start_time
      ).toLocaleTimeString()} → ${new Date(
        schedule.entries[0].end_time
      ).toLocaleTimeString()}`
    : "Awaiting AI plan";

  const lastGenerated = schedule?.generated_at
    ? new Date(schedule.generated_at).toLocaleTimeString()
    : "—";

  const metricCards = [
    {
      label: "Tunnel level",
      value: state ? `${state.tunnel_level_m.toFixed(2)} m` : "--",
      sub: "Live telemetry",
    },
    {
      label: "Inflow vs outflow",
      value:
        state && typeof state.inflow_m3_s === "number"
          ? `${state.inflow_m3_s.toFixed(1)} / ${state.outflow_m3_s.toFixed(
              1
            )} m³/s`
          : "--",
      sub: "Hydro balance",
    },
    {
      label: "Power price",
      value: state
        ? `${state.electricity_price_eur_mwh.toFixed(1)} €/MWh`
        : "--",
      sub: "Nord Pool feed",
    },
    {
      label: "Active pumps",
      value:
        pumpsActive !== undefined && pumpCount
          ? `${pumpsActive}/${pumpCount}`
          : "--",
      sub: "Operational",
    },
  ];

  return (
    <section className="relative overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-slate-950/95 via-slate-950/70 to-slate-900/30 p-8 shadow-card">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_20%_0%,rgba(56,189,248,0.35),transparent_60%),radial-gradient(circle_at_90%_20%,rgba(249,115,22,0.2),transparent_65%)]" />
      <div className="flex flex-wrap items-center gap-3 text-xs font-medium uppercase tracking-wider text-slate-200">
        <span className="rounded-full border border-white/15 px-3 py-1 text-white/90">
          HSY · Blominmäki
        </span>
        <span className="rounded-full border border-brand-accent/40 bg-brand-accent/10 px-3 py-1 text-brand-accent">
          AI Copilot Stack
        </span>
        <span className="rounded-full border border-white/10 px-3 py-1 text-slate-200">
          Active alerts · {alertsCount}
        </span>
      </div>
      <div className="mt-6 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-4">
          <div>
            <p className="section-title mb-2">Executive mission brief</p>
            <h1 className="text-3xl font-semibold text-white sm:text-4xl">
              Operational resilience through transparent, multi-agent decisions.
            </h1>
          </div>
          <p className="max-w-3xl text-base text-slate-300">
            Weather, inflow, market, and physics agents collaborate via MCP
            tooling, feeding FastAPI services that publish actionable
            recommendations every 15 minutes. Operators always see the evidence,
            can audit justifications, and override safely.
          </p>
          <div className="flex flex-wrap gap-3 text-xs font-semibold uppercase tracking-widest">
            {insightPills.map((pill) => (
              <span
                key={pill}
                className="rounded-full border border-white/15 bg-white/5 px-4 py-1 text-slate-100"
              >
                {pill}
              </span>
            ))}
          </div>
        </div>
        <div className="rounded-3xl border border-white/10 bg-black/40 px-6 py-4 text-sm text-slate-200">
          <div className="flex items-center justify-between gap-6">
            <div>
              <p className="text-xs uppercase tracking-widest text-slate-400">
                Last AI plan
              </p>
              <p className="mt-1 text-lg font-semibold text-white">
                {lastPlanWindow}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs uppercase tracking-widest text-slate-400">
                Generated
              </p>
              <p className="mt-1 text-lg font-semibold text-white">
                {lastGenerated}
              </p>
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-400">
            Recommendation payloads, justification text, and manual overrides
            are retained for audit readiness.
          </p>
        </div>
      </div>
      <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {metricCards.map((metric) => (
          <div
            key={metric.label}
            className="rounded-3xl border border-white/10 bg-white/5 px-5 py-4 text-slate-200"
          >
            <p className="text-xs uppercase tracking-widest text-slate-400">
              {metric.label}
            </p>
            <p className="mt-2 text-2xl font-semibold text-white">
              {metric.value}
            </p>
            <p className="text-xs text-slate-400">{metric.sub}</p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default HeroHeader;

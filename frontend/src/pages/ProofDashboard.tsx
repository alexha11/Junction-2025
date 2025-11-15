import ProjectContextPanel from "../components/ProjectContextPanel";
import ProjectRoadmap from "../components/ProjectRoadmap";
import DeliveryChecklist from "../components/DeliveryChecklist";
import AlertsBanner from "../components/AlertsBanner";
import HeroHeader from "../components/HeroHeader";
import {
  ScheduleRecommendation,
  SystemState,
  useScheduleRecommendation,
  useSystemState,
} from "../hooks/system";

const proofAlerts = [
  {
    id: "roadmap",
    level: "info" as const,
    message:
      "Simulated telemetry replay validated optimization loop latency (< 2 min).",
  },
];

const fallbackState: SystemState = {
  timestamp: new Date().toISOString(),
  tunnel_level_m: 3.15,
  tunnel_level_l2_m: 3.05,
  inflow_m3_s: 2.3,
  outflow_m3_s: 2.1,
  electricity_price_eur_mwh: 74.5,
  pumps: Array.from({ length: 8 }).map((_, index) => ({
    pump_id: `P${index + 1}`,
    state: index % 2 === 0 ? "running" : "standby",
    frequency_hz: index % 2 === 0 ? 48.5 : 0,
    power_kw: index % 2 === 0 ? 360 : 0,
  })),
};

const fallbackSchedule: ScheduleRecommendation = {
  generated_at: new Date().toISOString(),
  horizon_minutes: 120,
  entries: [
    {
      pump_id: "P1",
      target_frequency_hz: 48.5,
      start_time: new Date().toISOString(),
      end_time: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    },
    {
      pump_id: "P2",
      target_frequency_hz: 47.8,
      start_time: new Date().toISOString(),
      end_time: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
    },
  ],
  justification:
    "Keep inflow aligned with outflow while electricity prices are favorable for proactive pumping.",
};

const alerts = [
  {
    id: "alert-1",
    level: "warning" as const,
    message:
      "Tunnel level trending 0.2 m above target window, monitor inflow closely.",
  },
  {
    id: "alert-2",
    level: "info" as const,
    message: "Maintenance window scheduled for Pump P3 tomorrow 07:00-09:00.",
  },
];

const ProofDashboard = () => {
  const { data: systemState, isLoading: systemLoading } = useSystemState();
  const state = systemState ?? fallbackState;
  const { data: scheduleData, isLoading: scheduleLoading } =
    useScheduleRecommendation();

  const schedule = scheduleData ?? fallbackSchedule;

  
  
  return (
    <div className="space-y-6">
      <header className="glass-card space-y-3">
        <p className="section-title">Proof of performance</p>
        <h1 className="text-3xl font-semibold text-white">
          Testing & readiness signals
        </h1>
        <p className="text-slate-300">
          Track delivery evidence across documentation, simulations, and QA
          runs. This view doubles as a stakeholder-friendly roll-up that
          highlights progress, risks, and next actions for the AI agent stack.
        </p>
      </header>

      <div>
        <HeroHeader
          state={state}
          schedule={scheduleData ?? schedule}
          alertsCount={alerts.length}
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <ProjectContextPanel />
        <ProjectRoadmap />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <DeliveryChecklist />
        <AlertsBanner alerts={proofAlerts} />
      </div>
    </div>
  );
};

export default ProofDashboard;

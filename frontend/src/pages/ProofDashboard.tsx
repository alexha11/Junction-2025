import ProjectContextPanel from "../components/ProjectContextPanel";
import ProjectRoadmap from "../components/ProjectRoadmap";
import DeliveryChecklist from "../components/DeliveryChecklist";
import AlertsBanner from "../components/AlertsBanner";

const proofAlerts = [
  {
    id: "roadmap",
    level: "info" as const,
    message: "Simulated telemetry replay validated optimization loop latency (< 2 min).",
  },
];

const ProofDashboard = () => (
  <div className="space-y-6">
    <header className="glass-card space-y-3">
      <p className="section-title">Proof of performance</p>
      <h1 className="text-3xl font-semibold text-white">Testing & readiness signals</h1>
      <p className="text-slate-300">
        Track delivery evidence across documentation, simulations, and QA runs. This view doubles as a
        stakeholder-friendly roll-up that highlights progress, risks, and next actions for the AI agent stack.
      </p>
    </header>
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

export default ProofDashboard;

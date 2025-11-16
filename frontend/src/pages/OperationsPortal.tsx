import { useEffect, useRef, useState } from "react";
import AlertsBanner from "../components/AlertsBanner";
import BaselineComparisonPanel from "../components/BaselineComparisonPanel";
import DeliveryChecklist from "../components/DeliveryChecklist";
import ForecastPanel from "../components/ForecastPanel";
import OverridePanel from "../components/OverridePanel";
import ProjectContextPanel from "../components/ProjectContextPanel";
import ProjectRoadmap from "../components/ProjectRoadmap";
import RecommendationPanel from "../components/RecommendationPanel";
import SystemOverviewCard from "../components/SystemOverviewCard";
import TopBar from "../components/TopBar";
import WeatherForecastCard from "../components/weather/WeatherForecastCard";
import WeatherMetricCard from "../components/weather/WeatherMetricCard";
import {
  useSystemForecasts,
  type ForecastSeries,
  type ScheduleRecommendation,
  type SystemState,
} from "../hooks/system";
import { useWeatherForecast } from "../hooks/useWeatherForecast";
import { useDemoSimulator } from "../hooks/useDemoSimulator";
import { playText } from "../../utils/elevenlabs.mjs";

const fallbackState: SystemState = {
  timestamp: new Date().toISOString(),
  tunnel_level_l2_m: 0,
  tunnel_water_volume_l1_m3: 0,
  inflow_m3_s: 0,
  outflow_m3_s: 0,
  electricity_price_eur_cents_kwh: 0,
  pumps: Array.from({ length: 8 }).map((_, index) => ({
    pump_id: `P${index + 1}`,
    state: "standby",
    frequency_hz: 0,
    power_kw: 0,
  })),
};

const fallbackSchedule: ScheduleRecommendation = {
  generated_at: new Date().toISOString(),
  horizon_minutes: 120,
  entries: [],
  justification: "",
};

const fallbackInflowSeries = {
  metric: "Inflow",
  unit: "m³/s",
  points: Array.from({ length: 12 }).map((_, index) => ({
    timestamp: new Date(Date.now() + index * 60 * 60 * 1000).toISOString(),
    value: 0,
  })),
};

const fallbackPriceSeries = {
  metric: "Electricity price",
  unit: "C/kWh",
  points: Array.from({ length: 12 }).map((_, index) => ({
    timestamp: new Date(Date.now() + index * 60 * 60 * 1000).toISOString(),
    value: 0,
  })),
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

const DEFAULT_LOCATION = "Helsinki";

// Transform simulation step to SystemState
function simulationStepToSystemState(step: any): SystemState | null {
  if (!step || step.type !== "simulation_step" || !step.state) return null;
  
  const s = step.state;
  // Get per-pump running hours from metrics
  const perPumpHours = step.metrics?.total_running_time_hours?.per_pump_cumulative || {};
  
  const pumps = (s.pumps || []).map((p: any) => {
    // Determine pump type if not provided
    const pumpType = p.type || (p.pump_id?.endsWith(".1") ? "small" : "big");
    // Get running hours for this pump (handle both "P1.1" and "1.1" formats)
    const pumpKey = p.pump_id?.replace("P", "") || p.pump_id;
    const runningHours = perPumpHours[pumpKey] || perPumpHours[p.pump_id] || 0;
    
    return {
      pump_id: p.pump_id?.startsWith("P") ? p.pump_id : `P${p.pump_id}`,
      state: p.state === "on" ? "running" : "standby",
      frequency_hz: p.frequency_hz || 0,
      power_kw: p.power_kw || 0, // Get from simulation data
      type: pumpType, // "big" or "small" for display
      running_hours: runningHours, // Total running hours for this pump
    };
  });

  // Extract total run hours from metrics if available
  const totalRunHours = step.metrics?.total_running_time_hours?.cumulative || 0;

  // Get L1 level from state (in meters)
  const l1Level = s.l1_m || 0;

  return {
    timestamp: s.timestamp || step.timestamp || new Date().toISOString(),
    tunnel_level_l2_m: 0, // L2 removed - not available in simulation data
    tunnel_water_volume_l1_m3: s.l1_volume_m3 || 0,
    tunnel_level_l1_m: l1Level, // L1 level in meters
    inflow_m3_s: s.inflow_m3_s || 0,
    outflow_m3_s: s.outflow_m3_s || 0,
    electricity_price_eur_cents_kwh: s.price_c_per_kwh || 0,
    pumps,
    total_run_hours: totalRunHours, // Add total run hours
    // Add metrics from simulation step
    violation_count: step.metrics?.violation_count || step.optimization?.l1_violations || 0,
    energy_kwh: step.optimization?.current_step_energy_kwh || step.optimization?.total_energy_kwh || 0,
    cost_eur: step.optimization?.current_step_cost_eur || step.optimization?.total_cost_eur || 0,
    savings: step.optimization?.savings || null,
    // Baseline comparison data
    baseline: step.optimization?.baseline || null,
    optimized: step.optimization?.optimized || null,
    // Calculate specific energy (kWh/m³) if we have energy and outflow
    specific_energy_kwh_m3: (() => {
      const energy = step.optimization?.current_step_energy_kwh || step.optimization?.total_energy_kwh || 0;
      const outflow = s.outflow_m3_s || 0;
      // Calculate for 15-minute step (0.25 hours)
      const outflow_m3 = outflow * 0.25 * 3600; // Convert m³/s to m³ for 15 min
      return outflow_m3 > 0 ? energy / outflow_m3 : 0;
    })(),
  };
}

// Transform simulation step to ScheduleRecommendation
function simulationStepToSchedule(step: any): ScheduleRecommendation | null {
  if (!step || step.type !== "simulation_step" || !step.optimization) return null;
  
  const opt = step.optimization;
  const schedules = opt.schedules || [];
  
  // Group schedules by pump and create entries
  const entries = schedules
    .filter((s: any) => s.is_on && s.time_step === 0) // Current step only
    .map((s: any) => {
      const startTime = new Date(step.timestamp);
      const endTime = new Date(startTime.getTime() + 15 * 60 * 1000); // 15 min interval
      
      return {
        pump_id: s.pump_id?.startsWith("P") ? s.pump_id : `P${s.pump_id}`,
        target_frequency_hz: s.frequency_hz || 0,
        start_time: startTime.toISOString(),
        end_time: endTime.toISOString(),
      };
    });

  // Extract explanation and strategy from step data
  // Explanation can be a string or an object with a 'text' field
  let explanation: string | null = null;
  if (step.explanation) {
    if (typeof step.explanation === 'string') {
      explanation = step.explanation;
    } else if (step.explanation.text) {
      explanation = step.explanation.text;
    } else if (typeof step.explanation === 'object' && step.explanation !== null) {
      // Try to get any string value from the object
      explanation = Object.values(step.explanation).find(v => typeof v === 'string') as string || null;
    }
  }
  if (!explanation && opt.explanation) {
    explanation = typeof opt.explanation === 'string' ? opt.explanation : opt.explanation.text || null;
  }
  if (!explanation) {
    explanation = "Optimized pump schedule based on current conditions.";
  }
  
  // Strategy is typically a string
  const strategy = step.strategy || null;

  return {
    generated_at: step.timestamp || new Date().toISOString(),
    horizon_minutes: 120,
    entries,
    justification: explanation,
    strategy: strategy,
  };
}

// Transform simulation step to ForecastSeries
function simulationStepToForecasts(step: any): ForecastSeries[] | null {
  if (!step || step.type !== "simulation_step" || !step.forecast) return null;
  
  const f = step.forecast;
  const timestamps = f.timestamps || [];
  
  return [
    {
      metric: "Inflow",
      unit: "m³/s",
      points: timestamps.map((ts: string, idx: number) => ({
        timestamp: ts,
        value: f.inflow_m3_s?.[idx] || 0,
      })),
    },
    {
      metric: "Electricity price",
      unit: "C/kWh",
      points: timestamps.map((ts: string, idx: number) => ({
        timestamp: ts,
        value: f.price_c_per_kwh?.[idx] || 0,
      })),
    },
  ];
}

const OperationsPortal = () => {
  // Demo simulator integration
  const { connect, disconnect, isConnected, messages, lastMessage } = useDemoSimulator();
  const [simulationActive, setSimulationActive] = useState(false);
  const welcomeMessagePlayed = useRef(false);
  const lastSpokenExplanation = useRef<string | null>(null);
  const lastSpokenStrategy = useRef<string | null>(null);
  const isPlayingTTS = useRef(false);

  // API hooks - forecasts always come from API endpoint, not simulation
  const { data: forecastSeries } = useSystemForecasts({
    enabled: true, // Always enabled - forecasts are handled by their own endpoint
  });
  const shortTerm = useWeatherForecast({
    hours: 2,
    location: DEFAULT_LOCATION,
    enabled: !simulationActive, // Disable when simulation is active
  });
  const longTerm = useWeatherForecast({
    hours: 24,
    location: DEFAULT_LOCATION,
    enabled: !simulationActive, // Disable when simulation is active
  });

  // Use simulation data if active, otherwise use API data
  // Note: Forecasts always come from API endpoint, not simulation
  // Only update system overview when at least 1 pump is open
  const simulationState = simulationActive && lastMessage?.type === "simulation_step"
    ? simulationStepToSystemState(lastMessage)
    : null;
  const simulationSchedule = simulationActive && lastMessage?.type === "simulation_step"
    ? simulationStepToSchedule(lastMessage)
    : null;

  // Helper function to check if at least one pump is active
  const hasActivePump = (pumps?: SystemState['pumps']) => {
    return pumps?.some(pump => 
      pump.state === "running" || pump.state === "on" || pump.frequency_hz > 0
    ) ?? false;
  };

  // Only use simulation state if at least one pump is active
  const state = (simulationState && hasActivePump(simulationState.pumps)) 
    ? simulationState 
    : fallbackState;
  const schedule = simulationSchedule ?? fallbackSchedule;

  // Forecasts always come from API endpoint, never from simulation
  const inflow = pickSeries(forecastSeries, "inflow") ?? fallbackInflowSeries;
  const price = pickSeries(forecastSeries, "price") ?? fallbackPriceSeries;

  // Handle simulation start/stop
  const handleStartSimulation = () => {
    connect({ speed_multiplier: 1.0 }); // No speed control - process sequentially
    setSimulationActive(true);
  };

  const handleStopSimulation = () => {
    disconnect();
    setSimulationActive(false);
  };

  // Auto-stop simulation when it completes
  useEffect(() => {
    if (lastMessage?.type === "simulation_summary") {
      setSimulationActive(false);
    }
  }, [lastMessage]);

  const currentTemperature =
    shortTerm.data?.[0]?.temperature_c ??
    longTerm.data?.[0]?.temperature_c ??
    0;
  const shortTermPrecip = sumPrecipitation(shortTerm.data);
  const longTermPrecip = sumPrecipitation(longTerm.data);
  const longTermHigh = maxTemperature(longTerm.data);
  const longTermLow = minTemperature(longTerm.data);
  const timeline = (longTerm.data ?? shortTerm.data ?? []).slice(0, 12);

  // Helper function to safely play TTS (prevents overlapping calls)
  const safePlayText = async (text: string, voiceId: string = 'JBFqnCBsd6RMkjVDRZzb') => {
    if (isPlayingTTS.current) {
      console.debug("TTS already playing, skipping:", text.substring(0, 50));
      return;
    }
    
    isPlayingTTS.current = true;
    try {
      console.log("Playing TTS:", text.substring(0, 100));
      await playText(text, voiceId);
    } catch (error) {
      console.error("TTS playback error:", error);
    } finally {
      // Add a small delay before allowing next TTS call
      setTimeout(() => {
        isPlayingTTS.current = false;
      }, 500);
    }
  };

  // Play welcome message only when at least 1 pump is on (only once)
  useEffect(() => {
    if (welcomeMessagePlayed.current) return; // Already played
    
    if (hasActivePump(state?.pumps)) {
      welcomeMessagePlayed.current = true;
      safePlayText('Welcome to the Operations Cockpit. All systems are functioning within normal parameters.');
    }
  }, [state?.pumps]);

  // Speak out explanation when it changes (only if it's not the default fallback)
  // Auto-play when content changes
  useEffect(() => {
    const explanation = schedule?.justification;
    if (!explanation || explanation === "Optimized pump schedule based on current conditions.") {
      return;
    }
    
    // Only speak if this is a new explanation (different from last spoken)
    if (explanation !== lastSpokenExplanation.current) {
      lastSpokenExplanation.current = explanation;
      // Play explanation automatically
      safePlayText(`Explanation: ${explanation}`);
    }
  }, [schedule?.justification]);

  // Speak out strategy when it changes
  // Auto-play when content changes
  useEffect(() => {
    const strategy = schedule?.strategy;
    if (!strategy) {
      return;
    }
    
    // Only speak if this is a new strategy (different from last spoken)
    if (strategy !== lastSpokenStrategy.current) {
      lastSpokenStrategy.current = strategy;
      // Play strategy automatically
      safePlayText(`Strategy: ${strategy}`);
    }
  }, [schedule?.strategy]);

  return (
    <div className="space-y-6">
      <TopBar
        alertsCount={alerts.length}
        scheduleGeneratedAt={schedule.generated_at}
      />

      {/* Simulation Controls */}
      <div className="glass-card space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="section-title">Demo Simulator</p>
            <h2 className="text-2xl font-semibold text-white">Live Simulation Mode</h2>
            <p className="text-sm text-slate-300 mt-1">
              {simulationActive 
                ? `Running simulation (${lastMessage?.type === "simulation_step" ? `Step ${lastMessage.step + 1}/${lastMessage.total_steps}` : "Starting..."})`
                : "Start a simulation to feed live data to the operations dashboard"}
            </p>
          </div>
          <div className={`px-4 py-2 rounded-full text-sm font-medium ${
            isConnected ? "bg-green-500/20 text-green-400" : "bg-slate-600/20 text-slate-400"
          }`}>
            {isConnected ? "🟢 Connected" : "⚪ Disconnected"}
          </div>
        </div>

        <div className="flex items-center gap-4">
          {!isConnected ? (
            <button
              onClick={handleStartSimulation}
              className="px-6 py-2 rounded-lg bg-green-500 hover:bg-green-600 text-white font-medium transition"
            >
              Start Simulation
            </button>
          ) : (
            <button
              onClick={handleStopSimulation}
              className="px-6 py-2 rounded-lg bg-red-500 hover:bg-red-600 text-white font-medium transition"
            >
              Stop Simulation
            </button>
          )}

          {simulationActive && lastMessage?.type === "simulation_step" && (
            <div className="text-sm text-slate-300">
              <span className="text-slate-400">Progress:</span>{" "}
              <span className="font-semibold text-white">
                {lastMessage.step + 1} / {lastMessage.total_steps}
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <SystemOverviewCard state={state} loading={false} />
          <BaselineComparisonPanel state={state} loading={false} />
          <ForecastPanel inflow={inflow} prices={price} />
        </div>
        <div className="space-y-6">
          <RecommendationPanel schedule={schedule} loading={false} />
          <AlertsBanner alerts={alerts} />
          <OverridePanel />
          <DeliveryChecklist />
        </div>
      </div>

      <section className="space-y-4">
        <div className="glass-card flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="section-title">Weather intelligence</p>
            <h2 className="text-2xl font-semibold text-white">
              Agent-sourced precipitation outlook (2h · 24h)
            </h2>
          </div>
          <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">
            Location · {DEFAULT_LOCATION}
          </span>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <WeatherMetricCard
            label="Current temperature"
            value={`${currentTemperature.toFixed(1)}°C`}
            description="Latest reading from the weather agent"
            trend="flat"
          />
          <WeatherMetricCard
            label="Precipitation · 2h"
            value={`${shortTermPrecip.toFixed(1)} mm`}
            description="Short-term accumulation"
            trend={shortTermPrecip > 0.4 ? "up" : "flat"}
          />
          <WeatherMetricCard
            label="Precipitation · 24h"
            value={`${longTermPrecip.toFixed(1)} mm`}
            description="Day-long accumulation"
            trend={longTermPrecip > shortTermPrecip ? "up" : "down"}
          />
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <WeatherForecastCard
            title="Short-term focus"
            subtitle="Next 2 hours"
            data={shortTerm.data}
            loading={shortTerm.isLoading}
            horizonLabel="Auto refresh via MCP"
          />
          <WeatherForecastCard
            title="Daily outlook"
            subtitle="Next 24 hours"
            data={longTerm.data}
            loading={longTerm.isLoading}
            horizonLabel="Aligned with optimization horizon"
          />
        </div>
        <div className="glass-card">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="section-title">Hourly detail</p>
              <h3 className="text-xl font-semibold text-white">
                First 12 normalized points
              </h3>
            </div>
            <p className="text-sm text-slate-400">
              {timeline.length} hrs ·{" "}
              {longTermLow !== undefined && longTermHigh !== undefined
                ? `${longTermLow.toFixed(1)}°C – ${longTermHigh.toFixed(1)}°C`
                : "Waiting for feed"}
            </p>
          </div>
          <div className="mt-4 max-h-[320px] overflow-auto rounded-3xl border border-white/5 scroll-glow">
            <table className="w-full text-sm text-slate-300">
              <thead className="bg-white/5 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-3 text-left">Timestamp</th>
                  <th className="px-4 py-3 text-left">Temperature</th>
                  <th className="px-4 py-3 text-left">Precipitation</th>
                </tr>
              </thead>
              <tbody>
                {timeline.map((point) => (
                  <tr
                    key={point.timestamp}
                    className="border-t border-white/5 hover:bg-white/5"
                  >
                    <td className="px-4 py-2">
                      {new Date(point.timestamp).toLocaleString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                        month: "short",
                        day: "2-digit",
                      })}
                    </td>
                    <td className="px-4 py-2">
                      {point.temperature_c.toFixed(1)} °C
                    </td>
                    <td className="px-4 py-2">
                      {point.precipitation_mm.toFixed(2)} mm
                    </td>
                  </tr>
                ))}
                {timeline.length === 0 && (
                  <tr>
                    <td
                      colSpan={3}
                      className="px-4 py-6 text-center text-slate-400"
                    >
                      Weather agent still loading...
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
      <div className="grid gap-6 lg:grid-cols-2">
        <ProjectContextPanel />
        <ProjectRoadmap />
      </div>
    </div>
  );
};

function sumPrecipitation(points?: { precipitation_mm: number }[]) {
  if (!points || points.length === 0) return 0;
  return points.reduce((sum, point) => sum + point.precipitation_mm, 0);
}

function pickSeries(series: ForecastSeries[] | undefined, metric: string) {
  if (!series) return undefined;
  const match = series.find(
    (item) => item.metric.toLowerCase() === metric.toLowerCase()
  );
  if (!match) return undefined;
  return {
    metric: match.metric,
    unit: match.unit,
    points: match.points.map((point) => ({
      timestamp: point.timestamp,
      value: point.value,
    })),
  };
}

function maxTemperature(points?: { temperature_c: number }[]) {
  if (!points || points.length === 0) return undefined;
  return Math.max(...points.map((point) => point.temperature_c));
}

function minTemperature(points?: { temperature_c: number }[]) {
  if (!points || points.length === 0) return undefined;
  return Math.min(...points.map((point) => point.temperature_c));
}

export default OperationsPortal;

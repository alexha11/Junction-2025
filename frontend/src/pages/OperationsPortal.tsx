import { useEffect } from "react";
import AlertsBanner from "../components/AlertsBanner";
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
	useScheduleRecommendation,
	useSystemForecasts,
	useSystemState,
	type ForecastSeries,
	type ScheduleRecommendation,
	type SystemState,
} from "../hooks/system";
import { useWeatherForecast } from "../hooks/useWeatherForecast";
import { playText } from "../../utils/elevenlabs.mjs";

const fallbackState: SystemState = {
	timestamp: new Date().toISOString(),
	tunnel_level_l2_m: 3.15,
	tunnel_water_volume_l1_m3: 12500,
	inflow_m3_s: 2.3,
	outflow_m3_s: 2.1,
	electricity_price_eur_cents_kwh: 8.0,
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

const fallbackInflowSeries = {
	metric: "Inflow",
	unit: "m³/s",
	points: Array.from({ length: 12 }).map((_, index) => ({
		timestamp: new Date(Date.now() + index * 60 * 60 * 1000).toISOString(),
		value: 2 + index * 0.1,
	})),
};

const fallbackPriceSeries = {
	metric: "Electricity price",
	unit: "C/kWh",
	points: Array.from({ length: 12 }).map((_, index) => ({
		timestamp: new Date(Date.now() + index * 60 * 60 * 1000).toISOString(),
		value: 65 + index * 2,
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
		message:
			"Maintenance window scheduled for Pump P3 tomorrow 07:00-09:00.",
	},
];

const DEFAULT_LOCATION = "Helsinki";

const OperationsPortal = () => {
	const { data: systemState, isLoading: systemLoading } = useSystemState();
	const { data: forecastSeries } = useSystemForecasts();
	const { data: scheduleData, isLoading: scheduleLoading } =
		useScheduleRecommendation();
	const shortTerm = useWeatherForecast({
		hours: 2,
		location: DEFAULT_LOCATION,
	});
	const longTerm = useWeatherForecast({
		hours: 24,
		location: DEFAULT_LOCATION,
	});

	const state = systemState ?? fallbackState;
	const schedule = scheduleData ?? fallbackSchedule;

	const inflow = pickSeries(forecastSeries, "inflow") ?? fallbackInflowSeries;
	const price = pickSeries(forecastSeries, "price") ?? fallbackPriceSeries;

	const currentTemperature =
		shortTerm.data?.[0]?.temperature_c ??
		longTerm.data?.[0]?.temperature_c ??
		0;
	const shortTermPrecip = sumPrecipitation(shortTerm.data);
	const longTermPrecip = sumPrecipitation(longTerm.data);
	const longTermHigh = maxTemperature(longTerm.data);
	const longTermLow = minTemperature(longTerm.data);
	const timeline = (longTerm.data ?? shortTerm.data ?? []).slice(0, 12);

	useEffect(() => {
		playText('Welcome to the Operations Cockpit. All systems are functioning within normal parameters.', 'JBFqnCBsd6RMkjVDRZzb');
	}	
, []);

	return (
		<div className="space-y-6">
			<TopBar
				alertsCount={alerts.length}
				scheduleGeneratedAt={
					scheduleData?.generated_at ?? schedule.generated_at
				}
			/>

			<div className="grid gap-6 lg:grid-cols-3">
				<div className="lg:col-span-2 space-y-6">
					<SystemOverviewCard state={state} loading={systemLoading} />
					<ForecastPanel inflow={inflow} prices={price} />
					<RecommendationPanel
						schedule={scheduleData ?? schedule}
						loading={scheduleLoading}
					/>
				</div>
				<div className="space-y-6">
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
							{longTermLow !== undefined &&
							longTermHigh !== undefined
								? `${longTermLow.toFixed(
										1
								  )}°C – ${longTermHigh.toFixed(1)}°C`
								: "Waiting for feed"}
						</p>
					</div>
					<div className="mt-4 max-h-[320px] overflow-auto rounded-3xl border border-white/5 scroll-glow">
						<table className="w-full text-sm text-slate-300">
							<thead className="bg-white/5 text-xs uppercase tracking-wide text-slate-400">
								<tr>
									<th className="px-4 py-3 text-left">
										Timestamp
									</th>
									<th className="px-4 py-3 text-left">
										Temperature
									</th>
									<th className="px-4 py-3 text-left">
										Precipitation
									</th>
								</tr>
							</thead>
							<tbody>
								{timeline.map((point) => (
									<tr
										key={point.timestamp}
										className="border-t border-white/5 hover:bg-white/5"
									>
										<td className="px-4 py-2">
											{new Date(
												point.timestamp
											).toLocaleString([], {
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
											{point.precipitation_mm.toFixed(2)}{" "}
											mm
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

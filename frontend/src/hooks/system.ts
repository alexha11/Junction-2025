import { useQuery } from "@tanstack/react-query";

export interface PumpStatus {
	pump_id: string;
	state: string;
	frequency_hz: number;
	power_kw: number;
	running_hours?: number; // Total running hours for this pump (from simulation)
}

export interface SystemState {
	timestamp: string;
	tunnel_level_l2_m: number;
	tunnel_level_l1_m?: number; // L1 level in meters (from simulation)
	tunnel_water_volume_l1_m3: number;
	inflow_m3_s: number;
	outflow_m3_s: number;
	electricity_price_eur_cents_kwh: number;
	pumps: PumpStatus[];
	total_run_hours?: number; // Total cumulative run hours for all pumps (from simulation)
	violation_count?: number; // Number of L1 constraint violations (from simulation)
	energy_kwh?: number; // Energy consumption in kWh (from simulation)
	cost_eur?: number; // Cost in EUR (from simulation)
	savings?: { // Savings compared to baseline (from simulation)
		cost_eur?: number;
		cost_percent?: number;
		energy_kwh?: number;
		energy_percent?: number;
	};
	baseline?: { // Baseline metrics (from simulation)
		cost_eur?: number;
		energy_kwh?: number;
		outflow_variance?: number;
	};
	optimized?: { // Optimized metrics (from simulation)
		cost_eur?: number;
		energy_kwh?: number;
		outflow_variance?: number;
	};
	specific_energy_kwh_m3?: number; // Specific energy in kWh/m³ (from simulation)
}

export interface ForecastPoint {
	timestamp: string;
	value: number;
}

export interface ForecastSeries {
	metric: string;
	unit: string;
	points: ForecastPoint[];
}

export interface ScheduleEntry {
	pump_id: string;
	target_frequency_hz: number;
	start_time: string;
	end_time: string;
}

export interface ScheduleRecommendation {
	generated_at: string;
	horizon_minutes: number;
	entries: ScheduleEntry[];
	justification: string;
	strategy?: string; // Optional strategy from simulation
}

const fetchJSON = async <T>(url: string): Promise<T> => {
	const response = await fetch(url);
	if (!response.ok) {
		throw new Error(
			`Request to ${url} failed with status ${response.status}`
		);
	}
	return response.json() as Promise<T>;
};

export const useSystemState = (options?: { enabled?: boolean }) =>
	useQuery<SystemState>({
		queryKey: ["system-state"],
		queryFn: () => fetchJSON<SystemState>("https://hsy-backend-524386263600.europe-west1.run.app/system/state"),
		refetchInterval: 30_000,
		enabled: options?.enabled !== false,
	});

export const useSystemForecasts = (options?: { enabled?: boolean }) =>
	useQuery<ForecastSeries[]>({
		queryKey: ["system-forecasts"],
		queryFn: () => fetchJSON<ForecastSeries[]>("https://hsy-backend-524386263600.europe-west1.run.app/system/forecasts"),
		staleTime: 60_000,
		enabled: options?.enabled !== false,
	});

export const useScheduleRecommendation = (options?: { enabled?: boolean }) =>
	useQuery<ScheduleRecommendation>({
		queryKey: ["system-schedule"],
		queryFn: () =>
			fetchJSON<ScheduleRecommendation>("https://hsy-backend-524386263600.europe-west1.run.app/system/schedule"),
		refetchInterval: 60_000,
		enabled: options?.enabled !== false,
	});

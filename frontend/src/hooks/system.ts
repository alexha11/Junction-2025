import { useQuery } from "@tanstack/react-query";

export interface PumpStatus {
  pump_id: string;
  state: string;
  frequency_hz: number;
  power_kw: number;
}

export interface SystemState {
  timestamp: string;
  tunnel_level_m: number;
  inflow_m3_s: number;
  outflow_m3_s: number;
  electricity_price_eur_mwh: number;
  pumps: PumpStatus[];
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
}

const fetchJSON = async <T>(url: string): Promise<T> => {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request to ${url} failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
};

export const useSystemState = () =>
  useQuery<SystemState>({
    queryKey: ["system-state"],
    queryFn: () => fetchJSON<SystemState>("/api/system/state"),
    refetchInterval: 30_000,
  });

export const useSystemForecasts = () =>
  useQuery<ForecastSeries[]>({
    queryKey: ["system-forecasts"],
    queryFn: () => fetchJSON<ForecastSeries[]>("/api/system/forecasts"),
    staleTime: 60_000,
  });

export const useScheduleRecommendation = () =>
  useQuery<ScheduleRecommendation>({
    queryKey: ["system-schedule"],
    queryFn: () => fetchJSON<ScheduleRecommendation>("/api/system/schedule"),
    refetchInterval: 60_000,
  });

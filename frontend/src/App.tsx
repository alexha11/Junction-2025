import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import AlertsBanner from "./components/AlertsBanner";
import ForecastPanel from "./components/ForecastPanel";
import OverridePanel from "./components/OverridePanel";
import RecommendationPanel from "./components/RecommendationPanel";
import SystemOverviewCard from "./components/SystemOverviewCard";

const api = axios.create({ baseURL: "/api" });

const useSystemState = () =>
  useQuery({
    queryKey: ["system-state"],
    queryFn: async () => (await api.get("/system/state")).data,
    refetchInterval: 15_000,
  });

const useForecasts = () =>
  useQuery({
    queryKey: ["forecasts"],
    queryFn: async () => (await api.get("/system/forecasts")).data,
    refetchInterval: 60_000,
  });

const useSchedule = () =>
  useQuery({
    queryKey: ["schedule"],
    queryFn: async () => (await api.get("/system/schedule")).data,
    refetchInterval: 60_000,
  });

const useAlerts = () =>
  useQuery({
    queryKey: ["alerts"],
    queryFn: async () => (await api.get("/alerts")).data,
    refetchInterval: 30_000,
  });

function App() {
  const { data: systemState, isLoading: stateLoading } = useSystemState();
  const { data: forecasts } = useForecasts();
  const { data: schedule } = useSchedule();
  const { data: alerts } = useAlerts();

  const inflowSeries = useMemo(
    () => forecasts?.find((series: any) => series.metric === "inflow"),
    [forecasts]
  );
  const priceSeries = useMemo(
    () => forecasts?.find((series: any) => series.metric === "price"),
    [forecasts]
  );

  return (
    <div className="dashboard">
      <AlertsBanner alerts={alerts ?? []} />
      <SystemOverviewCard state={systemState} loading={stateLoading} />
      <ForecastPanel inflow={inflowSeries} prices={priceSeries} />
      <RecommendationPanel schedule={schedule} />
      <OverridePanel schedule={schedule} />
    </div>
  );
}

export default App;

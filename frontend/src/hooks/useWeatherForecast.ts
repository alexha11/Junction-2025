import { useQuery } from "@tanstack/react-query";

export type WeatherPoint = {
  timestamp: string;
  precipitation_mm: number;
  temperature_c: number;
};

interface Params {
  hours: number;
  location: string;
  enabled?: boolean;
}

const FALLBACK_LOCATION = "Helsinki";
const WEATHER_AGENT_URL = "https://hsy-backend-524386263600.europe-west1.run.app/weather/forecast";

const resolveUrl = (target: string) => {
  if (target.startsWith("http")) {
    return target;
  }
  if (typeof window === "undefined") {
    return target;
  }
  return `${window.location.origin}${target}`;
};

const isOpenWeatherEndpoint = (url: string) =>
  url.includes("api.openweathermap.org");

async function requestWeatherForecast(params: Params): Promise<WeatherPoint[]> {
  const resolvedUrl = resolveUrl(WEATHER_AGENT_URL);

  try {
    if (isOpenWeatherEndpoint(resolvedUrl)) {
      return await fetchFromOpenWeather(resolvedUrl, params);
    }
    return await fetchFromAgent(resolvedUrl, params);
  } catch (error) {
    console.warn(
      "Falling back to synthetic weather series because the weather agent is unreachable:",
      error
    );
    return generateMockForecast(params.hours);
  }
}

async function fetchFromAgent(
  url: string,
  params: Params
): Promise<WeatherPoint[]> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      lookahead_hours: params.hours,
      location: params.location || FALLBACK_LOCATION,
    }),
  });

  if (!response.ok) {
    throw new Error(`Weather agent responded with status ${response.status}`);
  }

  const data = (await response.json()) as WeatherPoint[];
  return data;
}

// Mirrors the OpenWeather current-weather contract so the UI stays aligned with
// https://openweathermap.org/guide even when bypassing our backend agent.
async function fetchFromOpenWeather(
  url: string,
  params: Params
): Promise<WeatherPoint[]> {
  const urlObject = new URL(url);
  const location = params.location || FALLBACK_LOCATION;
  urlObject.searchParams.set("q", location);

  const response = await fetch(urlObject.toString());
  if (!response.ok) {
    throw new Error(`OpenWeather responded with status ${response.status}`);
  }

  const payload = await response.json();
  const timestampMs = payload.dt ? payload.dt * 1000 : Date.now();
  const temperature =
    typeof payload.main?.temp === "number" ? payload.main.temp : 0;
  const precipitation =
    Number(payload.rain?.["1h"] ?? 0) + Number(payload.snow?.["1h"] ?? 0);

  return Array.from({ length: params.hours }).map((_, index) => ({
    timestamp: new Date(timestampMs + index * 60 * 60 * 1000).toISOString(),
    temperature_c: temperature,
    precipitation_mm: precipitation,
  }));
}

function generateMockForecast(hours: number): WeatherPoint[] {
  const now = Date.now();
  return Array.from({ length: hours }).map((_, index) => ({
    timestamp: new Date(now + index * 60 * 60 * 1000).toISOString(),
    temperature_c: 3 + Math.sin(index / 3) * 2.5,
    precipitation_mm: Math.max(0, Math.sin(index / 2 + 1)) * 0.3,
  }));
}

export const useWeatherForecast = (params: Params) =>
  useQuery<WeatherPoint[]>({
    queryKey: ["weather-forecast", params.location, params.hours],
    queryFn: () => requestWeatherForecast(params),
    staleTime: 1000 * 60 * 5,
    enabled: params.enabled !== false,
  });

# Frontend Reference

This document explains every file in `frontend/`, how the pieces fit together, and what to modify when you extend the operator dashboard.

## Top-Level Files

| File                          | Purpose                                                                                                                                                                                    |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `frontend/index.html`         | Minimal Vite HTML shell that mounts the React app into the `#root` div and loads `src/main.tsx` as the entry module.                                                                       |
| `frontend/package.json`       | Declares runtime dependencies (React 18, React Query, Axios, Zustand, Recharts) plus dev tooling (Vite, TypeScript, Tailwind, ESLint). Scripts: `dev`, `build`, `preview`, `lint`.         |
| `frontend/postcss.config.js`  | Wires Tailwind and Autoprefixer into Vite's CSS build pipeline.                                                                                                                            |
| `frontend/tailwind.config.js` | Tailwind theme extension: Inter font stack, `brand.*` colors, reusable `card` shadow, and `mesh` background gradient. Content paths cover `index.html` and all `src/**/*.{ts,tsx,js,jsx}`. |
| `frontend/tsconfig.node.json` | Base TypeScript compiler options for the tooling layer (ES2020 target, strict mode, bundler-style module resolution). Only includes `vite.config.ts`.                                      |
| `frontend/tsconfig.json`      | Extends the node config for application code, enabling `react-jsx`, registering the `vite/client` types, and setting `baseUrl` to `src` for absolute imports.                              |
| `frontend/vite.config.ts`     | Boots the React plugin and sets up a dev-server proxy so `/api/*` calls are forwarded to `http://localhost:8000` (FastAPI) with the `/api` prefix stripped.                                |

## `src/` Entry Points

| File                      | Purpose                                                                                                                                                                                                                           |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/main.tsx`   | React bootstrap: creates a `QueryClient`, wraps `<App />` with `QueryClientProvider`, enforces `React.StrictMode`, and hydrates the `#root` element. This is where you would add global providers (theme, Zustand context, etc.). |
| `frontend/src/App.tsx`    | Top-level router with two routes (`/` → `OperationsPortal`, `/proof` → `ProofDashboard`). Navigation pills highlight the active view.                                                                                             |
| `frontend/src/styles.css` | Tailwind entry file. Adds global background gradients, ensures `body/#root` span the viewport, and defines the reusable `.glass-card` container and `.section-title` helper classes.                                              |

## Components (`src/components/`)

Each component is presentational and expects data from future hooks or props. They all share Tailwind utility styling plus the `.glass-card` helper.

| Component                 | Description                                                                                                                                                           |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AlertsBanner.tsx`        | Renders a badge-styled list of active alerts. Accepts an `alerts` array with `level` (`info`, `warning`, `critical`) and message; hides itself if the array is empty. |
| `DeliveryChecklist.tsx`   | Static checklist highlighting telemetry, scheduler cadence, and override logging states. Mirrors the manual/automated coverage split from `docs/testing.md`.          |
| `ForecastPanel.tsx`       | Dual Recharts line charts (inflow + electricity price). Shows loading placeholders when the `Series` props are undefined.                                             |
| `HeroHeader.tsx`          | Hero block summarizing tunnel telemetry, power price, and AI schedule metadata. Computes derived values (active pumps, last plan window) and shows mission blurbs.    |
| `OverridePanel.tsx`       | Manual override form with optimistic confirmation toast. Currently keeps state locally and contains a TODO to POST the justification to the backend.                  |
| `ProjectContextPanel.tsx` | Summarizes PRD/testing highlights: mission priorities, architecture stack, KPIs, and quick links back to the docs.                                                    |
| `ProjectRoadmap.tsx`      | Three-phase delivery roadmap (Now/Next/Later) tied to owners and checklists matching the testing plan. Useful for stakeholder communication.                          |
| `RecommendationPanel.tsx` | Displays the AI-generated pump schedule (frequency + window) and an optional textual justification. Shows an empty-state placeholder if no plan exists.               |
| `SystemOverviewCard.tsx`  | Main telemetry table: tunnel level, inflow/outflow, price cards, and a pump table with Hz/kW readings. Handles a `loading` flag to show a skeleton.                   |
| `TopBar.tsx`              | High-level navigation header with badge links to PRD/testing/backends. Shows alert count and timestamp of the last AI update derived from props.                      |

## Other Source Folders

| Path                               | Status & Intended Use                                                                                                                                                             |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/pages/`              | Houses routed layouts. `OperationsPortal` now embeds the weather agent's short (2h) and long (24h) panels alongside telemetry, and `ProofDashboard` summarizes delivery evidence. |
| `frontend/src/data/`               | **Empty placeholder.** Use for mock JSON, fixtures, or typed API response mappers when wiring data sources.                                                                       |
| `frontend/src/hooks/`              | Contains API hooks. `useWeatherForecast` calls the weather agent endpoint provided via `VITE_WEATHER_AGENT_URL`, falling back to synthetic data when the agent is offline.        |
| `frontend/src/components/weather/` | Shared widgets for the weather dashboard (`WeatherMetricCard`, `WeatherForecastCard`).                                                                                            |

## Data Flow Expectations

- **Data fetching**: React Query is configured globally. `useWeatherForecast` is the first hook (calls `/api/weather/forecast` by default); mimic this pattern for system state, schedules, etc.
- **State management**: `zustand` is listed as a dependency but unused. Introduce a store (e.g., `src/state/systemStore.ts`) to share telemetry/pump info between components if React Query caching is insufficient.
- **Weather agent exposure**: Set `VITE_WEATHER_AGENT_URL` to any reachable endpoint (e.g., FastAPI proxy to the Python agent or a direct OpenWeather URL that already embeds the API key). The React Query hook posts `{lookahead_hours, location}` to that endpoint; extend FastAPI with `/weather/forecast` to satisfy this contract.

## Extending the Frontend

1. Add additional routed views (or expand `OperationsPortal`) by composing the existing components with new data hooks.
2. Implement more API hooks (`useSystemState`, `useForecastSeries`, etc.) under `src/hooks/` following the `useWeatherForecast` pattern.
3. Replace static arrays inside components (e.g., `DeliveryChecklist`, `ProjectRoadmap`) with props or backend data once endpoints are live.
4. Update `package.json` scripts/tests (`npm run test`) once Vitest is configured, aligning with `docs/testing.md` recommendations.

With the above map, you can navigate every file inside `frontend/`, know what it renders, and identify the TODOs required to make the dashboard fully functional.

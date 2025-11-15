# Optimizer Agent Plan (MPC + OR-Tools)

High-level guidelines and phases for building the optimization agent. No code, just structure and ideas.

---

## Goal

Design an **MPC-style optimizer agent** for the Blominmäki hackathon that:
- Minimizes **total pumping energy/cost** over the horizon using the provided data (per-pump flow, power, electricity price)
- Keeps tunnel water level **L1 within its min/max bounds**, accounting for the large tunnel volume and delay
- Produces a **smooth, near-constant outflow F2** to the WWTP
- Respects operational rules from the brief (limited start/stop, daily/2‑day flushing, balanced pump running hours)
- Is explainable and simple enough to tune quickly during the hackathon.

---

## Core Ideas

- Treat the optimizer as a **control loop** that runs every 15 minutes (MPC / receding horizon).
- Implement it as part of a **multi-agent system** (forecasters, planner, supervisor/executor, OPC UA connector) consistent with the Junction Platform Light architecture.
- Separate **long-term strategy** (24h view) from **short-term actions** (2h view).
- Express pump scheduling as a **constrained optimization problem** solved by OR-Tools (similar in spirit to literature on techno‑economic dispatch for pumping + PV).
- Optimize not just total kWh, but also **specific energy (kWh/m³)** and time spent inside each pump’s **preferred operating range (POR)** on the pump curves (high efficiency, low cavitation risk).
- Keep a clear distinction between:
  - _What the system must never do_ (hard constraints)
  - _What we prefer_ (soft constraints, cost, specific energy).

---

## LLM Choice and Role (Featherless.ai)

- Use a **general-purpose instruct model** hosted on Featherless, e.g. **Llama‑3.x‑8B‑Instruct** (or a similar ≤15B instruct model) as the shared LLM for the system.
- Primary roles for the LLM:
  - Turn structured optimization outputs into **clear operator explanations** and hackathon‑ready narratives.
  - Help draft **scenario summaries and comparisons** (baseline vs optimized) using metrics you compute.
  - Optionally support **lightweight reasoning** around strategy selection (e.g., describing why certain horizons/weights are chosen), while the actual optimization remains in OR‑Tools.
- Non‑roles for the LLM (keep this explicit in implementation):
  - It does **not** directly control pumps or enforce safety constraints.
  - It is **not** the primary optimizer; it augments an MPC/OR‑Tools core with explainability and presentation.

---

## Phases

### Phase 1 – Understand and Frame the Problem

- Clarify exactly what the optimizer controls: which pumps (e.g. 4 of capacity *x* and 1 of capacity *y*), what variables (on/off, frequency or discrete speeds), and the chosen time resolution (e.g. 15 or 60 minutes).
- Map the **hackathon dataset** to these variables (without assuming a fixed schema):
  - Inspect the current `Hackathon_HSY_data` sheets and document which columns correspond to F1, L1, per‑pump flows, per‑pump power, electricity price, timestamps, etc.
  - Treat this mapping as configuration (e.g. a small YAML/JSON or constants module) so you can easily adapt if the file structure changes again.
  - Static info: pump capacities, elevations/topography, discharge level L2
- Decide how forecasts are obtained for the optimizer:
  - Directly from the dataset (persistence / simple forecasting), and/or
  - Via lightweight stub agents that wrap these forecasts for later extensibility.
- Define outputs in a stable schema: a time‑ordered list of pump setpoints (per time slot) plus summary metrics (energy, cost, L1 min/max, flushing events).
- Explicitly list constraints and priorities from the brief:
  - Safety: L1 range, pumps never all off, limited start/stop frequency
  - Energy & efficiency: minimize kWh and kWh/m³, operate near efficient points
  - Smoothness: F2 as constant as possible, periodic tunnel flushing.

### Phase 2 – Design the Multi-Agent Control Architecture (Junction Platform Light)

- Map your solution onto the Junction Platform Light diagram:
  - **OPC UA / Digital Twin layer:** simulator or future real plant, exposing time-series tags.
  - **MCP↔OPC UA bridge agent:** a thin agent that reads/writes OPC UA tags and exposes them as MCP tools.
  - **Solution AI agents:**
    - Forecaster(s) for inflow, price, and/or process behaviour
    - Planner/MPC optimizer (this agent) that proposes schedules
    - Supervisor/executor that checks constraints, applies plans, and triggers fallbacks.
- Decide the **control horizon** and **time step** (e.g., 2h horizon, 15‑min steps → 8 steps) and make sure they match price granularity and available data.
- Decide the **re-optimization cadence** (e.g., run every 15 minutes) so the planner behaves like a receding-horizon MPC inside the multi-agent loop.
- Define the high-level cycle for the planner agent:
  1. Read current state via the status/OPC UA agent
  2. Pull fresh forecasts (2h + 24h) from forecaster agents or simple models
  3. Compute a plan over the horizon
  4. Hand the recommended schedule to the supervisor/executor
  5. Repeat next cycle with updated information.
- Agree how the backend / digital-twin harness will call this planner (tool contract, inputs/outputs) so it is easy to swap between offline simulation and real OPC UA.

### Phase 3 – Define the Optimization Problem Conceptually

- Identify **decision variables**:
  - For each time step and pump: on/off, chosen speed / frequency band.
- Define **hard constraints** conceptually, aligned with the challenge:
  - L1 must stay within its specified [L1min, L1max] at all steps.
  - At least one pump is always running (no full stop of the station).
  - When a pump is running, its frequency must be **≥ 47.8 Hz** (about 95%) except for brief ramp‑up/down periods that you do not schedule explicitly.
  - Pumps must not start and stop too frequently (minimum on/off durations).
  - Tunnel bottom must be flushed to (or near) L1min **once every day during dry‑weather periods** (identify low‑inflow windows and ensure at least one flush event per day falls into such a window).
- Define **soft preferences / objectives**:
  - Minimize total energy / cost over the horizon (kWh and optionally kWh × price), in line with prior work on optimal pump dispatch.
  - Minimize **specific energy** (kWh/m³) and time spent outside the preferred operating range on the pump curves.
  - Keep outflow F2 as smooth and near‑constant as possible.
  - Encourage operation near efficient pump points (good kWh/m³) and avoid operating regimes associated with cavitation or harmful transients.
- Decide whether to use:
  - A **single combined objective** (weighted sum of cost, smoothness, etc.), or
  - A **two-stage approach** (feasibility and safety first, then cost/smoothness optimization within the feasible set).

### Phase 4 – Dual-Horizon Strategy (24h + 2h)

- Use **24h forecasts** to derive a simple **strategic plan**:
  - Mark hours as: CHEAP, EXPENSIVE, SURGE_RISK, NORMAL.
  - Derive qualitative strategies: PUMP_AGGRESSIVE, PUMP_MINIMAL, MAINTAIN_BUFFER, BALANCED.
- Use **2h forecasts** for **tactical optimization**:
  - During CHEAP + safe-L1: allow higher pumping to exploit low prices.
  - Before SURGE_RISK: create extra buffer (lower L1 proactively).
  - During EXPENSIVE periods: minimize pumping as long as safety allows.
- The 24h layer doesn’t need to be exact — it just sets **guidance and guardrails** for the 2h optimizer.

### Phase 5 – Adaptive Trade-off Between Cost and Safety

- Define a **risk measure** based on how close L1 is to its bounds and expected inflow in the near future.
- Translate risk level into **weights** in the objective:
  - High risk → emphasize safety, accept higher cost.
  - Low risk → emphasize cost, still respect hard constraints.
- Optionally, include price “opportunity”:
  - If prices are unusually low now vs the horizon, bias towards pumping more now.
- The key idea: **the same optimizer** can behave differently depending on context, without changing constraints.

### Phase 6 – Data Flow and Interfaces Between Agents / Simulation

- For the hackathon, treat the **CSV/Excel dataset + Python simulator** as the primary data source, optionally wrapped behind simple agents.
- Define how the optimizer obtains its inputs:
  - Current state (L1, F1, F2, pump states) from the simulator / status logic
  - Price series from the dataset or a price agent
  - Optional inflow or weather forecasts if you decide to use them.
- Ensure:
  - All time series are aligned on the chosen optimization grid (e.g. 15‑ or 60‑minute steps).
  - Units and timestamps are consistent with the simulation model.
- Clarify error-handling and robustness strategies:
  - What happens if some data is missing or unreliable in the dataset?
  - When the optimizer should fall back to a simpler, rule‑based schedule for safety.

### Phase 7 – Safety Nets and Fallback Strategies

- Define at least three levels of behavior:
  1. **Full optimization**: MPC + OR-Tools with all constraints.
  2. **Simplified optimization**: reduced model if full solve fails or times out.
  3. **Rule-based safe mode**: conservative schedule that guarantees safety using simple rules.
- Decide clear rules for switching to fallback modes (e.g., solver timeout, infeasibility, missing data).
- Always prioritize **no constraint violations** over cost.

### Phase 8 – Explainability and Operator Trust

- For each generated schedule, capture:
  - Key drivers: “Prices low between X–Y”, “High inflow expected at Z”, “L1 close to upper bound”.
  - High-level strategy: “Pumping aggressively now to avoid expensive hours later”.
- Define a compact explanation format that can be shown in the frontend.
- Use the chosen **Featherless LLM** (e.g. Llama‑3.x‑8B‑Instruct) to:
  - Rephrase structured reasons and metrics into clear, concise natural language for operators and judges.
  - Generate short scenario narratives (what happened, why this schedule is better than baseline) based only on safe, pre‑computed numbers.
- Keep a clear separation: the LLM never bypasses safety/optimization logic; it only explains and packages results.

### Phase 9 – Validation & Iterative Refinement

- Use the **provided 14‑day / 1‑month datasets** to run offline simulations end‑to‑end.
- Design scenarios that reflect the brief:
  - Typical days with morning/evening peaks and low night consumption
  - Storm/rain events causing rapid inflow increases
  - Periods where L1 is close to its bounds.
- For each run, evaluate:
  - L1 trajectory: always within bounds, with flush events at the required frequency.
  - F2: reasonably smooth and close to constant on average.
  - Pump usage: similar working hours per pump, no excessive cycling.
  - Energy and **specific energy (kWh/m³)**: improvement vs a simple, constraint‑respecting baseline strategy.
  - (If you include any PV or tariff logic) self‑consumption %, imported vs exported energy, and €/m³ as in techno‑economic dispatch studies.
- Iterate on:
  - Constraint formulations that are too tight/loose for the data.
  - Weighting between cost, smoothness, and flushing.
  - Any heuristics you add for edge cases.

### Phase 10 – Integration and Evolution

- Integrate the optimizer agent into the existing backend and the Junction Platform Light vision:
  - Treat the Python simulator as an initial **digital twin** behind an OPC UA-style interface.
  - Keep planner inputs/outputs compatible with OPC UA tags so the same logic can later control a real plant.
  - Ensure the frontend can display the schedule, L1 forecast, energy savings, and explanations.
- Plan for future evolution:
  - Replace simplified physics with better pump and tunnel models when data is available.
  - Extend to more objectives (e.g., equipment wear, emissions) if needed.
  - Add more specialized agents (e.g., anomaly detection, maintenance scheduling, pump‑health and specific‑energy monitors) that consume the same data streams.
  - Explore **data‑driven / RL‑style controllers** that imitate the MPC policy on the digital twin for edge deployment (NN imitator), inspired by recent predictive‑control work.
  - Incorporate feedback from operator overrides into future optimization (learning loop).

---

## Judging Criteria Alignment

Keep these four dimensions in mind as you build and present the solution:

1. **Real-world applicability & integration (25%)**
   - Emphasize the OPC UA / digital twin‑friendly interfaces and the clear plant boundary (inputs/outputs).
   - Show how the same architecture can migrate from the hackathon simulator to Viikinmäki/Sulkavuori/Kakola with configuration changes.

2. **Clarity and impact demonstration (25%)**
   - Prepare simple metrics and visuals: energy/cost vs baseline, L1 trajectories, F2 smoothness, pump hours, flush events.
   - Provide short natural-language explanations for a few key scenarios so judges can see *why* the agent behaves as it does.

3. **Technical soundness and functionality (25%)**
   - Base dynamics on the provided tunnel volume and pump curve docs, not purely ad‑hoc assumptions.
   - Demonstrate stability across full 14‑day / 1‑month runs with no constraint violations and sensible pump behaviour.

4. **Creativity and AI coordination (25%)**
   - Highlight the multi-agent design (forecasters, planner, supervisor, OPC UA bridge) and how they coordinate.
   - Mention any interesting forecasting ideas, adaptive weighting strategies, or agent collaboration patterns you use.

---

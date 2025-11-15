# Optimizer Constraints Inventory

## Total Hard Constraints Count

For a 2-hour horizon with N pumps and 8 time steps (15-min intervals):
- **~500-800+ constraints** depending on configuration

## Detailed Breakdown

### 1. **Operational Constraints** (Per Time Step)

Per time step `t` and pump `pid`:

#### 1.1 Minimum Pumps On
```
∑(pump_on[p][t]) ≥ min_pumps_on  (typically 1)
```
- **Count:** `num_steps` (8 per 2h horizon)
- **Type:** Hard inequality

#### 1.2 Frequency Bounds (When Pump On)
For each pump at each time step:
```
pump_on[pid][t] * min_freq ≤ pump_freq[pid][t] ≤ pump_on[pid][t] * max_freq
```
- **Count:** `2 × num_pumps × num_steps` (e.g., 2 × 2 × 8 = 32 for 2 pumps)
- **Type:** Hard inequality (2 bounds per pump per step)

#### 1.3 Flow Bounds (Proportional to Frequency)
```
pump_flow[pid][t] ≥ (pump_freq[pid][t] / max_freq) × max_flow × 0.9
pump_flow[pid][t] ≤ (pump_freq[pid][t] / max_freq) × max_flow × 1.1
```
- **Count:** `2 × num_pumps × num_steps` (e.g., 32)
- **Type:** Hard inequality

#### 1.4 Power Model (Cubic Approximation)
```
pump_power[pid][t] ≥ base_power × pump_on[pid][t] + freq_excess × adjusted_slope × 0.85
pump_power[pid][t] ≤ base_power × pump_on[pid][t] + freq_excess × adjusted_slope × 1.15
pump_power[pid][t] ≥ base_power × pump_on[pid][t]
pump_power[pid][t] ≤ max_power × pump_on[pid][t]
```
- **Count:** `4 × num_pumps × num_steps` (e.g., 64)
- **Type:** Hard inequality

#### 1.5 L1 Mass Balance (Dynamics)
```
l1[t] = l1[t-1] + (inflow[t] - outflow[t]) × Δt / tunnel_volume
```
- **Count:** `num_steps` (8)
- **Type:** Hard equality

#### 1.6 L1 Level Bounds
**Hard constraints (default):**
```
l1_min_m ≤ l1[t] ≤ l1_max_m
```
OR
**Soft constraints (with violations):**
```
l1_violation_below[t] ≥ max(0, l1_min_m - l1[t])
l1_violation_above[t] ≥ max(0, l1[t] - l1_max_m)
```
- **Count (hard):** `num_steps` (enforced via variable bounds)
- **Count (soft):** `2 × num_steps` (penalty variables)
- **Type:** Hard or soft inequality

---

### 2. **Minimum On/Off Duration Constraints**

#### 2.1 Continuity for First Steps
```
pump_on[pid][0:min_on_steps] = 1  (if currently on)
pump_on[pid][0:min_off_steps] = 0  (if currently off)
```
- **Count:** `min_on_steps + min_off_steps` per pump (e.g., 2h / 15min + 2h / 15min = 16 per pump)
- **For 2 pumps:** 32 total
- **Type:** Hard equality

#### 2.2 Minimum On Duration (Turn-On Logic)
```
IF pump_on[pid][t] transitions from 0→1:
  THEN pump_on[pid][t:t+min_on_steps] = 1
```
- **Implemented via auxiliary boolean variables:**
  - `was_off[pid][t]` = 1 - pump_on[pid][t-1]
  - `turns_on[pid][t]` = was_off AND pump_on[pid][t]
  
- **Count:** `3 × (num_steps - min_on_steps) × num_pumps` (binary variables + constraints)
  - E.g., for 2 pumps, 8 steps, min_on_steps=8: ~48 constraints
  - Plus `min_on_steps × (num_steps - min_on_steps) × num_pumps` enforcement constraints
  - E.g., ~128 enforcement constraints

#### 2.3 Minimum Off Duration (Similar logic)
- **Count:** Same magnitude as on duration
- **Total:** ~128 constraints for 2 pumps, 2h horizon

---

### 3. **Objective Functions (Penalties, Not Explicit Constraints)**

These are **weighted objectives**, not hard constraints, but they shape feasible solutions:

#### 3.1 Cost Minimization
```
cost_obj = ∑_t,p (power[p][t] × price[t] × Δt)
```
- **Weight:** `weights["cost"]` (adaptive: 0.1–1.5)

#### 3.2 Smoothness (Outflow Variance)
```
smoothness_obj = ∑_t (outflow[t] - avg_outflow)²
```
- **Weight:** `weights["smoothness"]` (0.05–0.2)

#### 3.3 Safety (L1 Away from Bounds)
```
safety_obj = ∑_t (l1[t] - l1_center)² - 50 × (dist_to_min + dist_to_max)
```
- **Weight:** `weights["safety_margin"]` (0.1–2.0, higher when risky)

#### 3.5 Specific Energy (kWh/m³ Efficiency)
```
specific_energy_obj = ∑_t,p (power[p][t] × Δt - flow[p][t] × target_ratio)²
```
- **Weight:** `weights["specific_energy"]` (0.05–0.3)

#### 3.6 L1 Violation Penalty (If Soft Constraints Enabled)
```
violation_penalty = l1_violation_penalty × (l1_violation_below[t] + l1_violation_above[t])
```
- **Weight:** `l1_violation_penalty` (default: 1000, very high)

---

## Summary by Category

| Category | Count (2 pumps, 2h) | Complexity |
|----------|---------------------|-----------|
| Minimum pumps on | 8 | Linear |
| Frequency bounds | 32 | Linear |
| Flow bounds | 32 | Linear |
| Power model | 64 | Linear (approximates cubic) |
| L1 dynamics | 8 | Linear |
| L1 bounds | 8 (hard) or 16 (soft) | Linear |
| On/off continuity | 32 | Linear |
| Min on duration | 176 | Binary + linear |
| Min off duration | 176 | Binary + linear |
| **Total Hard Constraints** | **~536-568** | **Linear + Binary** |
| **Soft Constraint Penalties** | 6 objectives | Quadratic + Linear |

---

## Solver Configuration

- **Solver:** OR-Tools SCIP (mixed-integer linear programming)
- **Variables per pump:** ~40-50 per time step
- **Binary variables:** O(num_pumps × num_steps) for on/off decisions
- **Continuous variables:** O(num_pumps × num_steps) for freq, flow, power, L1
- **Multi-threading:** Enabled (Option C) - uses all available CPU cores for branch-and-bound search

---

## Real-World Complexity

For a realistic setup:
- **2 pumps, 2h horizon (8 steps):** ~550 constraints
- **2 pumps, 24h horizon (96 steps):** ~6,600 constraints
- **4 pumps, 24h horizon:** ~13,200 constraints

Solve time: 1–30 seconds depending on:
- Forecast quality
- Risk level (adaptive weighting complexity)
- Number of optimal solutions (early termination with feasible solution possible)
- Timeout setting (currently 30s)

---

## Adaptive Tuning

Constraints are **not fixed**—they adapt:

1. **Forecast quality** → Adjusts L1 bounds (safety margins added for poor forecast)
2. **Risk level** → Weights shift (CRITICAL risk: 2.0× safety margin weight)
3. **Strategic plan (LLM)** → Objective weights rebalanced per 24h window
4. **Soft vs. Hard constraints** → Toggle allows controlled L1 violations with penalties


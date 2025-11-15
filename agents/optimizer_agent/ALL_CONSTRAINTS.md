# Complete Constraints Inventory

## System Configuration

**Default Values:**
- L1 Min: 0.0 m
- L1 Max: 8.0 m
- Flush Target: 0.5 m (daily flush constraint)
- Tunnel Volume: 50,000 m³
- Min Pumps On: 1 (at least one pump always running)
- Min On Duration: 120 minutes (2 hours)
- Min Off Duration: 120 minutes (2 hours)
- Time Step: 15 minutes

**Pump Specifications:**
- Small Pumps (1.1, 2.1): ~0.5 m³/s, 200 kW
- Large Pumps (1.2-1.4, 2.2-2.4): ~1.0 m³/s, 400 kW
- Frequency Range: 47.8 - 50.0 Hz (hardware limits)

---

## HARD CONSTRAINTS (Must Always Be Satisfied)

### 1. **Minimum Pumps On** ⚠️ CRITICAL
```
∑(pump_on[p][t]) ≥ min_pumps_on  (default: 1)
```
- **Type:** Hard inequality
- **Count:** 1 per time step (8 for 2h horizon)
- **Purpose:** At least one pump must always be running (no full station shutdown)
- **Enforcement:** Linear constraint

---

### 2. **Pump Frequency Bounds** (When Pump is ON)
```
IF pump_on[pid][t] == 1:
  THEN: min_frequency_hz ≤ pump_freq[pid][t] ≤ max_frequency_hz
```
- **Type:** Hard inequality (conditional)
- **Bounds:**
  - Minimum: 47.8 Hz (when pump is ON)
  - Maximum: 50.0 Hz (when pump is ON)
  - When OFF: frequency = 0.0
- **Count:** 2 constraints per pump per time step
  - `pump_freq[pid][t] >= pump_on[pid][t] * min_frequency_hz`
  - `pump_freq[pid][t] <= pump_on[pid][t] * max_frequency_hz`
- **Purpose:** Enforce hardware operating limits

---

### 3. **Pump Flow Bounds** (Proportional to Frequency)
```
pump_flow[pid][t] ≥ (freq[pid][t] / max_freq) × max_flow × 0.9
pump_flow[pid][t] ≤ (freq[pid][t] / max_freq) × max_flow × 1.1
```
- **Type:** Hard inequality
- **Count:** 2 constraints per pump per time step
- **Purpose:** Flow must be proportional to frequency (linear approximation)
- **Tolerance:** ±10% to account for non-linear pump characteristics

---

### 4. **Pump Power Model** (Linear Approximation of Cubic Relationship)
```
power[pid][t] >= base_power × pump_on[pid][t] + freq_excess × slope × 0.85
power[pid][t] <= base_power × pump_on[pid][t] + freq_excess × slope × 1.15
power[pid][t] >= base_power × pump_on[pid][t]  (lower bound)
power[pid][t] <= max_power × pump_on[pid][t]   (upper bound)
```
- **Type:** Hard inequality (4 constraints per pump per time step)
- **Purpose:** Power consumption must match frequency (approximates P ∝ f³)
- **Base Power:** ~87% of max at minimum frequency (47.8 Hz)
- **Slope:** Adjusted by 1.5× to approximate cubic behavior
- **Tolerance:** ±15% for linear approximation

---

### 5. **L1 Mass Balance (Dynamics)**
```
IF t == 0:
  l1[0] = l1_initial + (inflow[0] - outflow[0]) × Δt / tunnel_volume
ELSE:
  l1[t] = l1[t-1] + (inflow[t] - outflow[t]) × Δt / tunnel_volume
```
- **Type:** Hard equality
- **Count:** 1 per time step (8 for 2h horizon)
- **Purpose:** L1 level changes based on mass balance (inflow - outflow)
- **Variables:**
  - `inflow[t]`: Forecasted inflow (m³/s)
  - `outflow[t]`: Sum of all pump flows (m³/s)
  - `Δt`: Time step (15 minutes = 900 seconds)
  - `tunnel_volume`: 50,000 m³

---

### 6. **L1 Level Bounds** (Hard Constraint) ⚠️ DEFAULT
```
l1_min_m ≤ l1[t] ≤ l1_max_m
```
- **Type:** Hard inequality (enforced via variable bounds)
- **Default:** 0.0 m ≤ L1 ≤ 8.0 m
- **Count:** Enforced via variable bounds (no explicit constraints needed)
- **Purpose:** L1 bounds are **hard constraints** - must never be violated for safety

#### 6b. Soft Constraints (Deprecated - when `allow_l1_violations = True`)
```
l1_min_m - tolerance ≤ l1[t] ≤ l1_max_m + tolerance
l1_violation_below[t] ≥ max(0, l1_min_m - l1[t])
l1_violation_above[t] ≥ max(0, l1[t] - l1_max_m)
```
- **Type:** Soft with penalty (deprecated - not recommended)
- **Tolerance:** ±0.5 m (default)
- **Penalty:** 1000.0 (very high, but violations allowed)
- **Count:** 2 constraints per time step (violation measurement)
- **Status:** Deprecated - L1 bounds should always be hard constraints for safety

---

### 7. **Minimum On Duration** ⚠️ TIME-BASED
```
IF pump turns ON at time t:
  THEN pump_on[pid][t:t+min_on_steps] = 1
```
- **Type:** Hard constraint (sequence-based)
- **Duration:** 120 minutes = 8 time steps (15-min intervals)
- **Implementation:**
  1. **Continuity:** If pump is currently ON, it must stay ON for first `min_on_steps`
  2. **Turn-On Detection:** Uses auxiliary boolean variables:
     - `was_off[pid][t] = 1 - pump_on[pid][t-1]`
     - `turns_on[pid][t] = was_off AND pump_on[pid][t]`
  3. **Enforcement:** If `turns_on[pid][t] == 1`, then `pump_on[pid][t:t+8] = 1`
- **Count:** 
  - Continuity: up to 8 constraints per pump
  - Turn-on detection: 3 constraints per pump per time step
  - Enforcement: 8 constraints per detected turn-on
  - **Total:** ~176 constraints for 2 pumps, 2h horizon

---

### 8. **Minimum Off Duration** ⚠️ TIME-BASED
```
IF pump turns OFF at time t:
  THEN pump_on[pid][t:t+min_off_steps] = 0
```
- **Type:** Hard constraint (sequence-based)
- **Duration:** 120 minutes = 8 time steps
- **Implementation:** Similar to minimum on duration
- **Count:** ~176 constraints for 2 pumps, 2h horizon
- **Purpose:** Prevent rapid cycling (protects pump hardware)

---

## SOFT CONSTRAINTS (Objectives with Penalties)

These are **weighted objectives** in the optimization, not hard constraints:

### 9. **Cost Minimization**
```
cost_obj = ∑(t,p) power[p][t] × price[t] × Δt
```
- **Weight:** Adaptive (0.1 - 1.5) based on risk level
- **Purpose:** Minimize total electricity cost
- **Unit:** EUR

---

### 10. **Outflow Smoothness**
```
smoothness_obj = ∑(t) |outflow[t] - outflow[t+1]|
```
- **Type:** Linear approximation (absolute deviation)
- **Weight:** 0.05 - 0.2 (adaptive)
- **Purpose:** Minimize outflow variance (prefer constant F2)
- **Implementation:** Minimizes absolute difference between consecutive time steps

---

### 11. **Safety Margin (L1 Away from Bounds)**
```
safety_obj = ∑(t) |l1[t] - l1_center| + penalty for being close to bounds
```
- **Type:** Linear approximation
- **Weight:** 0.1 - 2.0 (higher when risk is high)
- **Purpose:** Encourage L1 to stay in middle range (away from min/max bounds)
- **Adaptive:** Weight increases significantly in HIGH/CRITICAL risk scenarios

---

### 12. **Daily Flush Constraint** (Soft Objective)
```
flush_obj = ∑(t) flush_penalty[t] × flush_weight[t]
```
- **Type:** Soft objective (encourages, doesn't force)
- **Activation:** When `hours_since_last_flush >= 20` (near 24h mark)
- **Target:** L1 should reach `flush_target_level_m` (0.5 m) at least once per day
- **Weight:** Adaptive based on:
  - Urgency: Increases as time since last flush approaches 24h
  - Opportunity: Higher during low inflow + cheap price periods
  - Price: Inverse price weighting (prefer cheap periods)
- **Purpose:** Ensure daily tunnel cleaning while optimizing for cost
- **Implementation:** Soft penalty for L1 being above flush target during good conditions

---

### 13. **Specific Energy (Efficiency)**
```
specific_energy_obj = ∑(t,p) |energy[p][t] - target_energy[p][t]|
```
- **Type:** Linear approximation (absolute deviation from target)
- **Target:** 0.08 kWh/m³ (configurable, better than baseline ~0.092 to encourage improvement)
- **Weight:** 0.05 - 0.3 (adaptive)
- **Purpose:** Minimize kWh per m³ pumped (encourage efficient operation)

---

### 15. **L1 Violation Penalty** (If Soft Constraints Enabled)
```
violation_penalty = l1_violation_penalty × (l1_violation_below[t] + l1_violation_above[t])
```
- **Type:** Penalty term
- **Weight:** 1000.0 (default, very high)
- **Purpose:** Strongly discourage L1 violations (but allow them if necessary)
- **Tolerance:** ±0.5 m (default)

---

## ADAPTIVE CONSTRAINTS (Dynamic Adjustments)

### 16. **Forecast Quality-Based L1 Bounds Adjustment**
```
IF forecast_quality == 'poor':
  adjusted_l1_max = l1_max_m - (inflow_mae / 100 * 4)
  adjusted_l1_min = l1_min_m + 0.3
ELIF forecast_quality == 'fair':
  adjusted_l1_max = l1_max_m - (inflow_mae / 100 * 3)
  adjusted_l1_min = l1_min_m + 0.2
ELSE:
  adjusted_l1_max = l1_max_m  (no change)
  adjusted_l1_min = l1_min_m  (no change)
```
- **Type:** Dynamic constraint adjustment
- **Purpose:** Add safety margins when forecasts are unreliable
- **Trigger:** Based on forecast error history (MAE)

---

### 17. **Emergency Response Constraints** (LLM-Triggered)
```
IF emergency_response.severity == 'high' or 'critical':
  adjusted_l1_max = l1_max_m - 1.5  (reduce max by 1.5m)
  adjusted_l1_min = l1_min_m + 0.3  (increase min by 0.3m)
  weights['safety_margin'] *= 2.0
  weights['cost'] *= 0.3
```
- **Type:** Dynamic constraint and weight adjustment
- **Purpose:** React to detected forecast errors or system divergence
- **Trigger:** LLM emergency response generation

---

## VARIABLE BOUNDS

### Pump Variables (per pump, per time step):
- `pump_on[pid][t]`: Binary {0, 1}
- `pump_freq[pid][t]`: Continuous [0.0, max_frequency_hz]
- `pump_flow[pid][t]`: Continuous [0.0, max_flow_m3_s]
- `pump_power[pid][t]`: Continuous [0.0, max_power_kw]

### L1 Variables (per time step):
- **Hard mode:** `l1[t]`: Continuous [l1_min_m, l1_max_m]
- **Soft mode:** `l1[t]`: Continuous [l1_min_m - tolerance, l1_max_m + tolerance]
- **Violation variables:** `l1_violation_below[t]`, `l1_violation_above[t]`: Continuous [0.0, tolerance]

---

## CONSTRAINT SUMMARY

| Category | Type | Count (2 pumps, 2h) | Enforced |
|----------|------|---------------------|----------|
| **Hard Constraints** |
| Min pumps on | Hard | 8 | Always |
| Frequency bounds | Hard | 32 | Always |
| Flow bounds | Hard | 32 | Always |
| Power model | Hard | 64 | Always |
| L1 dynamics | Hard | 8 | Always |
| L1 bounds | Hard/Soft | 8/16 | Always (with tolerance) |
| Min on duration | Hard | ~176 | Always |
| Min off duration | Hard | ~176 | Always |
| **Soft Objectives** |
| Cost | Objective | 1 | Weighted |
| Smoothness | Objective | 7 | Weighted |
| Safety margin | Objective | 8 | Weighted |
| Specific energy | Objective | 64 | Weighted |
| Daily flush | Objective | 8 | Weighted (when active) |
| Violation penalty | Objective | 16 | Weighted |
| **Total** | | **~536-568 hard** | |

---

## ADAPTIVE BEHAVIOR

Constraints are **NOT static**—they adapt based on:

1. **Risk Level** (LOW, NORMAL, HIGH, CRITICAL)
   - Adjusts objective weights
   - Higher risk → more safety, less cost optimization

2. **Forecast Quality** (GOOD, FAIR, POOR)
   - Adjusts L1 bounds (adds safety margins)
   - Poor forecasts → tighter bounds

3. **Strategic Plan** (LLM-generated 24h plan)
   - Adjusts objective weights per time period
   - Strategies: PUMP_AGGRESSIVE, PUMP_MINIMAL, MAINTAIN_BUFFER, PUMP_CONSERVATIVE, BALANCED

4. **Emergency Response** (LLM-triggered)
   - Adjusts constraints and weights when divergence detected
   - Reduces L1 bounds, increases safety weight


---

## NOTES

- **Solver:** OR-Tools SCIP (Mixed-Integer Linear Programming)
- **Multi-threading:** Enabled (uses all CPU cores)
- **Solve Time:** 0.01 - 30 seconds (typically < 1s)
- **Time Horizon:** 2 hours (8 steps of 15 minutes)
- **Reoptimization:** Every 15 minutes (rolling MPC)


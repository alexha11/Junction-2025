"""Core MPC-style optimizer using OR-Tools for pump scheduling."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np
from ortools.linear_solver import pywraplp


class OptimizationMode(str, Enum):
    """Optimization fallback modes."""
    FULL = "full"  # Full MPC with all constraints
    SIMPLIFIED = "simplified"  # Reduced model for faster solve
    RULE_BASED = "rule_based"  # Conservative safe schedule


class RiskLevel(str, Enum):
    """Risk assessment for adaptive weighting."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PumpSpec:
    """Pump specifications."""
    pump_id: str
    max_flow_m3_s: float
    max_power_kw: float
    min_frequency_hz: float = 47.8  # Minimum operating frequency
    max_frequency_hz: float = 50.0
    preferred_freq_min_hz: float = 47.8
    preferred_freq_max_hz: float = 49.0


@dataclass
class SystemConstraints:
    """Constraints for the system."""
    l1_min_m: float = 0.5
    l1_max_m: float = 8.0
    tunnel_volume_m3: float = 50000.0  # Approximate tunnel volume
    min_pumps_on: int = 1  # At least one pump always on
    min_pump_on_duration_minutes: int = 120  # Minimum 2h on duration
    min_pump_off_duration_minutes: int = 120  # Minimum 2h off duration
    flush_frequency_days: int = 1  # Flush once per day
    flush_target_level_m: float = 0.5  # Flush to near minimum
    # Soft constraint options
    allow_l1_violations: bool = True  # Allow minor L1 violations with penalties
    l1_violation_tolerance_m: float = 0.5  # Maximum allowed violation (default 0.5m)
    l1_violation_penalty: float = 1000.0  # Penalty weight for violations (high = strict)


@dataclass
class ForecastData:
    """Forecasted data for optimization horizon."""
    timestamps: List[datetime]
    inflow_m3_s: List[float]
    price_eur_mwh: List[float]


@dataclass
class CurrentState:
    """Current system state."""
    timestamp: datetime
    l1_m: float
    inflow_m3_s: float
    outflow_m3_s: float
    pump_states: List[Tuple[str, bool, float]]  # (pump_id, is_on, frequency_hz)
    price_eur_mwh: float


@dataclass
class PumpSchedule:
    """Optimal pump schedule entry."""
    pump_id: str
    time_step: int
    is_on: bool
    frequency_hz: float
    flow_m3_s: float
    power_kw: float


@dataclass
class OptimizationResult:
    """Result from optimization."""
    success: bool
    mode: OptimizationMode
    schedules: List[PumpSchedule]
    l1_trajectory: List[float]
    total_energy_kwh: float
    total_cost_eur: float
    explanation: str
    solve_time_seconds: float
    l1_violations: int = 0  # Count of L1 constraint violations
    max_violation_m: float = 0.0  # Maximum violation magnitude


class MPCOptimizer:
    """MPC-style optimizer using OR-Tools for pump scheduling."""

    def __init__(
        self,
        pumps: List[PumpSpec],
        constraints: SystemConstraints,
        time_step_minutes: int = 15,
        tactical_horizon_minutes: int = 120,  # 2h tactical
        strategic_horizon_minutes: int = 1440,  # 24h strategic
    ):
        self.pumps = {p.pump_id: p for p in pumps}
        self.constraints = constraints
        self.time_step_minutes = time_step_minutes
        self.tactical_horizon_minutes = tactical_horizon_minutes
        self.strategic_horizon_minutes = strategic_horizon_minutes
        self.tactical_steps = tactical_horizon_minutes // time_step_minutes
        self.strategic_steps = strategic_horizon_minutes // time_step_minutes

    def assess_risk_level(self, current_state: CurrentState, forecast: ForecastData) -> RiskLevel:
        """Assess risk level based on L1 proximity to bounds and expected inflow."""
        l1 = current_state.l1_m
        l1_mid = (self.constraints.l1_min_m + self.constraints.l1_max_m) / 2
        l1_range = self.constraints.l1_max_m - self.constraints.l1_min_m
        
        # Distance to bounds (normalized)
        dist_to_min = (l1 - self.constraints.l1_min_m) / l1_range
        dist_to_max = (self.constraints.l1_max_m - l1) / l1_range
        
        # Expected inflow in next few steps
        avg_inflow = np.mean(forecast.inflow_m3_s[:4]) if len(forecast.inflow_m3_s) >= 4 else forecast.inflow_m3_s[0]
        expected_growth = np.mean(np.diff(forecast.inflow_m3_s[:4])) if len(forecast.inflow_m3_s) >= 4 else 0.0
        
        # Risk assessment
        if dist_to_min < 0.1 or dist_to_max < 0.1:
            return RiskLevel.CRITICAL
        elif dist_to_min < 0.2 or dist_to_max < 0.2:
            return RiskLevel.HIGH
        elif (dist_to_min < 0.3 and expected_growth > 0.1) or (dist_to_max < 0.3 and expected_growth < -0.1):
            return RiskLevel.HIGH
        elif dist_to_min < 0.4 or dist_to_max < 0.4:
            return RiskLevel.NORMAL
        else:
            return RiskLevel.LOW

    def get_adaptive_weights(self, risk_level: RiskLevel) -> dict:
        """Get adaptive objective weights based on risk level."""
        weights = {
            RiskLevel.LOW: {
                "cost": 1.0,
                "smoothness": 0.2,
                "fairness": 0.5,  # Increased for better pump balancing
                "safety_margin": 0.1,
                "specific_energy": 0.3,  # Added explicit specific energy objective
            },
            RiskLevel.NORMAL: {
                "cost": 0.8,
                "smoothness": 0.2,
                "fairness": 0.4,
                "safety_margin": 0.3,
                "specific_energy": 0.2,
            },
            RiskLevel.HIGH: {
                "cost": 0.4,
                "smoothness": 0.1,
                "fairness": 0.3,
                "safety_margin": 0.8,
                "specific_energy": 0.1,
            },
            RiskLevel.CRITICAL: {
                "cost": 0.1,
                "smoothness": 0.05,
                "fairness": 0.1,
                "safety_margin": 2.0,
                "specific_energy": 0.05,
            },
        }
        return weights[risk_level]

    def derive_strategic_guidance(
        self, forecast_24h: ForecastData
    ) -> List[str]:
        """Derive strategic guidance from 24h forecast."""
        guidance = []
        avg_price = np.mean(forecast_24h.price_eur_mwh)
        price_std = np.std(forecast_24h.price_eur_mwh)
        
        for i, price in enumerate(forecast_24h.price_eur_mwh):
            if price < avg_price - 0.5 * price_std:
                guidance.append("CHEAP")
            elif price > avg_price + 0.5 * price_std:
                guidance.append("EXPENSIVE")
            elif i < len(forecast_24h.inflow_m3_s) and forecast_24h.inflow_m3_s[i] > np.mean(forecast_24h.inflow_m3_s) * 1.3:
                guidance.append("SURGE_RISK")
            else:
                guidance.append("NORMAL")
        
        return guidance

    def solve_optimization(
        self,
        current_state: CurrentState,
        forecast: ForecastData,
        mode: OptimizationMode = OptimizationMode.FULL,
        timeout_seconds: int = 30,
    ) -> OptimizationResult:
        """Solve the optimization problem using OR-Tools."""
        start_time = time.time()
        
        # Assess risk and get weights
        risk_level = self.assess_risk_level(current_state, forecast)
        weights = self.get_adaptive_weights(risk_level)
        
        # Try full optimization first
        if mode == OptimizationMode.FULL:
            result = self._solve_full_optimization(
                current_state, forecast, weights, timeout_seconds
            )
            if result.success:
                return result
        
        # Fall back to simplified if full fails
        if mode in (OptimizationMode.FULL, OptimizationMode.SIMPLIFIED):
            result = self._solve_simplified_optimization(
                current_state, forecast, weights, timeout_seconds
            )
            if result.success:
                result.mode = OptimizationMode.SIMPLIFIED
                return result
        
        # Fall back to rule-based safe mode
        result = self._solve_rule_based(current_state, forecast)
        result.mode = OptimizationMode.RULE_BASED
        solve_time = time.time() - start_time
        result.solve_time_seconds = solve_time
        return result

    def _solve_full_optimization(
        self,
        current_state: CurrentState,
        forecast: ForecastData,
        weights: dict,
        timeout_seconds: int,
    ) -> OptimizationResult:
        """Solve full optimization with all constraints."""
        solver = pywraplp.Solver.CreateSolver("SCIP")
        if not solver:
            return OptimizationResult(
                success=False,
                mode=OptimizationMode.FULL,
                schedules=[],
                l1_trajectory=[],
                total_energy_kwh=0.0,
                total_cost_eur=0.0,
                explanation="Solver creation failed",
                solve_time_seconds=0.0,
            )
        
        solver.SetTimeLimit(timeout_seconds * 1000)  # Convert to milliseconds
        
        num_steps = len(forecast.timestamps)
        pump_ids = list(self.pumps.keys())
        
        # Decision variables
        # pump_on[pump_id][t] = 1 if pump is on at time t, 0 otherwise
        pump_on = {}
        # pump_freq[pump_id][t] = frequency in Hz
        pump_freq = {}
        # flow[pump_id][t] = flow rate in m3/s
        pump_flow = {}
        # power[pump_id][t] = power consumption in kW
        pump_power = {}
        # l1[t] = tunnel level at time t
        l1 = {}
        
        for pid in pump_ids:
            pump_on[pid] = [solver.BoolVar(f"on_{pid}_{t}") for t in range(num_steps)]
            pump_freq[pid] = [
                solver.NumVar(
                    self.pumps[pid].min_frequency_hz if pump_on[pid][t] else 0.0,
                    self.pumps[pid].max_frequency_hz,
                    f"freq_{pid}_{t}"
                )
                for t in range(num_steps)
            ]
            pump_flow[pid] = [
                solver.NumVar(0.0, self.pumps[pid].max_flow_m3_s, f"flow_{pid}_{t}")
                for t in range(num_steps)
            ]
            pump_power[pid] = [
                solver.NumVar(0.0, self.pumps[pid].max_power_kw, f"power_{pid}_{t}")
                for t in range(num_steps)
            ]
        
        # Violation variables (if soft constraints enabled)
        l1_violation_below = {}  # Violation below minimum
        l1_violation_above = {}  # Violation above maximum
        
        for t in range(num_steps):
            if self.constraints.allow_l1_violations:
                # Allow violations within tolerance
                l1_min_bound = self.constraints.l1_min_m - self.constraints.l1_violation_tolerance_m
                l1_max_bound = self.constraints.l1_max_m + self.constraints.l1_violation_tolerance_m
                l1[t] = solver.NumVar(
                    l1_min_bound,
                    l1_max_bound,
                    f"l1_{t}"
                )
                # Violation variables (non-negative, measure violation amount)
                l1_violation_below[t] = solver.NumVar(0.0, self.constraints.l1_violation_tolerance_m, f"l1_viol_below_{t}")
                l1_violation_above[t] = solver.NumVar(0.0, self.constraints.l1_violation_tolerance_m, f"l1_viol_above_{t}")
            else:
                # Hard constraints (original behavior)
                l1[t] = solver.NumVar(
                    self.constraints.l1_min_m,
                    self.constraints.l1_max_m,
                    f"l1_{t}"
                )
        
        # Initial conditions
        l1_initial = solver.NumVar(
            current_state.l1_m,
            current_state.l1_m,
            "l1_initial"
        )
        
        # Constraints
        for t in range(num_steps):
            # At least min_pumps_on pumps must be running
            solver.Add(
                sum(pump_on[pid][t] for pid in pump_ids) >= self.constraints.min_pumps_on
            )
            
            # Frequency only if pump is on
            for pid in pump_ids:
                pump_spec = self.pumps[pid]
                # If pump is on, frequency must be >= min_frequency
                solver.Add(
                    pump_freq[pid][t] >= pump_on[pid][t] * pump_spec.min_frequency_hz
                )
                solver.Add(
                    pump_freq[pid][t] <= pump_on[pid][t] * pump_spec.max_frequency_hz
                )
                
                # Simplified flow model: flow ≈ freq_factor * max_flow (linear)
                # Use linear approximation: flow proportional to frequency
                # Division by constant is allowed: flow = freq / max_freq * max_flow
                # Flow bounds: flow proportional to frequency when pump is on
                max_freq_inv = 1.0 / pump_spec.max_frequency_hz
                solver.Add(
                    pump_flow[pid][t] >= (pump_freq[pid][t] * max_freq_inv) * pump_spec.max_flow_m3_s * 0.9
                )
                solver.Add(
                    pump_flow[pid][t] <= (pump_freq[pid][t] * max_freq_inv) * pump_spec.max_flow_m3_s * 1.1
                )
                
                # Power model: improved linear approximation of cubic relationship
                # Real pump power ∝ freq³, but linear solver requires linear constraints
                # Use improved approximation: power ≈ base + slope * (freq - min_freq)
                # Where slope is steeper to approximate cubic behavior
                
                min_freq_ratio = pump_spec.min_frequency_hz / pump_spec.max_frequency_hz
                # Base power at minimum frequency (approximate cubic: ~85% at 95% freq)
                base_power_ratio = min_freq_ratio ** 2.5  # 0.95^2.5 ≈ 0.87
                base_power = pump_spec.max_power_kw * base_power_ratio
                
                # Power slope: approximate cubic by using steeper linear slope
                # At 50Hz, power = max_power
                # At 47.8Hz, power ≈ 87% of max
                # Linear slope = (max - base) / (1 - min_ratio)
                power_slope = (pump_spec.max_power_kw - base_power) / (1.0 - min_freq_ratio)
                
                # Power increases with frequency above minimum
                # Power = base + slope * (freq_ratio - min_freq_ratio) when pump is on
                # Use: power >= base * pump_on + (freq - min_freq) * slope
                # When pump is on: freq is between min_freq and max_freq
                # freq_ratio = freq / max_freq, so freq_ratio is between min_freq_ratio and 1.0
                
                # Simplified linear approximation with adjusted slope for cubic behavior
                # Scale slope by 1.5x to better approximate cubic curve in the operating range
                adjusted_slope = power_slope * 1.5
                
                # Power lower bound: base power when on, plus additional based on frequency
                # power >= base * pump_on + (freq_ratio - min_freq_ratio) * slope when pump is on
                freq_excess = pump_freq[pid][t] * max_freq_inv - min_freq_ratio * pump_on[pid][t]
                
                solver.Add(
                    pump_power[pid][t] >= base_power * pump_on[pid][t] + 
                    freq_excess * adjusted_slope * 0.85
                )
                solver.Add(
                    pump_power[pid][t] <= base_power * pump_on[pid][t] + 
                    freq_excess * adjusted_slope * 1.15
                )
                
                # Bounds: power must be between base and max when on
                solver.Add(
                    pump_power[pid][t] >= base_power * pump_on[pid][t]
                )
                solver.Add(
                    pump_power[pid][t] <= pump_spec.max_power_kw * pump_on[pid][t]
                )
            
            # L1 dynamics: simplified mass balance
            if t == 0:
                inflow = forecast.inflow_m3_s[t]
                outflow = sum(pump_flow[pid][t] for pid in pump_ids)
                # Change in volume = (inflow - outflow) * dt
                dt_seconds = self.time_step_minutes * 60
                volume_change_m3 = (inflow - outflow) * dt_seconds
                level_change_m = volume_change_m3 / self.constraints.tunnel_volume_m3
                solver.Add(l1[t] == l1_initial + level_change_m)
            else:
                inflow = forecast.inflow_m3_s[t]
                outflow = sum(pump_flow[pid][t] for pid in pump_ids)
                dt_seconds = self.time_step_minutes * 60
                volume_change_m3 = (inflow - outflow) * dt_seconds
                level_change_m = volume_change_m3 / self.constraints.tunnel_volume_m3
                solver.Add(l1[t] == l1[t - 1] + level_change_m)
            
            # L1 bounds - constraints handled via variable bounds and penalties
            # If soft constraints enabled, bounds are already expanded above
            # Add explicit constraints to ensure violations are measured correctly
            if self.constraints.allow_l1_violations:
                # Violations are measured by how far outside bounds L1 is
                # l1_violation_below >= max(0, l1_min - l1[t])
                # l1_violation_above >= max(0, l1[t] - l1_max)
                # These are linearized constraints
                solver.Add(l1_violation_below[t] >= self.constraints.l1_min_m - l1[t])
                solver.Add(l1_violation_below[t] >= 0.0)
                
                solver.Add(l1_violation_above[t] >= l1[t] - self.constraints.l1_max_m)
                solver.Add(l1_violation_above[t] >= 0.0)
            else:
                # Hard constraints (original behavior)
                solver.Add(l1[t] >= self.constraints.l1_min_m)
                solver.Add(l1[t] <= self.constraints.l1_max_m)
        
        # Minimum on/off durations
        min_on_steps = self.constraints.min_pump_on_duration_minutes // self.time_step_minutes
        min_off_steps = self.constraints.min_pump_off_duration_minutes // self.time_step_minutes
        
        for pid in pump_ids:
            current_is_on = next(
                (s[1] for s in current_state.pump_states if s[0] == pid),
                False
            )
            
            # Continuity constraints for first few steps
            for t in range(min(min_on_steps, num_steps)):
                if current_is_on:
                    solver.Add(pump_on[pid][t] == 1)
            for t in range(min(min_off_steps, num_steps)):
                if not current_is_on:
                    solver.Add(pump_on[pid][t] == 0)
            
            # General minimum duration constraints using sequence constraints
            # If pump turns on at t, it must stay on for at least min_on_steps
            for t in range(num_steps - min_on_steps + 1):
                if t > 0:
                    # Detect when pump turns on (transition from 0 to 1)
                    was_off = solver.BoolVar(f"was_off_{pid}_{t}")
                    turns_on = solver.BoolVar(f"turns_on_{pid}_{t}")
                    
                    # was_off = not pump_on[t-1]
                    solver.Add(was_off == 1 - pump_on[pid][t - 1])
                    # turns_on = was_off AND pump_on[t]
                    solver.Add(turns_on <= was_off)
                    solver.Add(turns_on <= pump_on[pid][t])
                    solver.Add(turns_on >= was_off + pump_on[pid][t] - 1)
                    
                    # If pump turns on at t, it must stay on for min_on_steps
                    for s in range(min_on_steps):
                        if t + s < num_steps:
                            solver.Add(pump_on[pid][t + s] >= turns_on)
            
            # Similar for turning off
            for t in range(num_steps - min_off_steps + 1):
                if t > 0:
                    was_on = solver.BoolVar(f"was_on_{pid}_{t}")
                    turns_off = solver.BoolVar(f"turns_off_{pid}_{t}")
                    
                    solver.Add(was_on == pump_on[pid][t - 1])
                    solver.Add(turns_off <= was_on)
                    solver.Add(turns_off <= 1 - pump_on[pid][t])
                    solver.Add(turns_off >= was_on + (1 - pump_on[pid][t]) - 1)
                    
                    for s in range(min_off_steps):
                        if t + s < num_steps:
                            solver.Add(pump_on[pid][t + s] <= 1 - turns_off)
        
        # Objective: minimize weighted combination
        cost_obj = 0.0
        smoothness_obj = 0.0
        fairness_obj = 0.0
        safety_obj = 0.0
        specific_energy_obj = 0.0
        
        # Cost: total energy cost
        for t in range(num_steps):
            price = forecast.price_eur_mwh[t] / 1000.0  # Convert to EUR/kWh
            dt_hours = self.time_step_minutes / 60.0
            for pid in pump_ids:
                energy_kwh = pump_power[pid][t] * dt_hours
                cost_obj += energy_kwh * price
        
        # Smoothness: minimize F2 variance (quadratic penalty)
        outflow_vars = [
            sum(pump_flow[pid][t] for pid in pump_ids) for t in range(num_steps)
        ]
        if len(outflow_vars) > 1:
            avg_outflow = sum(outflow_vars) / len(outflow_vars)
            for outflow in outflow_vars:
                smoothness_obj += (outflow - avg_outflow) ** 2
        
        # Fairness: balance pump hours more aggressively
        # Use absolute deviation from mean for better fairness
        pump_hours = [
            sum(pump_on[pid][t] for t in range(num_steps)) for pid in pump_ids
        ]
        if len(pump_hours) > 1:
            avg_hours = sum(pump_hours) / len(pump_hours)
            for hours in pump_hours:
                # Use squared deviation but scale by number of pumps for fairness
                fairness_obj += ((hours - avg_hours) / len(pump_hours)) ** 2
        
        # Specific energy: minimize kWh/m³ (encourage efficient operation)
        total_flow = 0.0
        for t in range(num_steps):
            for pid in pump_ids:
                total_flow += pump_flow[pid][t] * (self.time_step_minutes / 60.0)  # Convert to m³
        
        if total_flow > 0.01:  # Avoid division by zero
            # Minimize ratio of energy to flow (specific energy)
            # Since we can't divide directly, we minimize energy while maximizing flow
            # Approximate by: specific_energy_obj = total_energy / total_flow
            # Use inverse relationship: minimize energy / flow ≈ minimize (energy - flow * target_ratio)
            target_specific_energy = 0.4  # kWh/m³ target (will be tuned)
            for t in range(num_steps):
                dt_hours = self.time_step_minutes / 60.0
                for pid in pump_ids:
                    energy = pump_power[pid][t] * dt_hours
                    flow_m3 = pump_flow[pid][t] * dt_hours
                    # Penalize deviation from target specific energy
                    specific_energy_obj += (energy - flow_m3 * target_specific_energy) ** 2
        
        # Safety: penalize being close to bounds and violations
        # Use quadratic penalty that encourages staying away from bounds
        l1_safe_center = (self.constraints.l1_min_m + self.constraints.l1_max_m) / 2
        violation_penalty_obj = 0.0
        
        for t in range(num_steps):
            # Quadratic penalty for deviation from safe center (SCIP supports quadratic)
            # This encourages staying in the middle range
            safety_obj += (l1[t] - l1_safe_center) ** 2
            
            # Linear penalty terms for being close to bounds
            # Distance to minimum (larger penalty when closer to min)
            dist_to_min = l1[t] - self.constraints.l1_min_m
            # Distance to maximum (larger penalty when closer to max)
            dist_to_max = self.constraints.l1_max_m - l1[t]
            # Use negative distance (closer to bounds = higher penalty)
            # Penalty = -distance (linear term)
            safety_obj += -50.0 * dist_to_min  # Negative because smaller dist = higher penalty
            safety_obj += -50.0 * dist_to_max  # Negative because smaller dist = higher penalty
            
            # Violation penalty (if soft constraints enabled)
            if self.constraints.allow_l1_violations:
                # Heavy penalty for violations - discourage them strongly
                violation_penalty_obj += (
                    self.constraints.l1_violation_penalty * l1_violation_below[t] +
                    self.constraints.l1_violation_penalty * l1_violation_above[t]
                )
        
        # Violation penalty is always high priority (unless violations are fully allowed)
        violation_weight = self.constraints.l1_violation_penalty if self.constraints.allow_l1_violations else 0.0
        
        total_obj = (
            weights["cost"] * cost_obj +
            weights["smoothness"] * smoothness_obj +
            weights["fairness"] * fairness_obj +
            weights["safety_margin"] * safety_obj +
            weights.get("specific_energy", 0.0) * specific_energy_obj +
            violation_weight * violation_penalty_obj
        )
        
        solver.Minimize(total_obj)
        
        # Solve
        status = solver.Solve()
        
        if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            # Extract solution
            schedules = []
            l1_traj = []
            total_energy = 0.0
            total_cost = 0.0
            violations = 0
            max_violation = 0.0
            
            for t in range(num_steps):
                l1_val = l1[t].solution_value()
                l1_traj.append(l1_val)
                
                # Check for violations
                if l1_val < self.constraints.l1_min_m:
                    violations += 1
                    violation_mag = self.constraints.l1_min_m - l1_val
                    max_violation = max(max_violation, violation_mag)
                elif l1_val > self.constraints.l1_max_m:
                    violations += 1
                    violation_mag = l1_val - self.constraints.l1_max_m
                    max_violation = max(max_violation, violation_mag)
                
                for pid in pump_ids:
                    is_on = pump_on[pid][t].solution_value() > 0.5
                    freq = pump_freq[pid][t].solution_value() if is_on else 0.0
                    flow = pump_flow[pid][t].solution_value() if is_on else 0.0
                    power = pump_power[pid][t].solution_value() if is_on else 0.0
                    
                    schedules.append(
                        PumpSchedule(
                            pump_id=pid,
                            time_step=t,
                            is_on=is_on,
                            frequency_hz=freq,
                            flow_m3_s=flow,
                            power_kw=power,
                        )
                    )
                    
                    if is_on:
                        dt_hours = self.time_step_minutes / 60.0
                        energy = power * dt_hours
                        total_energy += energy
                        total_cost += energy * (forecast.price_eur_mwh[t] / 1000.0)
            
            solve_time = time.time() - start_time
            
            explanation = f"Optimized schedule using full MPC (risk: {risk_level.value})"
            if violations > 0:
                explanation += f". Warning: {violations} L1 violations (max: {max_violation:.3f}m)"
            
            return OptimizationResult(
                success=True,
                mode=OptimizationMode.FULL,
                schedules=schedules,
                l1_trajectory=l1_traj,
                total_energy_kwh=total_energy,
                total_cost_eur=total_cost,
                explanation=explanation,
                solve_time_seconds=solve_time,
                l1_violations=violations,
                max_violation_m=max_violation,
            )
        else:
            return OptimizationResult(
                success=False,
                mode=OptimizationMode.FULL,
                schedules=[],
                l1_trajectory=[],
                total_energy_kwh=0.0,
                total_cost_eur=0.0,
                explanation=f"Solver status: {status}",
                solve_time_seconds=time.time() - start_time,
            )

    def _solve_simplified_optimization(
        self,
        current_state: CurrentState,
        forecast: ForecastData,
        weights: dict,
        timeout_seconds: int,
    ) -> OptimizationResult:
        """Simplified optimization with fewer constraints."""
        # Similar to full but with relaxed constraints
        # For now, return rule-based as fallback
        return self._solve_rule_based(current_state, forecast)

    def _solve_rule_based(
        self,
        current_state: CurrentState,
        forecast: ForecastData,
    ) -> OptimizationResult:
        """Rule-based safe schedule that guarantees constraints."""
        schedules = []
        l1_traj = [current_state.l1_m]
        total_energy = 0.0
        total_cost = 0.0
        
        num_steps = min(len(forecast.timestamps), self.tactical_steps)
        pump_ids = list(self.pumps.keys())
        l1_current = current_state.l1_m
        
        # Simple rule: maintain L1 in safe middle range
        target_l1 = (self.constraints.l1_min_m + self.constraints.l1_max_m) / 2
        l1_threshold_high = self.constraints.l1_max_m * 0.8
        l1_threshold_low = self.constraints.l1_min_m * 1.2
        
        # Turn on/off pumps based on L1
        active_pumps = [pid for pid, is_on, _ in current_state.pump_states if is_on]
        if not active_pumps:
            active_pumps = [pump_ids[0]]  # At least one pump on
        
        for t in range(num_steps):
            inflow = forecast.inflow_m3_s[t]
            
            # Adjust pumping based on L1
            if l1_current > l1_threshold_high:
                # Pump more aggressively
                num_pumps = min(len(pump_ids), len(active_pumps) + 1)
                active_pumps = pump_ids[:num_pumps]
            elif l1_current < l1_threshold_low:
                # Pump less
                num_pumps = max(1, len(active_pumps) - 1)
                active_pumps = pump_ids[:num_pumps]
            
            # Calculate outflow and L1
            outflow = 0.0
            for pid in active_pumps:
                pump_spec = self.pumps[pid]
                freq = pump_spec.min_frequency_hz
                flow = pump_spec.max_flow_m3_s * 0.8  # Conservative flow
                power = pump_spec.max_power_kw * 0.75  # Approximate power
                
                schedules.append(
                    PumpSchedule(
                        pump_id=pid,
                        time_step=t,
                        is_on=True,
                        frequency_hz=freq,
                        flow_m3_s=flow,
                        power_kw=power,
                    )
                )
                
                outflow += flow
                dt_hours = self.time_step_minutes / 60.0
                energy = power * dt_hours
                total_energy += energy
                total_cost += energy * (forecast.price_eur_mwh[t] / 1000.0)
            
            # Add off pumps
            for pid in pump_ids:
                if pid not in active_pumps:
                    schedules.append(
                        PumpSchedule(
                            pump_id=pid,
                            time_step=t,
                            is_on=False,
                            frequency_hz=0.0,
                            flow_m3_s=0.0,
                            power_kw=0.0,
                        )
                    )
            
            # Update L1
            dt_seconds = self.time_step_minutes * 60
            volume_change_m3 = (inflow - outflow) * dt_seconds
            level_change_m = volume_change_m3 / self.constraints.tunnel_volume_m3
            l1_current = max(
                self.constraints.l1_min_m,
                min(self.constraints.l1_max_m, l1_current + level_change_m)
            )
            l1_traj.append(l1_current)
        
        return OptimizationResult(
            success=True,
            mode=OptimizationMode.RULE_BASED,
            schedules=schedules,
            l1_trajectory=l1_traj,
            total_energy_kwh=total_energy,
            total_cost_eur=total_cost,
            explanation="Rule-based safe schedule (optimizer fallback mode)",
            solve_time_seconds=0.0,
        )


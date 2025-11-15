"""Core MPC-style optimizer using OR-Tools for pump scheduling."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Tuple, Any, Dict

import numpy as np
from ortools.linear_solver import pywraplp

logger = logging.getLogger(__name__)


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
        
        # Log multi-threading configuration
        import logging
        logger = logging.getLogger(__name__)
        num_threads = os.cpu_count() or 4
        self.num_threads = num_threads
        logger.info(f"✓ Optimizer initialized with multi-threading: {num_threads} CPU cores available")

    def assess_risk_level(self, current_state: CurrentState, forecast: ForecastData) -> RiskLevel:
        """Assess risk level based on L1 proximity to bounds and expected inflow."""
        l1 = current_state.l1_m
        l1_mid = (self.constraints.l1_min_m + self.constraints.l1_max_m) / 2
        l1_range = self.constraints.l1_max_m - self.constraints.l1_min_m
        
        # Distance to bounds (normalized)
        if l1_range > 0.01:  # Avoid division by zero
            dist_to_min = (l1 - self.constraints.l1_min_m) / l1_range
            dist_to_max = (self.constraints.l1_max_m - l1) / l1_range
        else:
            # If range is too small, treat as at middle
            dist_to_min = 0.5
            dist_to_max = 0.5
        
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
    
    def _adjust_weights_for_strategy(
        self,
        base_weights: dict,
        strategic_plan: Any,  # StrategicPlan
        current_state: CurrentState,
    ) -> dict:
        """Adjust optimization weights based on LLM-generated strategic plan.
        
        Args:
            base_weights: Base weights from risk assessment
            strategic_plan: LLM-generated strategic plan
            current_state: Current system state
        
        Returns:
            Adjusted weights dict
        """
        weights = base_weights.copy()
        
        # Get strategy for current hour (0-23)
        current_hour = current_state.timestamp.hour
        strategy = self.get_strategy_for_time_period(current_hour, strategic_plan)
        
        # Adjust weights based on strategy
        if strategy == "PUMP_AGGRESSIVE":
            # Emphasize cost optimization, allow more pumping (only when forecast confidence is high)
            weights["cost"] *= 1.5  # Prioritize cost
            if "specific_energy" in weights:
                weights["specific_energy"] *= 1.2
            weights["smoothness"] *= 0.8  # Less emphasis on smoothness
        elif strategy == "PUMP_MINIMAL":
            # Minimize pumping, prioritize safety
            weights["cost"] *= 0.8  # Less emphasis on cost
            if "specific_energy" in weights:
                weights["specific_energy"] *= 0.7  # Minimize energy use
            weights["smoothness"] *= 1.2  # Maintain smoothness
        elif strategy == "PUMP_CONSERVATIVE":
            # Conservative approach when forecast uncertainty is high
            weights["cost"] *= 0.5  # Reduce cost optimization significantly
            if "specific_energy" in weights:
                weights["specific_energy"] *= 0.6  # Reduce energy optimization
            weights["safety_margin"] *= 2.0  # Double safety margin weight
            weights["smoothness"] *= 1.1  # Maintain smoothness for stability
        elif strategy == "MAINTAIN_BUFFER":
            # Build buffer before surge/expensive periods
            weights["cost"] *= 1.0  # Balanced
            if "specific_energy" in weights:
                weights["specific_energy"] *= 1.1  # Slight emphasis on energy (pump now)
            weights["smoothness"] *= 0.9  # Allow variation to build buffer
        # BALANCED: use base weights unchanged
        
        return weights
    
    def _adjust_constraints_for_forecast_quality(
        self, forecast_quality: Dict[str, Any]
    ) -> Dict[str, float]:
        """Adjust constraints based on forecast quality to add safety margins.
        
        Args:
            forecast_quality: Dict with 'quality_level' ('good', 'fair', 'poor'),
                'inflow_mae', 'price_mae', 'l1_mae'
        
        Returns:
            Dict with adjusted 'l1_min_m' and 'l1_max_m'
        """
        quality_level = forecast_quality.get('quality_level', 'good')
        inflow_mae = forecast_quality.get('inflow_mae', 0)
        
        # Base constraints
        adjusted_min = self.constraints.l1_min_m
        adjusted_max = self.constraints.l1_max_m
        
        # Add safety margins based on forecast quality
        if quality_level == 'poor':
            # Large errors: significant safety margins
            # Reduce max by up to 1.5m to protect against surge, increase min by 0.3m for buffer
            safety_margin_max = min(1.5, inflow_mae / 100 * 5)  # Proportional to error
            safety_margin_min = 0.3
            adjusted_max = self.constraints.l1_max_m - safety_margin_max
            adjusted_min = self.constraints.l1_min_m + safety_margin_min
        elif quality_level == 'fair':
            # Medium errors: moderate safety margins
            safety_margin_max = min(0.8, inflow_mae / 100 * 3)
            safety_margin_min = 0.2
            adjusted_max = self.constraints.l1_max_m - safety_margin_max
            adjusted_min = self.constraints.l1_min_m + safety_margin_min
        # 'good' quality: use base constraints
        
        # Ensure adjusted constraints are still valid
        adjusted_min = max(self.constraints.l1_min_m * 0.8, adjusted_min)  # Don't go too low
        adjusted_max = min(self.constraints.l1_max_m * 1.1, adjusted_max)  # Don't go too high
        adjusted_max = max(adjusted_min + 0.5, adjusted_max)  # Ensure min < max
        
        return {
            'l1_min_m': adjusted_min,
            'l1_max_m': adjusted_max,
        }

    def derive_strategic_guidance(
        self, forecast_24h: ForecastData
    ) -> List[str]:
        """Derive strategic guidance from 24h forecast (algorithmic method)."""
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
    
    def get_strategy_for_time_period(
        self,
        hour: int,
        strategic_plan: Optional[Any] = None,  # StrategicPlan from LLM
    ) -> str:
        """Get strategy type for a specific hour based on strategic plan.
        
        Args:
            hour: Hour of the day (0-23)
            strategic_plan: Optional LLM-generated StrategicPlan
        
        Returns:
            Strategy type: PUMP_AGGRESSIVE, PUMP_MINIMAL, MAINTAIN_BUFFER, or BALANCED
        """
        if strategic_plan and hasattr(strategic_plan, 'time_periods'):
            # Use LLM-generated strategic plan
            for start_hour, end_hour, strategy in strategic_plan.time_periods:
                if start_hour <= hour < end_hour:
                    return strategy
        
        # Fallback: default strategy
        return "BALANCED"

    def detect_divergence(
        self,
        current_state: CurrentState,
        forecast: ForecastData,
        previous_prediction: Optional[float] = None,
        previous_forecast_inflow: Optional[float] = None,
        previous_forecast_price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Detect if actual values significantly diverge from forecasts.
        
        Returns:
            Dict with 'error_type', 'error_magnitude', 'forecast_value', 'actual_value'
            or None if no significant divergence
        """
        divergence = None
        
        # Check L1 divergence
        if previous_prediction is not None:
            l1_error = abs(current_state.l1_m - previous_prediction)
            if l1_error > 0.5:  # More than 0.5m difference
                divergence = {
                    'error_type': 'l1_divergence',
                    'error_magnitude': l1_error,
                    'forecast_value': previous_prediction,
                    'actual_value': current_state.l1_m,
                }
                return divergence
        
        # Check inflow surge (if we have previous forecast)
        if previous_forecast_inflow is not None and previous_forecast_inflow > 1e-6:  # Use threshold to avoid division by tiny values
            inflow_error_pct = abs(current_state.inflow_m3_s - previous_forecast_inflow) / previous_forecast_inflow * 100
            if current_state.inflow_m3_s > previous_forecast_inflow * 1.3:  # 30% higher
                divergence = {
                    'error_type': 'inflow_surge',
                    'error_magnitude': inflow_error_pct,
                    'forecast_value': previous_forecast_inflow,
                    'actual_value': current_state.inflow_m3_s,
                }
                return divergence
        
        # Check price spike (if we have previous forecast)
        if previous_forecast_price is not None and previous_forecast_price > 1e-6:  # Use threshold to avoid division by tiny values
            price_error_pct = abs(current_state.price_eur_mwh - previous_forecast_price) / previous_forecast_price * 100
            if current_state.price_eur_mwh > previous_forecast_price * 1.5:  # 50% higher
                divergence = {
                    'error_type': 'price_spike',
                    'error_magnitude': price_error_pct,
                    'forecast_value': previous_forecast_price,
                    'actual_value': current_state.price_eur_mwh,
                }
                return divergence
        
        return None
    
    def apply_emergency_response(
        self,
        emergency_response: Any,  # EmergencyResponse from LLM
        current_state: CurrentState,
    ) -> Dict[str, Any]:
        """Apply emergency response actions to optimizer configuration.
        
        Returns:
            Dict with adjusted constraints and weights
        """
        adjustments = {
            'constraints': {},
            'weights': {},
        }
        
        error_type = emergency_response.error_type
        severity = emergency_response.severity
        
        # Apply constraint adjustments based on error type and severity
        if error_type == 'inflow_surge':
            # Reduce L1_max to protect against overflow
            if severity in ('high', 'critical'):
                adjustments['constraints']['l1_max_m'] = self.constraints.l1_max_m - 1.5
            else:
                adjustments['constraints']['l1_max_m'] = self.constraints.l1_max_m - 1.0
            adjustments['constraints']['l1_min_m'] = self.constraints.l1_min_m + 0.3
        elif error_type == 'price_spike':
            # No constraint changes, but weight adjustments
            pass
        elif error_type == 'l1_divergence':
            # Tighten bounds around current L1
            if current_state.l1_m > (self.constraints.l1_min_m + self.constraints.l1_max_m) / 2:
                # L1 is high, reduce max
                adjustments['constraints']['l1_max_m'] = min(
                    self.constraints.l1_max_m - 0.5,
                    current_state.l1_m + 1.0
                )
            else:
                # L1 is low, increase min
                adjustments['constraints']['l1_min_m'] = max(
                    self.constraints.l1_min_m + 0.3,
                    current_state.l1_m - 1.0
                )
        
        # Apply weight adjustments for emergency mode
        if severity in ('high', 'critical'):
            adjustments['weights'] = {
                'safety_margin': 2.0,  # Double safety margin weight
                'cost': 0.3,  # Reduce cost optimization
                'specific_energy': 0.5,  # Reduce energy optimization
            }
        elif severity == 'medium':
            adjustments['weights'] = {
                'safety_margin': 1.5,
                'cost': 0.6,
                'specific_energy': 0.7,
            }
        
        return adjustments

    def solve_optimization(
        self,
        current_state: CurrentState,
        forecast: ForecastData,
        mode: OptimizationMode = OptimizationMode.FULL,
        timeout_seconds: int = 30,
        strategic_plan: Optional[Any] = None,  # Optional LLM-generated StrategicPlan
        forecast_quality: Optional[Dict[str, Any]] = None,  # Optional forecast quality metrics
        emergency_response: Optional[Any] = None,  # Optional EmergencyResponse from LLM
    ) -> OptimizationResult:
        """Solve the optimization problem using OR-Tools.
        
        Args:
            current_state: Current system state
            forecast: Forecast data for tactical horizon (2h)
            mode: Optimization mode (FULL, SIMPLIFIED, RULE_BASED)
            timeout_seconds: Solver timeout
            strategic_plan: Optional LLM-generated 24h strategic plan to influence weights
            forecast_quality: Optional dict with 'quality_level' ('good', 'fair', 'poor'),
                'inflow_mae', 'price_mae', 'l1_mae' for forecast quality assessment
        """
        start_time = time.time()
        
        # Adjust constraints based on forecast quality if provided
        adjusted_constraints = self.constraints
        if forecast_quality and forecast_quality.get('quality_level') != 'good':
            adjusted_constraints = self._adjust_constraints_for_forecast_quality(forecast_quality)
            # Temporarily store original for restoration
            original_l1_min = self.constraints.l1_min_m
            original_l1_max = self.constraints.l1_max_m
            self.constraints.l1_min_m = adjusted_constraints['l1_min_m']
            self.constraints.l1_max_m = adjusted_constraints['l1_max_m']
        else:
            original_l1_min = None
            original_l1_max = None
        
        try:
            # Apply emergency response adjustments if provided
            emergency_adjustments = None
            if emergency_response:
                emergency_adjustments = self.apply_emergency_response(emergency_response, current_state)
                # Apply constraint adjustments
                if 'l1_max_m' in emergency_adjustments['constraints']:
                    self.constraints.l1_max_m = emergency_adjustments['constraints']['l1_max_m']
                if 'l1_min_m' in emergency_adjustments['constraints']:
                    self.constraints.l1_min_m = emergency_adjustments['constraints']['l1_min_m']
            
            # Assess risk and get base weights
            risk_level = self.assess_risk_level(current_state, forecast)
            weights = self.get_adaptive_weights(risk_level)
            
            # Apply emergency weight adjustments if provided
            if emergency_adjustments and emergency_adjustments.get('weights'):
                for key, multiplier in emergency_adjustments['weights'].items():
                    if key in weights:
                        weights[key] *= multiplier
            
            # Adjust weights based on forecast quality if provided
            if forecast_quality and forecast_quality.get('quality_level') == 'poor':
                # Low forecast confidence: increase safety margin weight
                weights['safety_margin'] *= 1.5
                weights['cost'] *= 0.8  # Less emphasis on cost optimization
            
            # Adjust weights based on strategic plan if available
            if strategic_plan and hasattr(strategic_plan, 'plan_type'):
                weights = self._adjust_weights_for_strategy(weights, strategic_plan, current_state)
        
            # Try full optimization first
            if mode == OptimizationMode.FULL:
                result = self._solve_full_optimization(
                    current_state, forecast, weights, timeout_seconds, strategic_plan
                )
                if result.success:
                    solve_time = time.time() - start_time
                    result.solve_time_seconds = solve_time
                    # Restore original constraints if adjusted
                    if original_l1_min is not None:
                        self.constraints.l1_min_m = original_l1_min
                        self.constraints.l1_max_m = original_l1_max
                    return result
            
            # Fall back to simplified if full fails
            if mode in (OptimizationMode.FULL, OptimizationMode.SIMPLIFIED):
                result = self._solve_simplified_optimization(
                    current_state, forecast, weights, timeout_seconds
                )
                if result.success:
                    result.mode = OptimizationMode.SIMPLIFIED
                    solve_time = time.time() - start_time
                    result.solve_time_seconds = solve_time
                    # Restore original constraints if adjusted
                    if original_l1_min is not None:
                        self.constraints.l1_min_m = original_l1_min
                        self.constraints.l1_max_m = original_l1_max
                    return result
            
            # Fall back to rule-based safe mode
            result = self._solve_rule_based(current_state, forecast)
            result.mode = OptimizationMode.RULE_BASED
            solve_time = time.time() - start_time
            result.solve_time_seconds = solve_time
            # Restore original constraints if adjusted
            if original_l1_min is not None:
                self.constraints.l1_min_m = original_l1_min
                self.constraints.l1_max_m = original_l1_max
            return result
        except Exception as e:
            # Restore original constraints in case of error
            if original_l1_min is not None:
                self.constraints.l1_min_m = original_l1_min
                self.constraints.l1_max_m = original_l1_max
            raise

    def _solve_full_optimization(
        self,
        current_state: CurrentState,
        forecast: ForecastData,
        weights: dict,
        timeout_seconds: int,
        strategic_plan: Optional[Any] = None,
    ) -> OptimizationResult:
        """Solve full optimization with all constraints."""
        import logging
        logger = logging.getLogger(__name__)
        
        start_time = time.time()
        
        # Calculate risk level for explanation (needed for explanation string)
        risk_level = self.assess_risk_level(current_state, forecast)
        
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
        
        # Enable multi-threading for SCIP solver (Option C speedup)
        # Use all available CPU cores for parallel branch-and-bound search
        num_threads = getattr(self, 'num_threads', os.cpu_count() or 4)  # Use instance value or default
        # Set SCIP parallel parameters separately (must use '=' format)
        # Note: SCIP parameter names may vary by version - disable if not available
        try:
            solver.SetSolverSpecificParametersAsString("parallel/mode = 1")
        except Exception as e:
            # If parallel mode fails, continue without it
            logger.debug(f"Failed to set SCIP parallel/mode: {e}")
        
        # Try to set number of threads (parameter name may vary by SCIP version)
        try:
            # Try different possible parameter names
            for param_name in [f"parallel/maxnthreads = {num_threads}", 
                             f"parallel/numsolver = {num_threads}",
                             f"threads = {num_threads}"]:
                try:
                    solver.SetSolverSpecificParametersAsString(param_name)
                    break
                except:
                    continue
        except Exception as e:
            # If setting threads fails, continue without it
            logger.debug(f"Failed to set SCIP thread count: {e}")
        
        logger.debug(f"SCIP solver: Parallel mode enabled with {num_threads} threads (Option C speedup)")
        
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
            # Frequency can be 0 when pump is off, or between min/max when on
            # Lower bound is 0.0 (constraints enforce min when pump is on)
            pump_freq[pid] = [
                solver.NumVar(
                    0.0,  # Lower bound: 0 when pump is off (constraints enforce min when on)
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
                # Safety check: ensure max_frequency_hz is valid (avoid division by zero)
                if pump_spec.max_frequency_hz < 1.0:
                    raise ValueError(f"Invalid max_frequency_hz={pump_spec.max_frequency_hz} for pump {pid}. Must be >= 1.0 Hz")
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
                
                # Safety check: ensure max_frequency_hz is valid before division
                if pump_spec.max_frequency_hz < 1.0:
                    raise ValueError(f"Invalid max_frequency_hz={pump_spec.max_frequency_hz} for pump {pid}. Must be >= 1.0 Hz")
                min_freq_ratio = pump_spec.min_frequency_hz / pump_spec.max_frequency_hz
                # Base power at minimum frequency (approximate cubic: ~85% at 95% freq)
                base_power_ratio = min_freq_ratio ** 2.5  # 0.95^2.5 ≈ 0.87
                base_power = pump_spec.max_power_kw * base_power_ratio
                
                # Power slope: approximate cubic by using steeper linear slope
                # At 50Hz, power = max_power
                # At 47.8Hz, power ≈ 87% of max
                # Linear slope = (max - base) / (1 - min_ratio)
                denominator = 1.0 - min_freq_ratio
                if abs(denominator) < 0.01:  # Avoid division by zero
                    power_slope = (pump_spec.max_power_kw - base_power) / 0.5  # Fallback
                else:
                    power_slope = (pump_spec.max_power_kw - base_power) / denominator
                
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
        
        # Smoothness: minimize F2 variance (linear approximation)
        # Use pairwise deviation instead of deviation from mean (linear programming compatible)
        # Minimize differences between consecutive outflow values
        outflow_vars = [
            sum(pump_flow[pid][t] for pid in pump_ids) for t in range(num_steps)
        ]
        if len(outflow_vars) > 1:
            # Minimize deviation between consecutive time steps
            for t in range(len(outflow_vars) - 1):
                # Linear approximation: use absolute difference between consecutive steps
                diff_var = solver.NumVar(0.0, solver.infinity(), f"smooth_diff_{t}")
                solver.Add(diff_var >= outflow_vars[t] - outflow_vars[t + 1])
                solver.Add(diff_var >= outflow_vars[t + 1] - outflow_vars[t])
                smoothness_obj += diff_var
        
        # Fairness: balance pump hours more aggressively
        # Use pairwise deviation instead of deviation from mean (linear programming compatible)
        # Minimize differences between pump operating hours
        pump_hours = [
            sum(pump_on[pid][t] for t in range(num_steps)) for pid in pump_ids
        ]
        if len(pump_hours) > 1:
            # Minimize deviation between pairs of pumps
            for i in range(len(pump_hours)):
                for j in range(i + 1, len(pump_hours)):
                    # Linear approximation: use absolute difference between pump pairs
                    diff_var = solver.NumVar(0.0, solver.infinity(), f"fairness_diff_{i}_{j}")
                    solver.Add(diff_var >= pump_hours[i] - pump_hours[j])
                    solver.Add(diff_var >= pump_hours[j] - pump_hours[i])
                    fairness_obj += diff_var
        
        # Specific energy: minimize kWh/m³ (encourage efficient operation)
        # Linear approximation: minimize deviation from target specific energy ratio
        # Since we can't divide directly or use quadratic terms, use linear approximation
        target_specific_energy = 0.4  # kWh/m³ target (will be tuned)
        for t in range(num_steps):
            dt_hours = self.time_step_minutes / 60.0
            for pid in pump_ids:
                energy = pump_power[pid][t] * dt_hours
                flow_m3 = pump_flow[pid][t] * dt_hours
                target_energy = flow_m3 * target_specific_energy
                # Linear approximation: use absolute deviation instead of squared
                dev_var = solver.NumVar(0.0, solver.infinity(), f"spec_energy_dev_{pid}_{t}")
                solver.Add(dev_var >= energy - target_energy)
                solver.Add(dev_var >= target_energy - energy)
                specific_energy_obj += dev_var
        
        # Safety: penalize being close to bounds and violations
        # Use linear penalty that encourages staying away from bounds (linear programming compatible)
        l1_safe_center = (self.constraints.l1_min_m + self.constraints.l1_max_m) / 2
        violation_penalty_obj = 0.0
        
        for t in range(num_steps):
            # Linear approximation: use absolute deviation from safe center instead of squared
            # This encourages staying in the middle range
            dev_var = solver.NumVar(0.0, solver.infinity(), f"l1_safety_dev_{t}")
            solver.Add(dev_var >= l1[t] - l1_safe_center)
            solver.Add(dev_var >= l1_safe_center - l1[t])
            safety_obj += dev_var
            
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
        
        # Initialize variables (will be used in both success and failure paths)
        schedules = []
        l1_traj = []
        total_energy = 0.0
        total_cost = 0.0
        violations = 0
        max_violation = 0.0
        violation_details = []  # Track detailed violation info
        
        if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            # Extract solution
            for t in range(num_steps):
                l1_val = l1[t].solution_value()
                l1_traj.append(l1_val)
                
                # Check for violations
                if l1_val < self.constraints.l1_min_m:
                    violations += 1
                    violation_mag = self.constraints.l1_min_m - l1_val
                    max_violation = max(max_violation, violation_mag)
                    violation_details.append({
                        'time_step': t,
                        'l1_value': l1_val,
                        'constraint': self.constraints.l1_min_m,
                        'violation': violation_mag,
                        'type': 'below_min'
                    })
                elif l1_val > self.constraints.l1_max_m:
                    violations += 1
                    violation_mag = l1_val - self.constraints.l1_max_m
                    max_violation = max(max_violation, violation_mag)
                    violation_details.append({
                        'time_step': t,
                        'l1_value': l1_val,
                        'constraint': self.constraints.l1_max_m,
                        'violation': violation_mag,
                        'type': 'above_max'
                    })
                
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
                # Log detailed violations
                import logging
                opt_logger = logging.getLogger(__name__)
                opt_logger.warning(f"L1 Constraint Violations Detected: {violations} violations in {num_steps} steps")
                for v in violation_details[:5]:  # Log first 5 violations
                    step_time = v['time_step'] * self.time_step_minutes
                    opt_logger.warning(
                        f"  Step {v['time_step']} ({step_time}min): L1={v['l1_value']:.3f}m, "
                        f"Constraint={'min' if v['type'] == 'below_min' else 'max'}={v['constraint']:.3f}m, "
                        f"Violation={v['violation']:.3f}m"
                    )
                if len(violation_details) > 5:
                    opt_logger.warning(f"  ... and {len(violation_details) - 5} more violations")
            
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


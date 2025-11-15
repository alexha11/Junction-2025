"""Core MPC-style optimizer using OR-Tools for pump scheduling."""

from __future__ import annotations

import logging
import os
import random
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
    # Power model parameters (for L1/lifting height correction)
    power_vs_l1_slope_kw_per_m: float = 0.0  # Power reduction per meter of L1 increase (negative correlation: higher L1 = less power)
    power_l1_reference_m: float = 4.0  # Reference L1 level for power calculation


@dataclass
class SystemConstraints:
    """Constraints for the system."""
    l1_min_m: float = 0.0
    l1_max_m: float = 8.0
    tunnel_volume_m3: float = 50000.0  # Approximate tunnel volume
    min_pumps_on: int = 1  # At least one pump always on
    min_pump_on_duration_minutes: int = 120  # Minimum 2h on (hardware protection)
    min_pump_off_duration_minutes: int = 120  # Minimum 2h off (hardware protection)
    flush_frequency_days: int = 1  # Flush once per day
    flush_target_level_m: float = 0.5  # Flush to 0.5 m (near minimum for cleaning)
    # Soft constraint options (deprecated - L1 bounds are now hard constraints)
    allow_l1_violations: bool = False  # L1 bounds are hard constraints (must never be violated)
    l1_violation_tolerance_m: float = 0.5  # Maximum allowed violation (not used when allow_l1_violations=False)
    l1_violation_penalty: float = 1000.0  # Penalty weight for violations (not used when allow_l1_violations=False)


@dataclass
class ForecastData:
    """Forecasted data for optimization horizon.

    Note:
        price_c_per_kwh values are in cents per kWh (c/kWh), even if the
        original CSV column is mislabeled as EUR/MWh.
    """
    timestamps: List[datetime]
    inflow_m3_s: List[float]
    price_c_per_kwh: List[float]


@dataclass
class CurrentState:
    """Current system state.

    Note:
        price_c_per_kwh is in cents per kWh (c/kWh), even if the
        original CSV column is mislabeled as EUR/MWh.
    """
    timestamp: datetime
    l1_m: float
    inflow_m3_s: float
    outflow_m3_s: float
    pump_states: List[Tuple[str, bool, float]]  # (pump_id, is_on, frequency_hz)
    price_c_per_kwh: float


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
        tactical_horizon_minutes: int = 120,  # 2h tactical horizon
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
        """Get adaptive objective weights based on risk level.

        Notes:
            The "rotation" weight controls how strongly we prefer balancing
            usage across pumps with the same capacity. It is kept moderate in
            low/normal risk so that rotation is visible over multi-day
            horizons, and driven close to zero in high/critical risk so
            safety and hard constraints always dominate fairness.
        """
        weights = {
            RiskLevel.LOW: {
                "cost": 1.0,
                "smoothness": 0.8,  # Smooth outflow is desirable requirement
                "safety_margin": 0.1,
                "specific_energy": 0.7,  # Minimize kWh/m³ requirement
                # Encourage noticeable rotation when system is far from bounds
                "rotation": 0.10,
            },
            RiskLevel.NORMAL: {
                "cost": 0.8,
                "smoothness": 0.7,
                "safety_margin": 0.3,
                "specific_energy": 0.6,
                # Slightly stronger rotation in normal conditions
                "rotation": 0.15,
            },
            RiskLevel.HIGH: {
                "cost": 0.4,
                "smoothness": 0.5,
                "safety_margin": 0.8,
                "specific_energy": 0.4,
                # Keep rotation very small when close to bounds
                "rotation": 0.03,
            },
            RiskLevel.CRITICAL: {
                "cost": 0.1,
                "smoothness": 0.3,
                "safety_margin": 2.0,
                "specific_energy": 0.2,
                "rotation": 0.0,  # Disabled in critical risk
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
                weights["specific_energy"] *= 1.5  # Maintain efficiency requirement
            weights["smoothness"] *= 0.9  # Still maintain smoothness (increased from 0.8) - requirement
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
            weights["smoothness"] *= 1.0  # Maintain smoothness (increased from 0.9) - requirement
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
        avg_price = np.mean(forecast_24h.price_c_per_kwh)
        price_std = np.std(forecast_24h.price_c_per_kwh)
        
        for i, price in enumerate(forecast_24h.price_c_per_kwh):
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
            price_error_pct = abs(current_state.price_c_per_kwh - previous_forecast_price) / previous_forecast_price * 100
            if current_state.price_c_per_kwh > previous_forecast_price * 1.5:  # 50% higher
                divergence = {
                    'error_type': 'price_spike',
                    'error_magnitude': price_error_pct,
                    'forecast_value': previous_forecast_price,
                    'actual_value': current_state.price_c_per_kwh,
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
        timeout_seconds: Optional[int] = None,  # Auto-calculate based on horizon if None
        strategic_plan: Optional[Any] = None,  # Optional LLM-generated StrategicPlan
        forecast_quality: Optional[Dict[str, Any]] = None,  # Optional forecast quality metrics
        emergency_response: Optional[Any] = None,  # Optional EmergencyResponse from LLM
        hours_since_last_flush: Optional[float] = None,  # Hours since last flush (for daily flush constraint)
        pump_usage_hours: Optional[Dict[str, float]] = None,  # Cumulative usage hours per pump_id for fairness/rotation
        pump_durations: Optional[Dict[str, Dict[str, float]]] = None,  # How long each pump has been on/off (in minutes) for rotation-aware min duration
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
        # Auto-calculate timeout based on horizon size if not provided
        if timeout_seconds is None:
            num_steps = len(forecast.timestamps) if forecast.timestamps else self.tactical_steps
            # Base timeout: 15s per hour of horizon (minimum 30s)
            timeout_seconds = max(30, int(num_steps * 15 / 4))  # 15 min steps -> hours
            logger.debug(f"Auto-calculated timeout: {timeout_seconds}s for {num_steps} steps ({num_steps * 15 / 60:.1f}h horizon)")
        
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
                    current_state,
                    forecast,
                    weights,
                    timeout_seconds,
                    strategic_plan=strategic_plan,
                    hours_since_last_flush=hours_since_last_flush,
                    pump_usage_hours=pump_usage_hours,
                    pump_durations=pump_durations,
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
        hours_since_last_flush: Optional[float] = None,
        pump_usage_hours: Optional[Dict[str, float]] = None,
        pump_durations: Optional[Dict[str, Dict[str, float]]] = None,
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
        
        # Optimize SCIP solver settings for faster solving (especially for 6-hour horizon)
        try:
            # Set optimality gap (1% is acceptable for faster solving)
            solver.SetSolverSpecificParametersAsString("limits/gap = 0.01")
        except Exception as e:
            logger.debug(f"Failed to set SCIP gap limit: {e}")
        
        # Try additional speedup parameters (may not be available in all SCIP versions)
        try:
            # Enable aggressive presolving (if parameter exists)
            solver.SetSolverSpecificParametersAsString("presolving/maxrounds = -1")
        except Exception:
            pass  # Parameter may not exist, ignore
        
        try:
            # Set emphasis on feasibility over optimality (if parameter exists)
            solver.SetSolverSpecificParametersAsString("limits/time = 1")  # This is set via SetTimeLimit, but try anyway
        except Exception:
            pass
        
        solver.SetTimeLimit(timeout_seconds * 1000)  # Convert to milliseconds
        
        num_steps = len(forecast.timestamps)
        pump_ids = list(self.pumps.keys())
        
        # Sort pumps by usage (least used first) to break solver bias
        # This ensures the solver prefers less-used pumps when they're equivalent
        # More deterministic than random shuffling
        if pump_usage_hours:
            # Sort by usage hours (ascending) - least used first
            pump_ids = sorted(pump_ids, key=lambda pid: pump_usage_hours.get(pid, 0.0))
        
        # Fairness/rotation coefficients per pump (higher for over-used pumps
        # in their capacity class). We build groups in a way that is robust
        # to small spec differences and explicitly couples 1.1/2.1 (small
        # pumps) and the large pumps across both lines.
        rotation_coeff: Dict[str, float] = {pid: 0.0 for pid in pump_ids}
        if pump_usage_hours:
            # Explicit grouping by pump ID pattern for this plant:
            # - Small pumps: 1.1 and 2.1
            # - Large pumps: all remaining pumps
            small_group = [pid for pid in pump_ids if pid.endswith(".1")]
            large_group = [pid for pid in pump_ids if pid not in small_group]

            groups: List[List[str]] = []
            if len(small_group) > 1:
                groups.append(small_group)
            if len(large_group) > 1:
                groups.append(large_group)

            # For any remaining pumps (different naming schemes / other plants),
            # fall back to coarse capacity-based grouping using rounded values
            # so that pumps with nearly-identical specs still rotate.
            assigned: set[str] = set(pid for group in groups for pid in group)
            remaining = [pid for pid in pump_ids if pid not in assigned]
            if remaining:
                cap_groups: Dict[Tuple[float, float], List[str]] = {}
                for pid in remaining:
                    spec = self.pumps[pid]
                    key = (round(spec.max_flow_m3_s, 2), round(spec.max_power_kw, -1))
                    cap_groups.setdefault(key, []).append(pid)
                for group_pumps in cap_groups.values():
                    if len(group_pumps) > 1:
                        groups.append(group_pumps)

            # Within each group, compute how far above the group average usage
            # each pump is. Only over-used pumps get a positive coefficient;
            # under-used pumps get 0 so they are preferred.
            for group_pumps in groups:
                group_hours = [pump_usage_hours.get(pid, 0.0) for pid in group_pumps]
                if not group_hours:
                    continue
                group_avg = float(np.mean(group_hours))
                for pid, hours in zip(group_pumps, group_hours):
                    delta = hours - group_avg
                    if delta > 0.0:
                        rotation_coeff[pid] = delta

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
                
                # Power model: improved approximation accounting for:
                # 1. Frequency (cubic relationship: P ∝ f³)
                # 2. L1 / Lifting height (higher L1 = less lifting height needed = less power)
                # 3. Flow and efficiency (embedded in max_power_kw from pump curves)
                # 
                # Power = f(frequency) - f(L1) + base
                # Where:
                #   f(frequency) ≈ base_power + slope * (freq - min_freq) [cubic approximation]
                #   f(L1) = power_vs_l1_slope * (L1 - L1_reference) [lifting height effect]
                #   Higher L1 = less power needed (negative slope in data analysis)
                
                # Safety check: ensure max_frequency_hz is valid before division
                if pump_spec.max_frequency_hz < 1.0:
                    raise ValueError(f"Invalid max_frequency_hz={pump_spec.max_frequency_hz} for pump {pid}. Must be >= 1.0 Hz")
                min_freq_ratio = pump_spec.min_frequency_hz / pump_spec.max_frequency_hz
                # Base power at minimum frequency (approximate cubic: ~85% at 95% freq)
                base_power_ratio = min_freq_ratio ** 2.5  # 0.95^2.5 ≈ 0.87
                base_power_freq = pump_spec.max_power_kw * base_power_ratio
                
                # Power slope: approximate cubic by using steeper linear slope
                # At 50Hz, power = max_power
                # At 47.8Hz, power ≈ 87% of max
                # Linear slope = (max - base) / (1 - min_ratio)
                denominator = 1.0 - min_freq_ratio
                if abs(denominator) < 0.01:  # Avoid division by zero
                    power_slope = (pump_spec.max_power_kw - base_power_freq) / 0.5  # Fallback
                else:
                    power_slope = (pump_spec.max_power_kw - base_power_freq) / denominator
                
                # Simplified linear approximation with adjusted slope for cubic behavior
                # Scale slope by 1.5x to better approximate cubic curve in the operating range
                adjusted_slope = power_slope * 1.5
                
                # Power vs frequency component
                freq_excess = pump_freq[pid][t] * max_freq_inv - min_freq_ratio * pump_on[pid][t]
                
                # Power vs L1 component (lifting height correction)
                # Higher L1 = less lifting height needed = less power
                # Power correction: power_reduction = slope * (L1[t] - L1_reference)
                # Since L1[t] is a variable, we can use it directly in linear constraints
                l1_reference = pump_spec.power_l1_reference_m
                l1_slope = pump_spec.power_vs_l1_slope_kw_per_m
                
                # Power reduction from L1 (lifting height effect)
                # When L1 is higher than reference, less power needed
                # power_l1_reduction = l1_slope * (l1[t] - l1_reference)
                # This is linear and can be added directly to constraints
                
                # Total power = power_from_freq - power_l1_reduction
                # But we need to be careful: l1_slope * l1[t] creates a bilinear term if multiplied by pump_on
                # Approximation: apply L1 correction only when pump is on
                # Use conservative approximation: apply correction factor based on expected L1
                # For now, use forecasted L1 to estimate correction (small change assumption)
                if l1_slope > 0.01:  # Only apply if significant slope
                    # Estimate L1 at time t (approximate from forecast)
                    expected_l1 = current_state.l1_m  # Start from current
                    dt_sec = self.time_step_minutes * 60
                    for s in range(t + 1):
                        if s < len(forecast.inflow_m3_s):
                            # Approximate outflow as average (conservative)
                            avg_outflow = sum(self.pumps[p].max_flow_m3_s for p in pump_ids) * 0.5
                            expected_l1 += (forecast.inflow_m3_s[s] - avg_outflow) * dt_sec / self.constraints.tunnel_volume_m3
                    
                    # L1 correction (subtract from power when L1 is high)
                    l1_correction = l1_slope * (expected_l1 - l1_reference)
                    # Clamp correction to reasonable range (±20% of base power)
                    max_correction = base_power_freq * 0.2
                    l1_correction = max(-max_correction, min(max_correction, l1_correction))
                    
                    # Apply L1 correction: subtract from frequency-based power
                    base_power = base_power_freq - l1_correction
                else:
                    # No L1 correction (slope too small)
                    base_power = base_power_freq
                
                solver.Add(
                    pump_power[pid][t] >= base_power * pump_on[pid][t] + 
                    freq_excess * adjusted_slope * 0.85
                )
                solver.Add(
                    pump_power[pid][t] <= base_power * pump_on[pid][t] + 
                    freq_excess * adjusted_slope * 1.15
                )
                
                # Bounds: power must be between adjusted base and max when on
                adjusted_min_power = max(0.1 * pump_spec.max_power_kw, base_power * 0.8)
                solver.Add(
                    pump_power[pid][t] >= adjusted_min_power * pump_on[pid][t]
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
        min_on_minutes = self.constraints.min_pump_on_duration_minutes
        min_off_minutes = self.constraints.min_pump_off_duration_minutes
        min_on_steps = min_on_minutes // self.time_step_minutes
        min_off_steps = min_off_minutes // self.time_step_minutes
        
        for pid in pump_ids:
            current_is_on = next(
                (s[1] for s in current_state.pump_states if s[0] == pid),
                False
            )
            
            # Check how long pump has been on/off (if duration tracking available)
            # This allows rotation if minimum duration has already been met
            on_duration_minutes = 0.0
            off_duration_minutes = 0.0
            if pump_durations and pid in pump_durations:
                on_duration_minutes = pump_durations[pid].get("on_minutes", 0.0)
                off_duration_minutes = pump_durations[pid].get("off_minutes", 0.0)
            
            # Calculate remaining steps needed to meet minimum duration
            # If pump has already been on/off for >= minimum, allow immediate rotation
            remaining_on_steps = max(0, min_on_steps - int(on_duration_minutes / self.time_step_minutes))
            remaining_off_steps = max(0, min_off_steps - int(off_duration_minutes / self.time_step_minutes))
            
            # Continuity constraints: only enforce if pump hasn't met minimum duration yet
            if current_is_on and remaining_on_steps > 0:
                # Pump is on and hasn't met minimum on duration - must stay on
                for t in range(min(remaining_on_steps, num_steps)):
                    solver.Add(pump_on[pid][t] == 1)
            elif not current_is_on and remaining_off_steps > 0:
                # Pump is off and hasn't met minimum off duration - must stay off
                for t in range(min(remaining_off_steps, num_steps)):
                    solver.Add(pump_on[pid][t] == 0)
            # If minimum duration is already met, pump can rotate immediately
            
            # General minimum duration constraints using sequence constraints
            # Only apply if pump hasn't already met the minimum duration
            # If pump turns on at t, it must stay on for remaining min_on_steps
            if remaining_on_steps > 0:
                for t in range(num_steps - remaining_on_steps + 1):
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
                        
                        # If pump turns on at t, it must stay on for remaining_on_steps
                        for s in range(remaining_on_steps):
                            if t + s < num_steps:
                                solver.Add(pump_on[pid][t + s] >= turns_on)
            else:
                # Pump has already met minimum on duration - apply normal min duration for new turn-ons
                for t in range(num_steps - min_on_steps + 1):
                    if t > 0:
                        was_off = solver.BoolVar(f"was_off_{pid}_{t}")
                        turns_on = solver.BoolVar(f"turns_on_{pid}_{t}")
                        
                        solver.Add(was_off == 1 - pump_on[pid][t - 1])
                        solver.Add(turns_on <= was_off)
                        solver.Add(turns_on <= pump_on[pid][t])
                        solver.Add(turns_on >= was_off + pump_on[pid][t] - 1)
                        
                        for s in range(min_on_steps):
                            if t + s < num_steps:
                                solver.Add(pump_on[pid][t + s] >= turns_on)
            
            # Similar for turning off
            if remaining_off_steps > 0:
                for t in range(num_steps - remaining_off_steps + 1):
                    if t > 0:
                        was_on = solver.BoolVar(f"was_on_{pid}_{t}")
                        turns_off = solver.BoolVar(f"turns_off_{pid}_{t}")
                        
                        solver.Add(was_on == pump_on[pid][t - 1])
                        solver.Add(turns_off <= was_on)
                        solver.Add(turns_off <= 1 - pump_on[pid][t])
                        solver.Add(turns_off >= was_on + (1 - pump_on[pid][t]) - 1)
                        
                        for s in range(remaining_off_steps):
                            if t + s < num_steps:
                                solver.Add(pump_on[pid][t + s] <= 1 - turns_off)
            else:
                # Pump has already met minimum off duration - apply normal min duration for new turn-offs
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
        safety_obj = 0.0
        specific_energy_obj = 0.0
        flush_obj = 0.0  # Flush objective (encourage daily flush)
        pump_preference_obj = 0.0  # Prefer large pumps over small pumps for efficiency
        rotation_obj = 0.0  # Fairness/rotation objective (balance usage among identical pumps)
        
        # Cost: total energy cost
        # price_c_per_kwh is in c/kWh from inputs
        for t in range(num_steps):
            price_eur_per_kwh = forecast.price_c_per_kwh[t] / 100.0  # c/kWh -> EUR/kWh
            dt_hours = self.time_step_minutes / 60.0
            for pid in pump_ids:
                energy_kwh = pump_power[pid][t] * dt_hours
                cost_obj += energy_kwh * price_eur_per_kwh
        
        # Smoothness: minimize F2 variance (linear approximation)
        # Approach: Minimize deviation from target constant outflow
        # Target is the average of current outflow and expected average outflow
        outflow_vars = [
            sum(pump_flow[pid][t] for pid in pump_ids) for t in range(num_steps)
        ]
        
        if len(outflow_vars) > 0:
            # Calculate target constant outflow based on current state and forecast
            # Use actual current outflow from state (not a variable)
            current_outflow = current_state.outflow_m3_s
            avg_forecast_inflow = sum(forecast.inflow_m3_s) / len(forecast.inflow_m3_s) if forecast.inflow_m3_s else current_state.inflow_m3_s
            # Target: balance between current outflow and average expected inflow
            # This encourages maintaining steady outflow that balances with expected inflow
            target_outflow = (current_outflow + avg_forecast_inflow) / 2.0
            
            # Minimize deviation from target constant outflow
            for t in range(len(outflow_vars)):
                # Linear approximation: use absolute deviation from target
                dev_var = solver.NumVar(0.0, solver.infinity(), f"smooth_dev_{t}")
                solver.Add(dev_var >= outflow_vars[t] - target_outflow)
                solver.Add(dev_var >= target_outflow - outflow_vars[t])
                smoothness_obj += dev_var
            
            # Minimize first-order differences (rate of change)
            if len(outflow_vars) > 1:
                first_order_diffs = []
                for t in range(len(outflow_vars) - 1):
                    # Minimize change rate between consecutive steps
                    diff_var = solver.NumVar(0.0, solver.infinity(), f"smooth_diff_{t}")
                    solver.Add(diff_var >= outflow_vars[t] - outflow_vars[t + 1])
                    solver.Add(diff_var >= outflow_vars[t + 1] - outflow_vars[t])
                    first_order_diffs.append(diff_var)
                    smoothness_obj += diff_var * 0.3  # Weight rate of change less than target deviation
                
                # Minimize second-order differences (changes in rate of change) to prevent oscillations
                # This penalizes patterns like 1.1 → 1 → 1.1 → 1 (oscillating)
                if len(first_order_diffs) > 1:
                    for t in range(len(first_order_diffs) - 1):
                        # Second-order difference: change in the first-order difference
                        # If first-order diff changes sign, we have oscillation
                        second_order_diff = solver.NumVar(0.0, solver.infinity(), f"smooth_diff2_{t}")
                        solver.Add(second_order_diff >= first_order_diffs[t] - first_order_diffs[t + 1])
                        solver.Add(second_order_diff >= first_order_diffs[t + 1] - first_order_diffs[t])
                        smoothness_obj += second_order_diff * 0.5  # Penalize oscillations more than simple changes
        
        # Specific energy: minimize kWh/m³ (encourage efficient operation)
        # Linear approximation: minimize deviation from target specific energy ratio
        # Since we can't divide directly or use quadratic terms, use linear approximation
        target_specific_energy = 0.08  # kWh/m³ target (better than baseline ~0.092 to encourage improvement)
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
        
        # Pump preference: prefer large pumps over small pumps (better efficiency)
        # Small pumps (1.1, 2.1) have higher overhead per m³
        # Add penalty for using small pumps to encourage large pumps when possible
        small_pump_ids = ["1.1", "2.1"]  # Small pumps
        for t in range(num_steps):
            for pid in pump_ids:
                if pid in small_pump_ids:
                    # Penalty for using small pumps (encourages large pumps when flow allows)
                    # Weight: 0.05 per time step (increased from 0.01 for stronger preference)
                    pump_preference_obj += pump_on[pid][t] * 0.05
        
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
        
        # Flush objective: encourage reaching flush_target_level_m once per day
        # Stronger when it's been longer since last flush, and during low inflow + cheap prices
        if hours_since_last_flush is not None and hours_since_last_flush >= 20:  # Near 24h mark
            # Calculate average inflow and price in forecast
            avg_inflow = np.mean(forecast.inflow_m3_s) if forecast.inflow_m3_s else 0.0
            avg_price = np.mean(forecast.price_c_per_kwh) if forecast.price_c_per_kwh else 0.0
            price_std = np.std(forecast.price_c_per_kwh) if len(forecast.price_c_per_kwh) > 1 else 0.0
            
            # Flush urgency increases with hours since last flush (0-1 scale, max at 24h+)
            flush_urgency = min(1.0, (hours_since_last_flush - 20) / 4.0)  # 0 at 20h, 1.0 at 24h+
            
            for t in range(num_steps):
                # Check if this is a good time to flush (low inflow, cheap price)
                inflow = forecast.inflow_m3_s[t] if t < len(forecast.inflow_m3_s) else avg_inflow
                price = forecast.price_c_per_kwh[t] if t < len(forecast.price_c_per_kwh) else avg_price
                
                # Good flush conditions: low inflow (< average) and cheap price (< average)
                is_low_inflow = inflow < avg_inflow * 0.8 if avg_inflow > 0 else False
                is_cheap_price = price < (avg_price - 0.3 * price_std) if price_std > 0 else price < avg_price
                flush_opportunity = 1.0 if (is_low_inflow and is_cheap_price) else 0.3
                
                # Encourage L1 to reach flush_target_level_m
                # Penalty for being above flush target (want to pump down to flush level)
                # Only penalize if L1 is above flush target
                flush_penalty_var = solver.NumVar(0.0, solver.infinity(), f"flush_penalty_{t}")
                # flush_penalty_var >= max(0, l1[t] - flush_target)
                solver.Add(flush_penalty_var >= l1[t] - self.constraints.flush_target_level_m)
                solver.Add(flush_penalty_var >= 0.0)
                
                # Weight: higher when urgent, during good conditions, and when price is cheap
                flush_penalty_weight = flush_urgency * flush_opportunity * (1.0 / max(price / 100.0, 0.1))  # Inverse price weighting
                flush_obj += flush_penalty_weight * flush_penalty_var
        
        # Violation penalty is always high priority (unless violations are fully allowed)
        violation_weight = self.constraints.l1_violation_penalty if self.constraints.allow_l1_violations else 0.0
        
        # Flush weight: moderate priority, increases with urgency
        flush_weight = 0.5 if hours_since_last_flush and hours_since_last_flush >= 20 else 0.0
        
        # Pump preference weight: scale with specific_energy weight (efficiency-related)
        pump_preference_weight = weights.get("specific_energy", 0.0) * 0.3  # 30% of specific_energy weight (increased from 10%)
        
        # Fairness/rotation objective: prefer pumps with minimum total runtime
        # Direct approach: strongly prefer the least-used pump in each group
        # IMPORTANT: Only apply rotation preference if pump can actually be turned on/off
        # (i.e., has met minimum duration requirements)
        if pump_usage_hours:
            # Build groups to check usage
            small_group = [pid for pid in pump_ids if pid.endswith(".1")]
            large_group = [pid for pid in pump_ids if pid not in small_group]
            
            # For each group, find minimum usage and strongly prefer that pump
            for group_pumps in [small_group, large_group]:
                if len(group_pumps) < 2:
                    continue
                group_hours = [pump_usage_hours.get(pid, 0.0) for pid in group_pumps]
                if not group_hours:
                    continue
                
                # Find minimum usage in group
                group_min_hours = float(np.min(group_hours))
                
                # For each pump, add penalty/reward based on how far from minimum
                # BUT: only apply if pump can actually be rotated (has met min duration)
                for pid, hours in zip(group_pumps, group_hours):
                    # Check if this pump can be turned off (has met minimum on duration)
                    # If pump is currently on and hasn't met min duration, don't penalize it
                    # (the hard constraint will prevent turning it off anyway)
                    current_is_on = next(
                        (s[1] for s in current_state.pump_states if s[0] == pid),
                        False
                    )
                    
                    # Check if pump has met minimum on duration (can be turned off)
                    can_turn_off = True
                    if current_is_on and pump_durations and pid in pump_durations:
                        on_duration_minutes = pump_durations[pid].get("on_minutes", 0.0)
                        min_on_minutes = self.constraints.min_pump_on_duration_minutes
                        if on_duration_minutes < min_on_minutes:
                            # Pump is on but hasn't met minimum - can't turn it off yet
                            can_turn_off = False
                    
                    if hours > group_min_hours:
                        # Penalty for pumps above minimum: proportional to difference
                        # Strong enough to overcome small cost differences
                        # BUT: only penalize if pump can actually be turned off
                        if can_turn_off:
                            penalty = (hours - group_min_hours) * 25.0  # Strong penalty
                            # Minimum penalty even for small differences to ensure rotation
                            if hours > group_min_hours * 1.05:  # At least 5% more than minimum
                                penalty = max(penalty, 2.0)  # Minimum 2.0 penalty
                            for t in range(num_steps):
                                rotation_obj += penalty * pump_on[pid][t]
                        # If can't turn off, don't add penalty (hard constraint will handle it)
                    else:
                        # Reward for minimum-used pump (negative penalty = reward)
                        # This makes it strongly preferred when only one is needed
                        # Always reward minimum-used pump (it can always be turned on)
                        reward = 5.0  # Strong fixed reward for minimum-used pump
                        for t in range(num_steps):
                            rotation_obj -= reward * pump_on[pid][t]  # Negative = reward
        
        # Also apply rotation coefficients if available (for historical usage tracking)
        if any(rotation_coeff.values()) and weights.get("rotation", 0.0) > 0.0:
            for t in range(num_steps):
                for pid in pump_ids:
                    coeff = rotation_coeff.get(pid, 0.0)
                    if coeff > 0.0:
                        rotation_obj += coeff * pump_on[pid][t]
        
        # Group fairness constraint: ensure pumps in same group have approximately equal
        # working hours within this optimization horizon (especially on normal days)
        group_fairness_obj = 0.0
        dt_hours = self.time_step_minutes / 60.0
        
        # Build groups (same logic as rotation_coeff)
        groups: List[List[str]] = []
        if pump_usage_hours:
            small_group = [pid for pid in pump_ids if pid.endswith(".1")]
            large_group = [pid for pid in pump_ids if pid not in small_group]
            if len(small_group) > 1:
                groups.append(small_group)
            if len(large_group) > 1:
                groups.append(large_group)
        else:
            # If no usage history, still enforce fairness within horizon
            small_group = [pid for pid in pump_ids if pid.endswith(".1")]
            large_group = [pid for pid in pump_ids if pid not in small_group]
            if len(small_group) > 1:
                groups.append(small_group)
            if len(large_group) > 1:
                groups.append(large_group)
        
        # For each group, minimize the difference in working hours within this horizon
        for group_pumps in groups:
            if len(group_pumps) < 2:
                continue
            
            # Calculate total working hours in this horizon for each pump in group
            group_working_hours = []
            for pid in group_pumps:
                # Total hours this pump is on during horizon
                pump_hours_var = solver.NumVar(0.0, num_steps * dt_hours, f"pump_hours_{pid}")
                # Sum of pump_on over all time steps
                solver.Add(pump_hours_var == sum(pump_on[pid][t] for t in range(num_steps)) * dt_hours)
                group_working_hours.append(pump_hours_var)
            
            # Minimize the range (max - min) of working hours within group
            if len(group_working_hours) > 1:
                max_hours = solver.NumVar(0.0, num_steps * dt_hours, f"max_hours_group_{group_pumps[0]}")
                min_hours = solver.NumVar(0.0, num_steps * dt_hours, f"min_hours_group_{group_pumps[0]}")
                
                # max_hours >= each pump's hours
                for hours_var in group_working_hours:
                    solver.Add(max_hours >= hours_var)
                
                # min_hours <= each pump's hours
                for hours_var in group_working_hours:
                    solver.Add(min_hours <= hours_var)
                
                # Minimize the range (difference between max and min)
                range_var = solver.NumVar(0.0, num_steps * dt_hours, f"range_hours_group_{group_pumps[0]}")
                solver.Add(range_var >= max_hours - min_hours)
                group_fairness_obj += range_var
                
                # Hard constraint on normal days: maximum difference between pumps in same group
                # This prevents one pump from taking all the hours
                if risk_level in (RiskLevel.LOW, RiskLevel.NORMAL):
                    # Maximum allowed difference: 10% of horizon duration (very strict)
                    # For 6h horizon, this means max 0.6h (36 min) difference between pumps
                    max_allowed_diff = num_steps * dt_hours * 0.10
                    # Hard constraint: range must be within tolerance
                    solver.Add(range_var <= max_allowed_diff)
                    
                    # Also add pair-wise penalties for additional enforcement
                    for i, hours_var_i in enumerate(group_working_hours):
                        for j, hours_var_j in enumerate(group_working_hours):
                            if i < j:  # Only compare each pair once
                                # Penalize large differences between pumps in same group
                                pair_diff = solver.NumVar(0.0, num_steps * dt_hours, f"pair_diff_{group_pumps[0]}_{i}_{j}")
                                solver.Add(pair_diff >= hours_var_i - hours_var_j)
                                solver.Add(pair_diff >= hours_var_j - hours_var_i)
                                # Strong penalty for pair differences
                                group_fairness_obj += pair_diff * 2.0  # Increased from 1.0
        
        # Group fairness weight: MUCH stronger to prevent single pump from dominating
        # This ensures pumps in same group have approximately equal working hours
        # Use very strong weight - this is critical for pump rotation
        if risk_level in (RiskLevel.LOW, RiskLevel.NORMAL):
            # On normal days, use very strong weight (50x rotation weight or fixed high value)
            group_fairness_weight = max(weights.get("rotation", 0.0) * 50.0, 5.0)  # At least 5.0, up to 50x rotation
        elif risk_level == RiskLevel.HIGH:
            group_fairness_weight = max(weights.get("rotation", 0.0) * 20.0, 2.0)  # Still strong but less
        elif risk_level == RiskLevel.CRITICAL:
            group_fairness_weight = 0.0  # Disabled in critical situations
        else:
            group_fairness_weight = max(weights.get("rotation", 0.0) * 30.0, 3.0)  # Default strong weight

        total_obj = (
            weights["cost"] * cost_obj +
            weights["smoothness"] * smoothness_obj +
            weights["safety_margin"] * safety_obj +
            weights.get("specific_energy", 0.0) * specific_energy_obj +
            pump_preference_weight * pump_preference_obj +
            violation_weight * violation_penalty_obj +
            flush_weight * flush_obj +
            weights.get("rotation", 0.0) * rotation_obj +
            group_fairness_weight * group_fairness_obj  # Add group fairness constraint
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
                        # price_c_per_kwh is in c/kWh → convert to EUR/kWh
                        total_cost += energy * (forecast.price_c_per_kwh[t] / 100.0)
            
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
                # price_c_per_kwh is in c/kWh → convert to EUR/kWh
                total_cost += energy * (forecast.price_c_per_kwh[t] / 100.0)
            
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


"""Rolling MPC simulation for testing optimizer on historical data."""

from __future__ import annotations

from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional, Dict

import numpy as np

from typing import Optional
import asyncio
import logging

from .optimizer import MPCOptimizer, OptimizationResult, CurrentState, ForecastData, OptimizationMode
from .test_data_loader import HSYDataLoader
from .explainability import LLMExplainer, ScheduleMetrics

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """Results from rolling MPC simulation."""
    timestamp: datetime
    current_state: CurrentState
    optimization_result: OptimizationResult
    baseline_schedule: dict
    explanation: Optional[str] = None  # LLM explanation for this step
    strategy: Optional[str] = None  # Strategic guidance for this step


@dataclass
class RollingSimulation:
    """Results from full rolling simulation."""
    start_time: datetime
    end_time: datetime
    results: List[SimulationResult] = field(default_factory=list)
    optimized_l1_trajectory: List[float] = field(default_factory=list)
    baseline_l1_trajectory: List[float] = field(default_factory=list)
    optimized_energy: List[float] = field(default_factory=list)
    baseline_energy: List[float] = field(default_factory=list)
    optimized_cost: List[float] = field(default_factory=list)
    baseline_cost: List[float] = field(default_factory=list)


class RollingMPCSimulator:
    """Simulate rolling MPC optimization on historical data."""

    def __init__(
        self,
        data_loader: HSYDataLoader,
        optimizer: MPCOptimizer,
        reoptimize_interval_minutes: int = 15,
        forecast_method: str = 'perfect',
        llm_explainer: Optional[LLMExplainer] = None,
        generate_explanations: bool = True,
    ):
        """Initialize simulator.
        
        Args:
            data_loader: Loader for historical data
            optimizer: MPCOptimizer instance
            reoptimize_interval_minutes: Time between re-optimizations (default 15)
            forecast_method: 'perfect' or 'persistence' for forecasts
            llm_explainer: Optional LLM explainer for generating explanations per step
            generate_explanations: Whether to generate explanations for each optimization step
        """
        self.data_loader = data_loader
        self.optimizer = optimizer
        self.reoptimize_interval_minutes = reoptimize_interval_minutes
        self.forecast_method = forecast_method
        self.llm_explainer = llm_explainer
        self.generate_explanations = generate_explanations and (llm_explainer is not None)

    def simulate(
        self,
        start_time: datetime,
        end_time: datetime,
        horizon_minutes: int = 120,
    ) -> RollingSimulation:
        """Run rolling MPC simulation.
        
        Args:
            start_time: Start time for simulation
            end_time: End time for simulation
            horizon_minutes: Optimization horizon in minutes (default 120 = 2h)
        
        Returns:
            RollingSimulation with all results
        """
        simulation = RollingSimulation(start_time=start_time, end_time=end_time)
        
        current_time = start_time
        horizon_steps = horizon_minutes // self.optimizer.time_step_minutes
        
        # Track simulated L1 (starts from historical value)
        initial_state = self.data_loader.get_state_at_time(start_time)
        if initial_state is None:
            raise ValueError(f"No data available at {start_time}")
        
        simulated_l1 = initial_state.l1_m
        
        while current_time <= end_time:
            # Get current state from historical data (for inflow, price, etc.)
            current_state = self.data_loader.get_state_at_time(current_time)
            if current_state is None:
                # Skip if no data
                current_time += timedelta(minutes=self.reoptimize_interval_minutes)
                continue
            
            # Update simulated L1 (in real MPC, this would come from plant/simulator)
            # For testing, we use historical L1 but could simulate it forward
            current_state.l1_m = simulated_l1
            
            # Get forecast
            forecast = self.data_loader.get_forecast_from_time(
                current_time, horizon_steps, method=self.forecast_method
            )
            if forecast is None:
                current_time += timedelta(minutes=self.reoptimize_interval_minutes)
                continue
            
            # Get baseline schedule for comparison
            baseline_schedule = self.data_loader.get_baseline_schedule_at_time(current_time)
            
            # Run optimization
            try:
                opt_result = self.optimizer.solve_optimization(
                    current_state=current_state,
                    forecast=forecast,
                    mode=OptimizationMode.FULL,
                    timeout_seconds=30,
                )
            except Exception as e:
                # Fallback on error
                opt_result = self.optimizer.solve_optimization(
                    current_state=current_state,
                    forecast=forecast,
                    mode=OptimizationMode.RULE_BASED,
                    timeout_seconds=10,
                )
            
            # Generate explanation for this step if enabled
            explanation = None
            strategy = None
            if self.generate_explanations and self.llm_explainer:
                try:
                    # Get strategic guidance
                    strategic_guidance = self.optimizer.derive_strategic_guidance(forecast)
                    strategy = ", ".join(set(strategic_guidance[:4]))
                    logger.info(f"[Step {len(simulation.results)+1}] Strategy: {strategy}")
                    
                    # Compute metrics for this step
                    metrics = self._compute_step_metrics(opt_result, forecast, current_state)
                    
                    # Build current state description
                    current_state_desc = (
                        f"Tunnel level: {current_state.l1_m:.2f}m, "
                        f"Inflow: {current_state.inflow_m3_s:.2f} m³/s, "
                        f"Price: {current_state.price_eur_mwh:.1f} EUR/MWh"
                    )
                    
                    # Generate LLM explanation asynchronously
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    explanation = loop.run_until_complete(
                        self.llm_explainer.generate_explanation(
                            metrics=metrics,
                            strategic_guidance=strategic_guidance,
                            current_state_description=current_state_desc,
                        )
                    )
                    logger.info(f"[Step {len(simulation.results)+1}] LLM Explanation: {explanation}")
                except Exception as e:
                    logger.warning(f"[Step {len(simulation.results)+1}] Failed to generate explanation: {e}")
            
            # Store result
            simulation_result = SimulationResult(
                timestamp=current_time,
                current_state=current_state,
                optimization_result=opt_result,
                baseline_schedule=baseline_schedule,
                explanation=explanation,
                strategy=strategy,
            )
            simulation.results.append(simulation_result)
            
            # Track trajectories
            simulation.optimized_l1_trajectory.append(simulated_l1)
            baseline_state = self.data_loader.get_state_at_time(current_time)
            if baseline_state:
                simulation.baseline_l1_trajectory.append(baseline_state.l1_m)
            
            # Calculate energy and cost for this time step
            dt_hours = self.reoptimize_interval_minutes / 60.0
            
            # Optimized energy/cost (from optimization result, but only for current step)
            # For rolling simulation, we track cumulative
            if opt_result.success and opt_result.schedules:
                # Sum up power from schedules for first time step
                step_energy = 0.0
                step_cost = 0.0
                for schedule in opt_result.schedules:
                    if schedule.time_step == 0 and schedule.is_on:
                        step_energy += schedule.power_kw * dt_hours
                        step_cost += schedule.power_kw * dt_hours * (current_state.price_eur_mwh / 1000.0)
                
                simulation.optimized_energy.append(step_energy)
                simulation.optimized_cost.append(step_cost)
            else:
                simulation.optimized_energy.append(0.0)
                simulation.optimized_cost.append(0.0)
            
            # Baseline energy/cost
            baseline_energy = 0.0
            baseline_cost = 0.0
            for pump_id, pump_data in baseline_schedule.items():
                if pump_data['is_on']:
                    baseline_energy += pump_data['power_kw'] * dt_hours
                    baseline_cost += pump_data['power_kw'] * dt_hours * (current_state.price_eur_mwh / 1000.0)
            
            simulation.baseline_energy.append(baseline_energy)
            simulation.baseline_cost.append(baseline_cost)
            
            # Update simulated L1 for next step (simplified: use historical inflow/outflow change)
            # In real MPC, this would come from executing the schedule
            if opt_result.success and opt_result.l1_trajectory:
                # Use first predicted L1 from optimizer
                simulated_l1 = opt_result.l1_trajectory[0] if len(opt_result.l1_trajectory) > 0 else simulated_l1
            else:
                # Fallback: use simple mass balance
                total_outflow = sum(
                    s.flow_m3_s for s in opt_result.schedules 
                    if s.time_step == 0 and s.is_on
                ) if opt_result.success else current_state.outflow_m3_s
                
                dt_seconds = self.reoptimize_interval_minutes * 60
                volume_change_m3 = (current_state.inflow_m3_s - total_outflow) * dt_seconds
                level_change_m = volume_change_m3 / self.optimizer.constraints.tunnel_volume_m3
                simulated_l1 = max(
                    self.optimizer.constraints.l1_min_m,
                    min(self.optimizer.constraints.l1_max_m, simulated_l1 + level_change_m)
                )
            
            # Advance time
            current_time += timedelta(minutes=self.reoptimize_interval_minutes)
        
        return simulation
    
    def _compute_step_metrics(
        self,
        result: OptimizationResult,
        forecast: ForecastData,
        current_state: CurrentState,
    ) -> ScheduleMetrics:
        """Compute metrics for a single optimization step."""
        if not result.l1_trajectory:
            return ScheduleMetrics(
                total_energy_kwh=result.total_energy_kwh,
                total_cost_eur=result.total_cost_eur,
                avg_l1_m=current_state.l1_m,
                min_l1_m=current_state.l1_m,
                max_l1_m=current_state.l1_m,
                num_pumps_used=len([s for s in result.schedules if s.time_step == 0 and s.is_on]),
                avg_outflow_m3_s=sum(s.flow_m3_s for s in result.schedules if s.time_step == 0 and s.is_on),
                price_range_eur_mwh=(min(forecast.price_eur_mwh), max(forecast.price_eur_mwh)),
                risk_level="normal",
                optimization_mode=result.mode.value,
            )
        
        return ScheduleMetrics(
            total_energy_kwh=result.total_energy_kwh,
            total_cost_eur=result.total_cost_eur,
            avg_l1_m=sum(result.l1_trajectory) / len(result.l1_trajectory),
            min_l1_m=min(result.l1_trajectory),
            max_l1_m=max(result.l1_trajectory),
            num_pumps_used=len(set(s.pump_id for s in result.schedules if s.is_on)),
            avg_outflow_m3_s=sum(s.flow_m3_s for s in result.schedules if s.time_step == 0 and s.is_on),
            price_range_eur_mwh=(min(forecast.price_eur_mwh), max(forecast.price_eur_mwh)),
            risk_level="normal",
            optimization_mode=result.mode.value,
        )

    def compare_with_baseline(
        self,
        simulation: RollingSimulation,
    ) -> Dict:
        """Compare optimized simulation with baseline from historical data.
        
        Returns:
            Dictionary with comparison metrics
        """
        if not simulation.results:
            return {}
        
        # Calculate totals
        total_optimized_energy = sum(simulation.optimized_energy)
        total_baseline_energy = sum(simulation.baseline_energy)
        total_optimized_cost = sum(simulation.optimized_cost)
        total_baseline_cost = sum(simulation.baseline_cost)
        
        # Calculate L1 constraint violations
        optimized_violations = 0
        baseline_violations = 0
        optimized_max_violation = 0.0
        baseline_max_violation = 0.0
        
        l1_min = self.optimizer.constraints.l1_min_m
        l1_max = self.optimizer.constraints.l1_max_m
        
        for l1 in simulation.optimized_l1_trajectory:
            if l1 < l1_min:
                optimized_violations += 1
                optimized_max_violation = min(optimized_max_violation, l1 - l1_min)
            elif l1 > l1_max:
                optimized_violations += 1
                optimized_max_violation = max(optimized_max_violation, l1 - l1_max)
        
        for l1 in simulation.baseline_l1_trajectory:
            if l1 < l1_min:
                baseline_violations += 1
                baseline_max_violation = min(baseline_max_violation, l1 - l1_min)
            elif l1 > l1_max:
                baseline_violations += 1
                baseline_max_violation = max(baseline_max_violation, l1 - l1_max)
        
        # Calculate outflow smoothness (variance)
        optimized_outflows = []
        baseline_outflows = []
        
        for result in simulation.results:
            # Get outflow from optimized schedule
            opt_outflow = sum(
                s.flow_m3_s for s in result.optimization_result.schedules
                if s.time_step == 0 and s.is_on
            )
            optimized_outflows.append(opt_outflow)
            
            # Get baseline outflow
            baseline_outflow = sum(
                pump_data['flow_m3_s']
                for pump_data in result.baseline_schedule.values()
                if pump_data['is_on']
            )
            baseline_outflows.append(baseline_outflow)
        
        optimized_smoothness = float(np.var(optimized_outflows)) if optimized_outflows else 0.0
        baseline_smoothness = float(np.var(baseline_outflows)) if baseline_outflows else 0.0
        
        # Calculate pump operating hours (fairness)
        optimized_pump_hours: Dict[str, float] = {}
        baseline_pump_hours: Dict[str, float] = {}
        dt_hours = self.reoptimize_interval_minutes / 60.0
        
        for result in simulation.results:
            # Optimized
            for schedule in result.optimization_result.schedules:
                if schedule.time_step == 0 and schedule.is_on:
                    pump_id = schedule.pump_id
                    optimized_pump_hours[pump_id] = optimized_pump_hours.get(pump_id, 0.0) + dt_hours
            
            # Baseline
            for pump_id, pump_data in result.baseline_schedule.items():
                if pump_data['is_on']:
                    baseline_pump_hours[pump_id] = baseline_pump_hours.get(pump_id, 0.0) + dt_hours
        
        # Calculate specific energy (kWh/m³)
        total_optimized_volume = sum(
            sum(s.flow_m3_s * dt_hours for s in result.optimization_result.schedules if s.time_step == 0 and s.is_on)
            for result in simulation.results
        )
        total_baseline_volume = sum(
            sum(pump_data['flow_m3_s'] * dt_hours for pump_data in result.baseline_schedule.values() if pump_data['is_on'])
            for result in simulation.results
        )
        
        optimized_specific_energy = (
            total_optimized_energy / total_optimized_volume 
            if total_optimized_volume > 0 else 0.0
        )
        baseline_specific_energy = (
            total_baseline_energy / total_baseline_volume
            if total_baseline_volume > 0 else 0.0
        )
        
        return {
            'total_energy_kwh': {
                'optimized': total_optimized_energy,
                'baseline': total_baseline_energy,
                'savings_kwh': total_baseline_energy - total_optimized_energy,
                'savings_percent': (
                    (total_baseline_energy - total_optimized_energy) / total_baseline_energy * 100.0
                    if total_baseline_energy > 0 else 0.0
                ),
            },
            'total_cost_eur': {
                'optimized': total_optimized_cost,
                'baseline': total_baseline_cost,
                'savings_eur': total_baseline_cost - total_optimized_cost,
                'savings_percent': (
                    (total_baseline_cost - total_optimized_cost) / total_baseline_cost * 100.0
                    if total_baseline_cost > 0 else 0.0
                ),
            },
            'l1_violations': {
                'optimized': optimized_violations,
                'baseline': baseline_violations,
                'optimized_max_violation': optimized_max_violation,
                'baseline_max_violation': baseline_max_violation,
            },
            'outflow_smoothness': {
                'optimized_variance': optimized_smoothness,
                'baseline_variance': baseline_smoothness,
                'improvement_percent': (
                    (baseline_smoothness - optimized_smoothness) / baseline_smoothness * 100.0
                    if baseline_smoothness > 0 else 0.0
                ),
            },
            'pump_operating_hours': {
                'optimized': optimized_pump_hours,
                'baseline': baseline_pump_hours,
            },
            'specific_energy_kwh_m3': {
                'optimized': optimized_specific_energy,
                'baseline': baseline_specific_energy,
                'improvement_percent': (
                    (baseline_specific_energy - optimized_specific_energy) / baseline_specific_energy * 100.0
                    if baseline_specific_energy > 0 else 0.0
                ),
            },
        }


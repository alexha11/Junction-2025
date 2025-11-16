"""Demo simulator with WebSocket support for real-time updates."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any, Union, Awaitable

from .test_simulator import RollingMPCSimulator, RollingSimulation, SimulationResult
from .test_data_loader import HSYDataLoader
from .optimizer import MPCOptimizer, ForecastData
from .explainability import LLMExplainer

logger = logging.getLogger(__name__)


class DemoSimulator:
    """Demo simulator that streams updates via callback for WebSocket broadcasting."""
    
    def __init__(
        self,
        data_loader: HSYDataLoader,
        optimizer: MPCOptimizer,
        reoptimize_interval_minutes: int = 15,
        update_callback: Optional[Union[Callable[[Dict[str, Any]], None], Callable[[Dict[str, Any]], Awaitable[None]]]] = None,
        llm_explainer: Optional[LLMExplainer] = None,
        generate_explanations: bool = True,
        generate_strategic_plan: bool = True,
    ):
        """Initialize demo simulator.
        
        Args:
            data_loader: Loader for historical data
            optimizer: MPCOptimizer instance
            reoptimize_interval_minutes: Time between re-optimizations (default 15)
            update_callback: Optional callback function to send updates (for WebSocket)
            llm_explainer: Optional LLM explainer for generating explanations
            generate_explanations: Whether to generate per-step explanations (default: True)
            generate_strategic_plan: Whether to generate 24h strategic plans (default: True)
        """
        self.data_loader = data_loader
        self.optimizer = optimizer
        self.reoptimize_interval_minutes = reoptimize_interval_minutes
        self.update_callback = update_callback
        
        # Create underlying simulator with LLM support
        self.simulator = RollingMPCSimulator(
            data_loader=data_loader,
            optimizer=optimizer,
            reoptimize_interval_minutes=reoptimize_interval_minutes,
            llm_explainer=llm_explainer,
            generate_explanations=generate_explanations and (llm_explainer is not None),
            generate_strategic_plan=generate_strategic_plan and (llm_explainer is not None),
            suppress_prefix=True,
        )
    
    def _format_result_as_json(self, result: SimulationResult, step_index: int, total_steps: int, forecast: Optional[ForecastData] = None, start_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Format a simulation result as JSON for frontend."""
        opt_result = result.optimization_result
        
        # Calculate total running time from all pump schedules in the horizon
        # For this step, sum up running time across all time steps in the schedule
        dt_hours = self.reoptimize_interval_minutes / 60.0
        
        # Running time in this optimization horizon
        # Group by pump_id and count unique time steps where pump is ON
        horizon_per_pump_running_time_hours: Dict[str, float] = {}
        
        if opt_result.schedules:
            # Group schedules by pump_id and count time steps where pump is ON
            pump_time_steps: Dict[str, set] = {}
            for schedule in opt_result.schedules:
                if schedule.is_on:
                    pid = schedule.pump_id
                    if pid not in pump_time_steps:
                        pump_time_steps[pid] = set()
                    pump_time_steps[pid].add(schedule.time_step)
            
            # Calculate running time per pump (number of time steps * dt_hours)
            for pid, time_steps in pump_time_steps.items():
                horizon_per_pump_running_time_hours[pid] = len(time_steps) * dt_hours
        
        horizon_total_running_time_hours = sum(horizon_per_pump_running_time_hours.values())
        
        # Get cumulative running time from simulator (across entire simulation)
        cumulative_total_running_time_hours = 0.0
        cumulative_per_pump_running_time_hours: Dict[str, float] = {}
        if hasattr(self.simulator, 'pump_usage_hours') and self.simulator.pump_usage_hours:
            cumulative_per_pump_running_time_hours = dict(self.simulator.pump_usage_hours)
            cumulative_total_running_time_hours = sum(cumulative_per_pump_running_time_hours.values())
        
        # Format pump schedules - send all schedules (not just current step)
        schedules = []
        if opt_result.schedules:
            for schedule in opt_result.schedules:
                schedules.append({
                    "pump_id": schedule.pump_id,
                    "time_step": schedule.time_step,
                    "is_on": schedule.is_on,
                    "frequency_hz": schedule.frequency_hz,
                    "flow_m3_s": schedule.flow_m3_s,
                    "power_kw": schedule.power_kw,
                })
        
        # Calculate L1 volume from L1 level (volume = level * cross_section_area)
        # Cross-section area = TUNNEL_VOLUME / MAX_LEVEL = 50000 / 8 = 6250 m²
        TUNNEL_VOLUME_M3 = 50000.0
        MAX_LEVEL_M = 8.0
        cross_section_area_m2 = TUNNEL_VOLUME_M3 / MAX_LEVEL_M
        l1_volume_m3 = result.current_state.l1_m * cross_section_area_m2
        
        # Try to get L2 from digital twin or data (may not be available)
        # For now, we'll use None if not available, or try to get from baseline state
        l2_m = None
        if hasattr(result, 'baseline_state') and result.baseline_state:
            # If we have baseline state, check for L2
            if hasattr(result.baseline_state, 'l2_m'):
                l2_m = result.baseline_state.l2_m
        
        # Format current state
        state = {
            "timestamp": result.current_state.timestamp.isoformat(),
            "l1_m": result.current_state.l1_m,  # L1 level in meters
            "l1_volume_m3": l1_volume_m3,  # L1 volume in m³ (calculated)
            "l2_m": l2_m,  # L2 level in meters (if available)
            "inflow_m3_s": result.current_state.inflow_m3_s,
            "outflow_m3_s": result.current_state.outflow_m3_s,
            "price_c_per_kwh": result.current_state.price_c_per_kwh,
            "pumps": [
                {
                    "pump_id": pump_id,
                    "state": "on" if is_on else "off",
                    "frequency_hz": freq,
                }
                for pump_id, is_on, freq in result.current_state.pump_states
            ],
        }
        
        # Format forecast (use passed forecast or result.forecast if available)
        # Send full forecast (not just first 8 steps) for better visualization
        forecast_data = None
        if forecast:
            forecast_data = {
                "timestamps": [ts.isoformat() for ts in forecast.timestamps],
                "inflow_m3_s": forecast.inflow_m3_s,
                "price_c_per_kwh": forecast.price_c_per_kwh,
            }
        elif hasattr(result, 'forecast') and result.forecast:
            forecast_data = {
                "timestamps": [ts.isoformat() for ts in result.forecast.timestamps],
                "inflow_m3_s": result.forecast.inflow_m3_s,
                "price_c_per_kwh": result.forecast.price_c_per_kwh,
            }
        else:
            forecast_data = {
                "timestamps": [],
                "inflow_m3_s": [],
                "price_c_per_kwh": [],
            }
        
        # Calculate baseline cost and energy for this step
        baseline_cost_eur = 0.0
        baseline_energy_kwh = 0.0
        baseline_outflow_m3_s = 0.0  # Total outflow (sum of all pumps)
        if result.baseline_schedule:
            dt_hours = self.reoptimize_interval_minutes / 60.0
            for pump_id, pump_data in result.baseline_schedule.items():
                if pump_data.get('is_on', False):
                    power_kw = pump_data.get('power_kw', 0.0)
                    flow_m3_s = pump_data.get('flow_m3_s', 0.0)
                    baseline_energy_kwh += power_kw * dt_hours
                    baseline_cost_eur += power_kw * dt_hours * (result.current_state.price_c_per_kwh / 100.0)
                    baseline_outflow_m3_s += flow_m3_s  # Sum all pump flows
        
        # Calculate optimized outflow for smoothness (time series across horizon)
        optimized_outflow_m3_s = []
        if opt_result.schedules:
            # Group schedules by time_step and sum outflow per time step
            max_time_step = max((s.time_step for s in opt_result.schedules), default=-1)
            for t in range(max_time_step + 1):
                outflow_t = sum(s.flow_m3_s for s in opt_result.schedules if s.time_step == t and s.is_on)
                optimized_outflow_m3_s.append(outflow_t)
        
        # Calculate smoothness (variance of outflow time series)
        # For baseline, we only have current step, so smoothness is 0 (single point)
        # For optimized, calculate variance across horizon
        optimized_smoothness = 0.0
        baseline_smoothness = 0.0  # Single point = no variance
        if len(optimized_outflow_m3_s) > 1:
            import statistics
            try:
                optimized_smoothness = statistics.variance(optimized_outflow_m3_s)
            except:
                # Fallback if variance calculation fails (need at least 2 points)
                mean_opt = sum(optimized_outflow_m3_s) / len(optimized_outflow_m3_s) if optimized_outflow_m3_s else 0.0
                optimized_smoothness = sum((x - mean_opt) ** 2 for x in optimized_outflow_m3_s) / len(optimized_outflow_m3_s) if optimized_outflow_m3_s else 0.0
        
        # Calculate savings compared to baseline
        savings_cost_eur = baseline_cost_eur - opt_result.total_cost_eur
        savings_cost_percent = (savings_cost_eur / baseline_cost_eur * 100.0) if baseline_cost_eur > 0 else 0.0
        savings_energy_kwh = baseline_energy_kwh - opt_result.total_energy_kwh
        savings_energy_percent = (savings_energy_kwh / baseline_energy_kwh * 100.0) if baseline_energy_kwh > 0 else 0.0
        
        # Format optimization result - include all available information
        optimization = {
            "success": opt_result.success,
            "mode": opt_result.mode.value if opt_result.mode else None,
            "total_energy_kwh": opt_result.total_energy_kwh,
            "total_cost_eur": opt_result.total_cost_eur,
            "solve_time_seconds": opt_result.solve_time_seconds,
            "l1_violations": getattr(opt_result, 'l1_violations', 0),
            "max_violation_m": getattr(opt_result, 'max_violation_m', 0.0),
            "l1_trajectory": opt_result.l1_trajectory if opt_result.l1_trajectory else [],
            "explanation": opt_result.explanation if opt_result.explanation else None,
            "schedules": schedules,
            # Baseline comparison
            "baseline": {
                "cost_eur": baseline_cost_eur,
                "energy_kwh": baseline_energy_kwh,
                "outflow_variance": baseline_smoothness,
            },
            # Savings compared to baseline
            "savings": {
                "cost_eur": savings_cost_eur,
                "cost_percent": savings_cost_percent,
                "energy_kwh": savings_energy_kwh,
                "energy_percent": savings_energy_percent,
            },
            # Smoothness metric
            "smoothness": {
                "optimized_variance": optimized_smoothness,
                "baseline_variance": baseline_smoothness,
                "improvement_percent": (
                    (baseline_smoothness - optimized_smoothness) / baseline_smoothness * 100.0
                    if baseline_smoothness > 0 else 0.0
                ),
            },
        }
        
        # Add error/warning information if optimization failed
        if not opt_result.success:
            optimization["error"] = {
                "status": "failed",
                "explanation": opt_result.explanation,
                "mode": opt_result.mode.value if opt_result.mode else None,
            }
        
        # Include LLM-generated content if available
        explanation_data = None
        if result.explanation:
            explanation_data = result.explanation
        
        strategy_data = None
        if result.strategy:
            strategy_data = result.strategy
        
        strategic_plan_data = None
        if result.strategic_plan:
            strategic_plan_data = {
                "plan_type": result.strategic_plan.plan_type,
                "forecast_confidence": result.strategic_plan.forecast_confidence,
                "description": result.strategic_plan.description,
                "time_periods": [
                    {
                        "start_hour": start_hour,
                        "end_hour": end_hour,
                        "strategy": strategy,
                    }
                    for start_hour, end_hour, strategy in (result.strategic_plan.time_periods or [])
                ],
                "reasoning": result.strategic_plan.reasoning,
            }
        
        return {
            "type": "simulation_step",
            "step": step_index,
            "total_steps": total_steps,
            "timestamp": result.timestamp.isoformat(),
            "start_time": start_time.isoformat() if start_time else None,
            "state": state,
            "forecast": forecast_data,
            "optimization": optimization,
            "baseline_schedule": result.baseline_schedule,
            # LLM-generated content (if available)
            "explanation": explanation_data,  # Per-step explanation
            "strategy": strategy_data,  # Strategic guidance
            "strategic_plan": strategic_plan_data,  # 24h strategic plan
            # Additional metadata
            "metrics": {
                "pump_count": len(state["pumps"]),
                "pumps_on": sum(1 for p in state["pumps"] if p["state"] == "on"),
                "pumps_off": sum(1 for p in state["pumps"] if p["state"] == "off"),
                "l1_m": state["l1_m"],  # Current L1 level
                "l1_volume_m3": state["l1_volume_m3"],  # Current L1 volume
                "l2_m": state.get("l2_m"),  # Current L2 level (if available)
                "inflow_m3_s": state["inflow_m3_s"],
                "outflow_m3_s": state["outflow_m3_s"],
                "net_flow_m3_s": state["inflow_m3_s"] - state["outflow_m3_s"],
                "price_eur_per_kwh": state["price_c_per_kwh"] / 100.0,  # Convert c/kWh to EUR/kWh
                "violation_count": optimization["l1_violations"],
                "smoothness_variance": optimization["smoothness"]["optimized_variance"],
                # Pump running time
                "total_running_time_hours": {
                    "cumulative": cumulative_total_running_time_hours,  # Total across entire simulation
                    "horizon": horizon_total_running_time_hours,  # Total in this optimization horizon
                    "per_pump_cumulative": cumulative_per_pump_running_time_hours,  # Per pump across simulation
                    "per_pump_horizon": horizon_per_pump_running_time_hours,  # Per pump in this horizon
                },
            },
        }
    
    def _format_summary_as_json(self, simulation: RollingSimulation) -> Dict[str, Any]:
        """Format simulation summary as JSON."""
        comparison = self.simulator.compare_with_baseline(simulation)
        
        return {
            "type": "simulation_summary",
            "start_time": simulation.start_time.isoformat(),
            "end_time": simulation.end_time.isoformat(),
            "total_steps": len(simulation.results),
            "comparison": comparison,
        }
    
    async def run_simulation(
        self,
        start_time: datetime,
        end_time: datetime,
        speed_multiplier: float = 1.0,  # 1.0 = real-time, 10.0 = 10x speed
    ) -> RollingSimulation:
        """Run simulation and stream updates via callback.
        
        Args:
            start_time: Simulation start time
            end_time: Simulation end time
            speed_multiplier: Speed multiplier for demo (1.0 = real-time, higher = faster)
        
        Returns:
            RollingSimulation result
        """
        # Calculate total steps
        total_duration = end_time - start_time
        total_steps = int(total_duration.total_seconds() / (self.reoptimize_interval_minutes * 60))
        
        # Send initial message
        if self.update_callback:
            initial_msg = {
                "type": "simulation_start",
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "total_steps": total_steps,
                "reoptimize_interval_minutes": self.reoptimize_interval_minutes,
            }
            if asyncio.iscoroutinefunction(self.update_callback):
                await self.update_callback(initial_msg)
            else:
                self.update_callback(initial_msg)
        
        # Use the simulator's simulate method which includes LLM support
        # We'll intercept results and send updates via callback
        simulation = self.simulator.simulate(
            start_time=start_time,
            end_time=end_time,
            horizon_minutes=120,  # 2-hour horizon
        )
        
        # Send updates for each result
        for step_index, result in enumerate(simulation.results):
            # Get forecast for this step
            forecast = self.data_loader.get_forecast_from_time(result.timestamp, 8)
            
            # Log explanation status for debugging
            if result.explanation:
                logger.info(f"Step {step_index}: Explanation available ({len(result.explanation)} chars)")
            else:
                logger.debug(f"Step {step_index}: No explanation (explanation={result.explanation}, strategy={result.strategy})")
            
            # Send update via callback
            if self.update_callback:
                update_data = self._format_result_as_json(result, step_index, len(simulation.results), forecast=forecast, start_time=start_time)
                if asyncio.iscoroutinefunction(self.update_callback):
                    await self.update_callback(update_data)
                else:
                    self.update_callback(update_data)
            
            # Wait before next step (adjusted by speed multiplier)
            if step_index < len(simulation.results) - 1:  # Don't wait after last step
                wait_seconds = (self.reoptimize_interval_minutes * 60) / speed_multiplier
                await asyncio.sleep(wait_seconds)
        
        # Send summary
        if self.update_callback:
            summary = self._format_summary_as_json(simulation)
            # Handle both sync and async callbacks
            if asyncio.iscoroutinefunction(self.update_callback):
                await self.update_callback(summary)
            else:
                self.update_callback(summary)
        
        return simulation


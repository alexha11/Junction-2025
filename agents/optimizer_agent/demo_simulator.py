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
        self.llm_explainer = llm_explainer
        
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
        
        # Log LLM initialization status
        if llm_explainer:
            logger.info(f"✅ DemoSimulator: LLM explainer initialized (generate_explanations={self.simulator.generate_explanations}, generate_strategic_plan={self.simulator.generate_strategic_plan})")
        else:
            logger.warning("❌ DemoSimulator: No LLM explainer provided - explanations/strategy will be None")
    
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
        
        # L2 removed - not available in simulation data
        
        # Get pump power from optimization schedules (time_step 0 = current step)
        pump_power_map: Dict[str, float] = {}
        if opt_result.schedules:
            for schedule in opt_result.schedules:
                if schedule.time_step == 0 and schedule.is_on:
                    pump_power_map[schedule.pump_id] = schedule.power_kw
        
        # Determine pump type (big vs small)
        # Small pumps: 1.1, 2.1 (200 kW max)
        # Big pumps: 1.2, 1.3, 1.4, 2.2, 2.3, 2.4 (400 kW max)
        def get_pump_type(pump_id: str) -> str:
            if pump_id.endswith(".1"):
                return "small"
            return "big"
        
        # Format current state
        state = {
            "timestamp": result.current_state.timestamp.isoformat(),
            "l1_m": result.current_state.l1_m,  # L1 level in meters
            "l1_volume_m3": l1_volume_m3,  # L1 volume in m³ (calculated)
            "inflow_m3_s": result.current_state.inflow_m3_s,
            "outflow_m3_s": result.current_state.outflow_m3_s,
            "price_c_per_kwh": result.current_state.price_c_per_kwh,
            "pumps": [
                {
                    "pump_id": pump_id,
                    "state": "on" if is_on else "off",
                    "frequency_hz": freq,
                    "power_kw": pump_power_map.get(pump_id, 0.0),
                    "type": get_pump_type(pump_id),  # "big" or "small"
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
        
        # Calculate baseline cost and energy for CURRENT STEP ONLY (15 minutes)
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
        
        # Calculate optimized cost and energy for CURRENT STEP ONLY (time_step 0)
        # This matches baseline which is for 1 step
        optimized_cost_eur_current_step = 0.0
        optimized_energy_kwh_current_step = 0.0
        dt_hours = self.reoptimize_interval_minutes / 60.0
        if opt_result.schedules and forecast:
            # Get price for current step (time_step 0)
            price_c_per_kwh_current = result.current_state.price_c_per_kwh
            if len(forecast.price_c_per_kwh) > 0:
                price_c_per_kwh_current = forecast.price_c_per_kwh[0]
            
            # Sum cost/energy for all pumps at time_step 0
            for schedule in opt_result.schedules:
                if schedule.time_step == 0 and schedule.is_on:
                    optimized_energy_kwh_current_step += schedule.power_kw * dt_hours
                    optimized_cost_eur_current_step += schedule.power_kw * dt_hours * (price_c_per_kwh_current / 100.0)
        
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
        
        # Calculate savings compared to baseline (comparing current step only)
        savings_cost_eur = baseline_cost_eur - optimized_cost_eur_current_step
        savings_cost_percent = (savings_cost_eur / baseline_cost_eur * 100.0) if baseline_cost_eur > 0 else 0.0
        savings_energy_kwh = baseline_energy_kwh - optimized_energy_kwh_current_step
        savings_energy_percent = (savings_energy_kwh / baseline_energy_kwh * 100.0) if baseline_energy_kwh > 0 else 0.0
        
        # Format optimization result - include all available information
        optimization = {
            "success": opt_result.success,
            "mode": opt_result.mode.value if opt_result.mode else None,
            # Full horizon totals (for reference)
            "total_energy_kwh": opt_result.total_energy_kwh,
            "total_cost_eur": opt_result.total_cost_eur,
            # Current step only (for comparison with baseline)
            "current_step_energy_kwh": optimized_energy_kwh_current_step,
            "current_step_cost_eur": optimized_cost_eur_current_step,
            # Solver metrics
            "solve_time_seconds": opt_result.solve_time_seconds,
            "l1_violations": getattr(opt_result, 'l1_violations', 0),
            "max_violation_m": getattr(opt_result, 'max_violation_m', 0.0),
            "l1_trajectory": opt_result.l1_trajectory if opt_result.l1_trajectory else [],
            "explanation": opt_result.explanation if opt_result.explanation else None,
            "schedules": schedules,
            # Baseline comparison (current step only)
            "baseline": {
                "cost_eur": baseline_cost_eur,
                "energy_kwh": baseline_energy_kwh,
                "outflow_variance": baseline_smoothness,
            },
            # Optimized (current step only) - for direct comparison
            "optimized": {
                "cost_eur": optimized_cost_eur_current_step,
                "energy_kwh": optimized_energy_kwh_current_step,
                "outflow_variance": optimized_smoothness,
            },
            # Savings compared to baseline (current step)
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
        
        # Include explanations and strategy (LLM only - no fallback)
        explanation_data = None
        if result.explanation:
            # Use LLM-generated explanation only
            explanation_data = result.explanation
        
        strategy_data = None
        if result.strategy:
            # Use LLM-generated strategy only
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
            logger.info(f"📤 Sending simulation_start message (total_steps={total_steps})...")
            try:
                if asyncio.iscoroutinefunction(self.update_callback):
                    sent = await self.update_callback(initial_msg)
                else:
                    sent = self.update_callback(initial_msg)
                if sent is False:
                    logger.warning("⚠️ Connection closed before simulation started")
                    raise ConnectionError("Connection closed before simulation started")
                logger.info("✅ simulation_start message sent successfully")
            except ConnectionError:
                raise
            except Exception as e:
                logger.error(f"❌ Failed to send simulation_start: {e}", exc_info=True)
                raise
        
        logger.info(f"🚀 Running simulation from {start_time} to {end_time} ({total_steps} steps)...")
        
        # Create a RollingSimulation to collect results
        simulation = RollingSimulation(start_time=start_time, end_time=end_time)
        
        # Run simulation incrementally, sending messages after each step
        # This allows real-time streaming instead of waiting for entire simulation to complete
        current_time = start_time
        step_index = 0
        
        # Initialize state from simulator
        initial_state = self.data_loader.get_state_at_time(start_time, include_pump_states=False)
        if initial_state is None:
            error_msg = {
                "type": "error",
                "message": f"No data available at {start_time}",
                "error_type": "ValueError",
            }
            if self.update_callback:
                if asyncio.iscoroutinefunction(self.update_callback):
                    await self.update_callback(error_msg)
                else:
                    self.update_callback(error_msg)
            raise ValueError(f"No data available at {start_time}")
        
        # Use simulator's internal state
        simulated_l1 = initial_state.l1_m
        
        try:
            while current_time <= end_time:
                logger.info(f"🔄 Processing step {step_index + 1}/{total_steps} at {current_time.isoformat()}")
                
                # Get current state
                current_state = self.data_loader.get_state_at_time(current_time, include_pump_states=False)
                if current_state is None:
                    logger.warning(f"⚠️ No data available at {current_time}, skipping...")
                    current_time += timedelta(minutes=self.reoptimize_interval_minutes)
                    step_index += 1
                    continue
                
                current_state.l1_m = simulated_l1
                
                # Try to get L2 from data loader if available (check if data has L2 column)
                # For now, L2 is not in the data, so we'll set it to None and let the formatter handle it
                # If L2 data becomes available, we can add it here
                
                # Update pump states from previous optimization if available
                # Only use time_step=0 (current step) from previous optimization
                if len(simulation.results) > 0:
                    prev_result = simulation.results[-1]
                    if prev_result.optimization_result.success and prev_result.optimization_result.schedules:
                        prev_pump_states = {}
                        # Only use schedules from time_step=0 (current step) of previous optimization
                        for schedule in prev_result.optimization_result.schedules:
                            if schedule.time_step == 0:  # Only current step from previous optimization
                                prev_pump_states[schedule.pump_id] = (schedule.pump_id, schedule.is_on, schedule.frequency_hz)
                        
                        updated_pump_states = []
                        for pump_id, _, _ in current_state.pump_states:
                            if pump_id in prev_pump_states:
                                updated_pump_states.append(prev_pump_states[pump_id])
                            else:
                                updated_pump_states.append((pump_id, False, 0.0))
                        current_state.pump_states = updated_pump_states
                # At step 0, pumps should start OFF (already set by get_state_at_time with include_pump_states=False)
                
                # Get forecast for optimization (2-hour tactical horizon)
                horizon_steps = 120 // self.optimizer.time_step_minutes  # 2-hour horizon
                forecast = self.data_loader.get_forecast_from_time(current_time, horizon_steps, method='perfect')
                if forecast is None:
                    logger.warning(f"⚠️ No forecast available at {current_time}, skipping...")
                    current_time += timedelta(minutes=self.reoptimize_interval_minutes)
                    step_index += 1
                    continue
                
                # Generate strategic plan (24h) BEFORE optimization if LLM is enabled
                strategic_plan = None
                if self.simulator.generate_strategic_plan and self.simulator.llm_explainer:
                    try:
                        logger.info(f"🧠 Generating strategic plan for step {step_index + 1}...")
                        # Request 24h forecast (96 steps of 15 minutes)
                        forecast_24h_steps = 24 * 60 // self.optimizer.time_step_minutes  # 96 steps
                        forecast_24h = self.data_loader.get_forecast_from_time(
                            current_time, forecast_24h_steps, method='perfect'
                        )
                        if forecast_24h:
                            strategic_plan = await self.simulator.llm_explainer.generate_strategic_plan(
                                forecast_24h_timestamps=forecast_24h.timestamps,
                                forecast_24h_inflow=forecast_24h.inflow_m3_s,
                                forecast_24h_price=forecast_24h.price_c_per_kwh,
                                current_l1_m=current_state.l1_m,
                                l1_min_m=self.optimizer.constraints.l1_min_m,
                                l1_max_m=self.optimizer.constraints.l1_max_m,
                                forecast_quality_tracker=self.simulator.forecast_quality_tracker,
                            )
                            if strategic_plan:
                                logger.info(f"✅ Strategic plan generated: {strategic_plan.plan_type}")
                            else:
                                logger.warning(f"⚠️ Strategic plan generation returned None")
                        else:
                            logger.warning(f"⚠️ No 24h forecast available for strategic planning")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to generate strategic plan: {e}", exc_info=True)
                        strategic_plan = None
                
                # Run optimization in executor (it's synchronous)
                logger.info(f"🔧 Running optimization for step {step_index + 1}...")
                loop = asyncio.get_event_loop()
                opt_result = await loop.run_in_executor(
                    None,
                    lambda: self.optimizer.solve_optimization(
                        current_state=current_state,
                        forecast=forecast,
                        mode=None,  # Will default to OptimizationMode.FULL
                        timeout_seconds=30,
                        strategic_plan=strategic_plan,  # Pass strategic plan to influence optimization
                    )
                )
                logger.info(f"✅ Optimization completed for step {step_index + 1} (success={opt_result.success})")
                
                # Generate explanation and strategy AFTER optimization if LLM is enabled
                explanation = None
                strategy = None
                if self.simulator.generate_explanations and self.simulator.llm_explainer:
                    try:
                        logger.info(f"🧠 Generating explanation for step {step_index + 1}...")
                        # Get strategic guidance
                        strategic_guidance = self.optimizer.derive_strategic_guidance(forecast)
                        strategy = ", ".join(set(strategic_guidance[:4]))
                        
                        # Compute metrics for this step
                        from .test_simulator import ScheduleMetrics
                        metrics = ScheduleMetrics(
                            total_energy_kwh=opt_result.total_energy_kwh,
                            total_cost_eur=opt_result.total_cost_eur,
                            avg_l1_m=current_state.l1_m,
                            min_l1_m=opt_result.l1_trajectory[0] if opt_result.l1_trajectory else current_state.l1_m,
                            max_l1_m=max(opt_result.l1_trajectory) if opt_result.l1_trajectory else current_state.l1_m,
                            num_pumps_used=len([s for s in opt_result.schedules if s.is_on]) if opt_result.schedules else 0,
                            avg_outflow_m3_s=sum(s.flow_m3_s for s in opt_result.schedules if s.is_on) / len(opt_result.schedules) if opt_result.schedules else 0.0,
                            price_range_c_per_kwh=(min(forecast.price_c_per_kwh), max(forecast.price_c_per_kwh)),
                            risk_level="normal",
                            optimization_mode=opt_result.mode.value if opt_result.mode else "full",
                        )
                        
                        # Build state description
                        pump_state_desc = "; ".join([
                            f"{pid}: {'ON' if on else 'OFF'}" + (f" @ {freq:.1f}Hz" if on else "")
                            for pid, on, freq in current_state.pump_states
                        ])
                        current_state_desc = (
                            f"System State: Tunnel level L1={current_state.l1_m:.2f}m, "
                            f"Inflow F1={current_state.inflow_m3_s:.2f} m³/s, "
                            f"Outflow F2={current_state.outflow_m3_s:.2f} m³/s, "
                            f"Electricity price={current_state.price_c_per_kwh:.1f} c/kWh. "
                            f"Pump states: {pump_state_desc}"
                        )
                        
                        # Generate LLM explanation
                        explanation = await self.simulator.llm_explainer.generate_explanation(
                            metrics=metrics,
                            strategic_guidance=strategic_guidance,
                            current_state_description=current_state_desc,
                            strategic_plan=strategic_plan,
                        )
                        if explanation:
                            logger.info(f"✅ Explanation generated ({len(explanation)} chars)")
                        else:
                            logger.warning(f"⚠️ Explanation generation returned None")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to generate explanation: {e}", exc_info=True)
                        explanation = None
                        strategy = None
                
                # Get baseline schedule
                baseline_schedule = self.data_loader.get_baseline_schedule_at_time(current_time)
                
                # Create simulation result with LLM-generated content
                result = SimulationResult(
                    timestamp=current_time,
                    current_state=current_state,  # Required field
                    optimization_result=opt_result,
                    baseline_schedule=baseline_schedule,
                    explanation=explanation,  # LLM explanation
                    strategy=strategy,  # Strategic guidance
                    strategic_plan=strategic_plan,  # Strategic plan
                )
                
                simulation.results.append(result)
                
                # Send update immediately after this step
                if self.update_callback:
                    try:
                        forecast_8 = self.data_loader.get_forecast_from_time(current_time, 8)
                        update_data = self._format_result_as_json(result, step_index, total_steps, forecast=forecast_8, start_time=start_time)
                        logger.info(f"📤 Sending step {step_index + 1}/{total_steps} (timestamp: {current_time.isoformat()})...")
                        if asyncio.iscoroutinefunction(self.update_callback):
                            sent = await self.update_callback(update_data)
                        else:
                            sent = self.update_callback(update_data)
                        
                        # Check if message was sent successfully (callback may return False if connection closed)
                        if sent is False:
                            logger.warning(f"⚠️ Connection closed, stopping simulation at step {step_index + 1}")
                            break  # Stop simulation if connection is closed
                        
                        logger.info(f"✅ Step {step_index + 1}/{total_steps} sent successfully")
                    except ConnectionError as conn_err:
                        logger.warning(f"⚠️ Connection error at step {step_index + 1}: {conn_err}")
                        break  # Stop simulation on connection error
                    except Exception as e:
                        logger.error(f"❌ Failed to send step {step_index + 1}: {e}", exc_info=True)
                        # Check if it's a connection error - if so, stop simulation
                        error_str = str(e).lower()
                        if "close" in error_str or "disconnect" in error_str or "connection" in error_str:
                            logger.warning(f"⚠️ Connection error detected, stopping simulation at step {step_index + 1}")
                            break  # Stop simulation on connection error
                        # For other errors, log but continue (might be transient)
                        logger.warning(f"⚠️ Non-connection error when sending step {step_index + 1}, continuing...")
                
                # Update simulated L1 for next step (simplified - would normally come from plant/simulator)
                if opt_result.success and opt_result.l1_trajectory and len(opt_result.l1_trajectory) > 0:
                    simulated_l1 = opt_result.l1_trajectory[0]
                
                # Move to next time step
                step_index += 1
                current_time += timedelta(minutes=self.reoptimize_interval_minutes)
                
                # Process messages sequentially - no wait time, proceed immediately to next step
                if current_time > end_time:
                    logger.info(f"✅ Reached end time, simulation complete")
        
        except Exception as e:
            logger.error(f"Simulation failed at step {step_index}: {e}", exc_info=True)
            if self.update_callback:
                error_msg = {
                    "type": "error",
                    "message": f"Simulation failed at step {step_index + 1}: {str(e)}",
                    "error_type": type(e).__name__,
                }
                if asyncio.iscoroutinefunction(self.update_callback):
                    await self.update_callback(error_msg)
                else:
                    self.update_callback(error_msg)
            raise
        
        # Send summary
        if self.update_callback:
            summary = self._format_summary_as_json(simulation)
            if asyncio.iscoroutinefunction(self.update_callback):
                await self.update_callback(summary)
            else:
                self.update_callback(summary)
        
        return simulation


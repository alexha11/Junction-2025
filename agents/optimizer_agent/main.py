"""Optimizer Agent - MPC-style pump scheduling optimizer."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any, List, Optional

import httpx
from pydantic import BaseModel

from agents.common import BaseMCPAgent

logger = logging.getLogger(__name__)

# Suppress httpx INFO level HTTP request logs (only show WARNING/ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)

from .explainability import LLMExplainer, ScheduleMetrics, StrategicPlan, ForecastQualityTracker
from .optimizer import (
    CurrentState,
    ForecastData,
    MPCOptimizer,
    OptimizationMode,
    PumpSpec,
    SystemConstraints,
)


class OptimizationRequest(BaseModel):
    horizon_minutes: int = 120  # Default 2h tactical horizon


class ScheduleEntry(BaseModel):
    pump_id: str
    start_time: datetime
    end_time: datetime
    target_frequency_hz: float


class OptimizationResponse(BaseModel):
    generated_at: datetime
    entries: List[ScheduleEntry]
    justification: str
    total_cost_eur: float = 0.0
    total_energy_kwh: float = 0.0
    optimization_mode: str = "full"


class OptimizationAgent(BaseMCPAgent):
    """Optimizer Agent implementing MPC-style optimization."""

    def __init__(
        self,
        status_agent_url: Optional[str] = None,
        price_agent_url: Optional[str] = None,
        inflow_agent_url: Optional[str] = None,
        featherless_api_base: Optional[str] = None,
        featherless_api_key: Optional[str] = None,
    ):
        super().__init__(name="optimization-agent")
        self.status_agent_url = status_agent_url or os.getenv("STATUS_AGENT_URL", "http://localhost:8103")
        self.price_agent_url = price_agent_url or os.getenv("PRICE_AGENT_URL", "http://localhost:8102")
        self.inflow_agent_url = inflow_agent_url or os.getenv("INFLOW_AGENT_URL", "http://localhost:8104")
        
        # Initialize optimizer
        self._init_optimizer()
        
        # Initialize LLM explainer
        self.explainer = LLMExplainer(
            api_base=featherless_api_base or os.getenv("FEATHERLESS_API_BASE"),
            api_key=featherless_api_key or os.getenv("FEATHERLESS_API_KEY"),
            model=os.getenv("LLM_MODEL", "llama-3.1-8b-instruct"),
        )
        # Initialize forecast quality tracker for recalibration loop
        self.forecast_quality_tracker = ForecastQualityTracker()
        
        # Track cumulative pump usage hours for fairness/rotation in live agent
        self.pump_usage_hours = {}
        
        # Cache for strategic plan to avoid unnecessary LLM calls
        self._cached_strategic_plan: Optional[Any] = None
        self._cached_strategic_plan_timestamp: Optional[datetime] = None
        self._cached_forecast_hash: Optional[str] = None
        self._strategic_plan_cache_ttl_minutes: int = 60  # Cache for 1 hour by default
        
        # State tracking for divergence detection
        self._previous_prediction: Optional[float] = None  # Previous L1 prediction
        self._previous_forecast_inflow: Optional[float] = None  # Previous forecast inflow
        self._previous_forecast_price: Optional[float] = None  # Previous forecast price
        self._previous_prediction_timestamp: Optional[datetime] = None  # When prediction was made
        self._prediction_state_ttl_minutes: int = 30  # Expire state after 30 minutes

    def _init_optimizer(self):
        """Initialize the MPC optimizer with pump specifications.

        Uses two pump capacity classes based on Hackathon_HSY_data.xlsx:
        - Small pumps:  ~0.5 m³/s, 200 kW
        - Large pumps:  ~1.0 m³/s, 400 kW

        Pump IDs follow the dataset naming and physical grouping:
        - Line 1: 1.1, 1.2, 1.3, 1.4
        - Line 2: 2.1, 2.2, 2.3, 2.4

        Mapping (per dataset):
        - 1.1, 2.1  → small pumps (one per line)
        - 1.2, 1.3, 1.4, 2.2, 2.3, 2.4 → large pumps
        """
        # Define nominal capacities (ceiled from historical data)
        small_flow_m3_s = 0.5
        small_power_kw = 200.0
        large_flow_m3_s = 1.0
        large_power_kw = 400.0

        pump_ids = ["1.1", "1.2", "1.3", "1.4", "2.1", "2.2", "2.3", "2.4"]

        pumps: list[PumpSpec] = []
        for pump_id in pump_ids:
            # Small pumps are the ".1" pumps on each line
            if pump_id.endswith(".1"):
                max_flow_m3_s = small_flow_m3_s
                max_power_kw = small_power_kw
            else:
                max_flow_m3_s = large_flow_m3_s
                max_power_kw = large_power_kw

            pumps.append(
                PumpSpec(
                    pump_id=pump_id,
                    max_flow_m3_s=max_flow_m3_s,
                    max_power_kw=max_power_kw,
                    min_frequency_hz=47.8,
                    max_frequency_hz=50.0,
                    preferred_freq_min_hz=47.8,
                    preferred_freq_max_hz=49.0,
                )
            )
        
        constraints = SystemConstraints(
            l1_min_m=0.0,
            l1_max_m=8.0,
            tunnel_volume_m3=50000.0,  # Approximate tunnel volume
            min_pumps_on=1,
            min_pump_on_duration_minutes=120,
            min_pump_off_duration_minutes=120,
            flush_frequency_days=1,
            flush_target_level_m=0.5,
        )
        
        self.optimizer = MPCOptimizer(
            pumps=pumps,
            constraints=constraints,
            time_step_minutes=15,
            tactical_horizon_minutes=120,  # 2-hour tactical horizon
            strategic_horizon_minutes=1440,
        )

    def configure(self) -> None:
        self.register_tool("generate_schedule", self.generate_schedule)

    def generate_schedule(self, request: OptimizationRequest) -> OptimizationResponse:
        """Generate optimal pump schedule using MPC optimization."""
        try:
            # Gather current state and forecasts
            current_state = self._get_current_state()
            forecast = self._get_forecasts(request.horizon_minutes)
            
            # Generate strategic plan (24h) BEFORE optimization (so it can influence optimization)
            # Use cached plan if forecasts haven't changed significantly and everything is working as predicted
            strategic_plan = self._get_strategic_plan(current_state)
            
            # Detect divergence and generate emergency response if needed
            divergence = None
            emergency_response = None
            
            # Check if we have previous prediction state (and it's not too old)
            has_previous_state = False
            if self._previous_prediction_timestamp:
                age_minutes = (datetime.utcnow() - self._previous_prediction_timestamp).total_seconds() / 60
                if age_minutes <= self._prediction_state_ttl_minutes:
                    has_previous_state = True
            
            if has_previous_state:
                # Detect divergence using previous prediction
                divergence = self.optimizer.detect_divergence(
                    current_state=current_state,
                    forecast=forecast,
                    previous_prediction=self._previous_prediction,
                    previous_forecast_inflow=self._previous_forecast_inflow,
                    previous_forecast_price=self._previous_forecast_price,
                )
                
                # Generate emergency response if divergence detected and LLM available
                if divergence and self.explainer.api_base and self.explainer.api_key:
                    try:
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        
                        emergency_response = loop.run_until_complete(
                            self.explainer.generate_emergency_response(
                                error_type=divergence['error_type'],
                                error_magnitude=divergence['error_magnitude'],
                                forecast_value=divergence['forecast_value'],
                                actual_value=divergence['actual_value'],
                                current_l1_m=current_state.l1_m,
                                l1_min_m=self.optimizer.constraints.l1_min_m,
                                l1_max_m=self.optimizer.constraints.l1_max_m,
                                predicted_l1_m=self._previous_prediction,
                            )
                        )
                        if emergency_response:
                            logger.warning(
                                f"🚨 Emergency response triggered: {divergence['error_type']} "
                                f"(severity: {emergency_response.severity})"
                            )
                    except Exception as e:
                        logger.warning(f"Failed to generate emergency response: {e}")
            
            # Solve optimization (strategic plan can influence weights)
            result = self.optimizer.solve_optimization(
                current_state=current_state,
                forecast=forecast,
                mode=OptimizationMode.FULL,
                timeout_seconds=30,
                strategic_plan=strategic_plan,  # Pass strategic plan to optimizer
                emergency_response=emergency_response,  # Pass emergency response if divergence detected
                pump_usage_hours=self.pump_usage_hours,  # Pass usage for fairness/rotation
            )
            
            if not result.success:
                # Try fallback (also with strategic plan if available)
                result = self.optimizer.solve_optimization(
                    current_state=current_state,
                    forecast=forecast,
                    mode=OptimizationMode.RULE_BASED,
                    timeout_seconds=10,
                    strategic_plan=strategic_plan,
                    emergency_response=emergency_response,  # Pass emergency response to fallback too
                    pump_usage_hours=self.pump_usage_hours,  # Pass usage for fairness/rotation (unused in rule-based)
                )
            
            # Update cumulative pump usage hours based on final result (first step only)
            dt_hours = self.optimizer.time_step_minutes / 60.0
            if result.success and result.schedules:
                for sched in result.schedules:
                    if sched.time_step == 0 and sched.is_on:
                        pid = sched.pump_id
                        self.pump_usage_hours[pid] = self.pump_usage_hours.get(pid, 0.0) + dt_hours
            
            # Store prediction state for next divergence detection
            if result.success and result.l1_trajectory and len(result.l1_trajectory) > 0:
                # Store first step prediction (what we expect L1 to be at next optimization)
                self._previous_prediction = result.l1_trajectory[0]
                self._previous_forecast_inflow = forecast.inflow_m3_s[0] if len(forecast.inflow_m3_s) > 0 else None
                self._previous_forecast_price = forecast.price_c_per_kwh[0] if len(forecast.price_c_per_kwh) > 0 else None
                self._previous_prediction_timestamp = datetime.utcnow()
            
            # Convert to response format
            entries = self._convert_to_entries(result, forecast.timestamps)
            
            # Derive algorithmic strategic guidance (always available as fallback)
            strategic_guidance = self.optimizer.derive_strategic_guidance(forecast)
            
            # Generate explanation
            metrics = self._compute_metrics(result, forecast)
            
            # Try LLM explanation if available, otherwise use fallback
            explanation = self._generate_explanation(
                metrics, strategic_guidance, current_state, strategic_plan
            )
            
            return OptimizationResponse(
                generated_at=datetime.utcnow(),
                entries=entries,
                justification=explanation,
                total_cost_eur=result.total_cost_eur,
                total_energy_kwh=result.total_energy_kwh,
                optimization_mode=result.mode.value,
            )
        except Exception as e:
            # Fallback to safe rule-based schedule
            return self._generate_fallback_schedule(request)

    def _get_current_state(self) -> CurrentState:
        """Get current system state from status agent or stub."""
        try:
            # Try to call status agent
            response = httpx.get(f"{self.status_agent_url}/get_current_system_state", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                pumps = [
                    (p["pump_id"], p.get("state") == "on", p.get("frequency_hz", 0.0))
                    for p in data.get("pumps", [])
                ]
                return CurrentState(
                    timestamp=datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")),
                    l1_m=data.get("tunnel_level_m", 3.2),
                    inflow_m3_s=data.get("inflow_m3_s", 2.1),
                    outflow_m3_s=data.get("outflow_m3_s", 2.0),
                    pump_states=pumps,
                    price_c_per_kwh=data.get("price_c_per_kwh", data.get("price_c_per_kwh", 72.5)),
                )
        except Exception:
            pass
        
        # Fallback to stub data (use physical pump IDs 1.1-1.4 and 2.1-2.4)
        default_pump_ids = ["1.1", "1.2", "1.3", "1.4", "2.1", "2.2", "2.3", "2.4"]
        return CurrentState(
            timestamp=datetime.utcnow(),
            l1_m=3.2,
            inflow_m3_s=2.1,
            outflow_m3_s=2.0,
            pump_states=[
                (pid, idx % 2 == 0, 48.0 if idx % 2 == 0 else 0.0)
                for idx, pid in enumerate(default_pump_ids)
            ],
            price_c_per_kwh=72.5,
        )

    def _get_forecasts(self, horizon_minutes: int) -> ForecastData:
        """Get forecasts from agents or generate stub data."""
        num_steps = horizon_minutes // 15  # 15-minute steps
        now = datetime.utcnow()
        timestamps = [now + timedelta(minutes=i * 15) for i in range(num_steps)]
        
        # Try to get price forecast
        price_forecast = []
        try:
            response = httpx.post(
                f"{self.price_agent_url}/get_electricity_price_forecast",
                json={"lookahead_hours": horizon_minutes / 60},
                timeout=5.0,
            )
            if response.status_code == 200:
                data = response.json()
                price_forecast = [p.get("eur_mwh", 70.0) for p in data]
        except Exception:
            pass
        
        # Try to get inflow forecast
        inflow_forecast = []
        try:
            response = httpx.post(
                f"{self.inflow_agent_url}/predict_inflow",
                json={"lookahead_hours": horizon_minutes / 60},
                timeout=5.0,
            )
            if response.status_code == 200:
                data = response.json()
                inflow_forecast = [p.get("inflow_m3_s", 2.0) for p in data]
        except Exception:
            pass
        
        # Fill in stub data if needed
        if not price_forecast:
            price_forecast = [70.0 + i * 1.5 for i in range(num_steps)]
        
        if not inflow_forecast:
            inflow_forecast = [2.0 + i * 0.05 for i in range(num_steps)]
        
        # Ensure correct length
        while len(price_forecast) < num_steps:
            price_forecast.append(price_forecast[-1] if price_forecast else 70.0)
        
        while len(inflow_forecast) < num_steps:
            inflow_forecast.append(inflow_forecast[-1] if inflow_forecast else 2.0)
        
        return ForecastData(
            timestamps=timestamps[:num_steps],
            inflow_m3_s=inflow_forecast[:num_steps],
            price_c_per_kwh=price_forecast[:num_steps],
        )

    def _convert_to_entries(
        self, result, timestamps: List[datetime]
    ) -> List[ScheduleEntry]:
        """Convert optimizer result to schedule entries."""
        entries = []
        
        # Group schedules by pump and time
        pump_schedules = {}
        for sched in result.schedules:
            if sched.is_on:
                pump_id = sched.pump_id
                if pump_id not in pump_schedules:
                    pump_schedules[pump_id] = []
                pump_schedules[pump_id].append((sched.time_step, sched))
        
        # Create entries with time ranges
        for pump_id, steps in pump_schedules.items():
            steps.sort(key=lambda x: x[0])
            
            current_start = None
            current_freq = None
            
            for step_idx, sched in steps:
                if current_start is None:
                    current_start = step_idx
                    current_freq = sched.frequency_hz
                elif sched.frequency_hz != current_freq or step_idx != current_start + 1:
                    # End current entry and start new one
                    if current_start < len(timestamps):
                        entries.append(
                            ScheduleEntry(
                                pump_id=pump_id,
                                start_time=timestamps[current_start],
                                end_time=timestamps[min(step_idx - 1, len(timestamps) - 1)],
                                target_frequency_hz=current_freq,
                            )
                        )
                    current_start = step_idx
                    current_freq = sched.frequency_hz
                else:
                    # Continue current entry
                    pass
            
            # Add final entry
            if current_start is not None and current_start < len(timestamps):
                entries.append(
                    ScheduleEntry(
                        pump_id=pump_id,
                        start_time=timestamps[current_start],
                        end_time=timestamps[min(len(timestamps) - 1, steps[-1][0])],
                        target_frequency_hz=current_freq or 48.0,
                    )
                )
        
        # If no entries generated, create at least one safe entry
        if not entries:
            entries.append(
                ScheduleEntry(
                    pump_id="P1",
                    start_time=timestamps[0],
                    end_time=timestamps[-1] if len(timestamps) > 1 else timestamps[0],
                    target_frequency_hz=48.0,
                )
            )
        
        return entries

    def _compute_metrics(self, result, forecast: ForecastData) -> ScheduleMetrics:
        """Compute metrics for explanation."""
        if not result.l1_trajectory:
            # Default price range: 70-80 EUR/MWh → 7-8 c/kWh
            return ScheduleMetrics(
                total_energy_kwh=result.total_energy_kwh,
                total_cost_eur=result.total_cost_eur,
                avg_l1_m=3.0,
                min_l1_m=0.5,
                max_l1_m=8.0,
                num_pumps_used=1,
                avg_outflow_m3_s=2.0,
                price_range_c_per_kwh=(7.0, 8.0),
                risk_level="normal",
                optimization_mode=result.mode.value,
            )
        
        pumps_used = len(set(s.pump_id for s in result.schedules if s.is_on))
        total_outflow = sum(s.flow_m3_s for s in result.schedules if s.is_on)
        num_on_steps = len([s for s in result.schedules if s.is_on])
        avg_outflow = total_outflow / max(1, num_on_steps) if num_on_steps > 0 else 0.0
        
        # Forecast prices are already in c/kWh in ForecastData
        min_price = min(forecast.price_c_per_kwh)
        max_price = max(forecast.price_c_per_kwh)
        return ScheduleMetrics(
            total_energy_kwh=result.total_energy_kwh,
            total_cost_eur=result.total_cost_eur,
            avg_l1_m=sum(result.l1_trajectory) / len(result.l1_trajectory),
            min_l1_m=min(result.l1_trajectory),
            max_l1_m=max(result.l1_trajectory),
            num_pumps_used=pumps_used,
            avg_outflow_m3_s=avg_outflow,
            price_range_c_per_kwh=(min_price, max_price),
            risk_level="normal",  # Could be computed from optimizer
            optimization_mode=result.mode.value,
        )

    def _generate_explanation(
        self,
        metrics,
        strategic_guidance: List[str],
        current_state: CurrentState,
        strategic_plan: Optional[Any] = None,
    ) -> str:
        """Generate explanation using LLM if available, otherwise fallback."""
        # Build current state description (price already in c/kWh)
        price_c_per_kwh = current_state.price_c_per_kwh
        current_state_desc = (
            f"Tunnel level: {current_state.l1_m:.2f}m, "
            f"Inflow: {current_state.inflow_m3_s:.2f} m³/s, "
            f"Price: {price_c_per_kwh:.1f} c/kWh"
        )
        
        # Log strategy
        if strategic_plan:
            strategy_summary = f"{strategic_plan.plan_type} (LLM-generated)"
            logger.info(f"Strategy: {strategy_summary}")
            logger.info(f"  Plan: {strategic_plan.description}")
        else:
            strategy_summary = ", ".join(set(strategic_guidance[:4]))
            logger.info(f"Strategy: {strategy_summary} (algorithmic)")
        
        # Try async LLM call in sync context using asyncio
        if self.explainer.api_base and self.explainer.api_key:
            logger.debug("LLM explainer: Attempting to generate explanation via LLM")
            try:
                import asyncio
                # Try to get existing event loop, or create new one
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # Run async LLM call
                explanation = loop.run_until_complete(
                    self.explainer.generate_explanation(
                        metrics=metrics,
                        strategic_guidance=strategic_guidance,
                        current_state_description=current_state_desc,
                        strategic_plan=strategic_plan,
                    )
                )
                logger.debug(f"LLM explainer: Successfully generated explanation via LLM")
                logger.info(f"LLM Explanation: {explanation}")
                return explanation
            except Exception as e:
                # Fall back to rule-based explanation on error
                logger.warning(f"LLM explainer: Failed to generate explanation: {e}. Using fallback.")
                fallback_explanation = self.explainer._generate_fallback_explanation(
                    metrics, strategic_guidance
                )
                logger.info(f"Fallback Explanation: {fallback_explanation}")
                return fallback_explanation
        else:
            # No LLM credentials, use fallback
            logger.info("LLM explainer: Not configured (missing API credentials). Using fallback explanation.")
            fallback_explanation = self.explainer._generate_fallback_explanation(
                metrics, strategic_guidance
            )
            logger.info(f"Fallback Explanation: {fallback_explanation}")
            return fallback_explanation

    def _get_forecast_hash(self, forecast: ForecastData) -> str:
        """Generate a hash of the forecast to detect changes."""
        # Create a hash from key forecast characteristics
        # Use first 24 hours of data (sampled every hour to reduce sensitivity to minor variations)
        sample_indices = list(range(0, min(len(forecast.inflow_m3_s), 96), 4))  # Every hour (4 * 15min)
        inflow_samples = [forecast.inflow_m3_s[i] for i in sample_indices]
        price_samples = [forecast.price_c_per_kwh[i] for i in sample_indices]
        
        # Round to reduce sensitivity to tiny variations
        inflow_rounded = [round(x, 2) for x in inflow_samples]
        price_rounded = [round(x, 1) for x in price_samples]
        
        hash_input = f"{inflow_rounded}{price_rounded}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    def _should_refetch_strategic_plan(
        self,
        forecast_24h: ForecastData,
        current_state: CurrentState,
        previous_prediction: Optional[float] = None,
    ) -> bool:
        """Determine if we should refetch the strategic plan.
        
        Returns True if we should fetch a new plan, False if we can reuse cached one.
        """
        # Always fetch if no cache exists
        if self._cached_strategic_plan is None:
            return True
        
        # Check if cache has expired (time-based)
        if self._cached_strategic_plan_timestamp:
            age_minutes = (datetime.utcnow() - self._cached_strategic_plan_timestamp).total_seconds() / 60
            if age_minutes > self._strategic_plan_cache_ttl_minutes:
                logger.debug(f"Strategic plan cache expired (age: {age_minutes:.1f} min > {self._strategic_plan_cache_ttl_minutes} min)")
                return True
        
        # Check if forecasts have changed significantly
        current_hash = self._get_forecast_hash(forecast_24h)
        if current_hash != self._cached_forecast_hash:
            logger.debug("Strategic plan cache invalidated: forecasts changed significantly")
            return True
        
        # Check for divergence from predictions (if we have previous prediction)
        if previous_prediction is not None:
            divergence = self.optimizer.detect_divergence(
                current_state=current_state,
                forecast=forecast_24h,
                previous_prediction=previous_prediction,
            )
            if divergence:
                logger.info(f"Strategic plan cache invalidated: divergence detected ({divergence['error_type']})")
                return True
        
        # Check forecast quality - if quality is poor, we should refetch more frequently
        quality_patterns = self.forecast_quality_tracker.get_error_patterns()
        if quality_patterns.get('quality_level') == 'poor':
            # If quality is poor, reduce cache TTL to 15 minutes
            if self._cached_strategic_plan_timestamp:
                age_minutes = (datetime.utcnow() - self._cached_strategic_plan_timestamp).total_seconds() / 60
                if age_minutes > 15:  # Shorter TTL for poor quality forecasts
                    logger.debug("Strategic plan cache invalidated: poor forecast quality requires fresh strategy")
                    return True
        
        # Everything is working as predicted - reuse cached plan
        logger.debug("Reusing cached strategic plan (forecasts unchanged, no divergence detected)")
        return False
    
    def _get_strategic_plan(self, current_state: CurrentState, previous_prediction: Optional[float] = None) -> Optional[Any]:
        """Get strategic plan, using cache if appropriate."""
        try:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Get 24h forecast for strategic planning
            forecast_24h = self._get_forecasts(1440)  # 24 hours
            if not forecast_24h:
                return None
            
            # Check if we should reuse cached plan
            if not self._should_refetch_strategic_plan(forecast_24h, current_state, previous_prediction):
                logger.info("Reusing cached strategic plan (everything working as predicted)")
                return self._cached_strategic_plan
            
            # Fetch new strategic plan
            logger.info("Fetching new strategic plan (forecasts changed or cache expired)")
            strategic_plan = loop.run_until_complete(
                    self.explainer.generate_strategic_plan(
                        forecast_24h_timestamps=forecast_24h.timestamps,
                        forecast_24h_inflow=forecast_24h.inflow_m3_s,
                        forecast_24h_price=forecast_24h.price_c_per_kwh,
                    current_l1_m=current_state.l1_m,
                    l1_min_m=self.optimizer.constraints.l1_min_m,
                    l1_max_m=self.optimizer.constraints.l1_max_m,
                    forecast_quality_tracker=self.forecast_quality_tracker,  # Feed learnings back
                )
            )
            
            if strategic_plan:
                # Update cache
                self._cached_strategic_plan = strategic_plan
                self._cached_strategic_plan_timestamp = datetime.utcnow()
                self._cached_forecast_hash = self._get_forecast_hash(forecast_24h)
                
                logger.info(f"LLM Strategic Plan: {strategic_plan.plan_type}")
                logger.info(f"  Description: {strategic_plan.description}")
                logger.info(f"  Reasoning: {strategic_plan.reasoning[:200]}...")
            
            return strategic_plan
        except Exception as e:
            logger.warning(f"Failed to generate LLM strategic plan: {e}")
            # Return cached plan as fallback if available
            if self._cached_strategic_plan:
                logger.info("Using cached strategic plan as fallback after error")
                return self._cached_strategic_plan
            return None

    def _generate_fallback_schedule(self, request: OptimizationRequest) -> OptimizationResponse:
        """Generate a simple fallback schedule if optimization fails."""
        now = datetime.utcnow()
        start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
        entries = [
            ScheduleEntry(
                pump_id="P1",
                start_time=start,
                end_time=start + timedelta(minutes=request.horizon_minutes),
                target_frequency_hz=48.0,
            )
        ]
        return OptimizationResponse(
            generated_at=now,
            entries=entries,
            justification="Safe fallback schedule: maintaining minimum pumping for safety.",
            total_cost_eur=0.0,
            total_energy_kwh=0.0,
            optimization_mode="fallback",
        )


def serve() -> None:
    """Serve the optimization agent."""
    OptimizationAgent().serve()


if __name__ == "__main__":
    serve()

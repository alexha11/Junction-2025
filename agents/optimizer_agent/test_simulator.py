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
from .explainability import LLMExplainer, ScheduleMetrics, StrategicPlan, ForecastQualityTracker

logger = logging.getLogger(__name__)


def format_table(headers: List[str], rows: List[List[str]], width: int = 80) -> List[str]:
    """Format data as a table with borders.
    
    Args:
        headers: List of column headers
        rows: List of rows, each row is a list of cell values
        width: Total table width in characters
    
    Returns:
        List of formatted table lines
    """
    if not headers:
        return []
    
    # Calculate column widths (ensure headers fit)
    num_cols = len(headers)
    col_widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row[:num_cols]):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Add padding (minimum 2 spaces on each side)
    col_widths = [max(w + 4, 10) for w in col_widths]
    
    # Adjust total width to fit columns
    total_width = sum(col_widths) + num_cols + 1  # +1 for initial border, +num_cols for separators
    if total_width > width:
        # Scale down proportionally
        scale = (width - num_cols - 1) / sum(col_widths)
        col_widths = [max(int(w * scale), 8) for w in col_widths]
    
    lines = []
    border_char = "─"
    corner_tl = "┌"
    corner_tr = "┐"
    corner_bl = "└"
    corner_br = "┘"
    corner_cross = "┼"
    border_vertical = "│"
    border_horizontal = border_char * sum(col_widths) + border_char * (num_cols - 1)
    
    # Top border
    top_row = corner_tl
    for i, w in enumerate(col_widths):
        top_row += border_char * w
        if i < len(col_widths) - 1:
            top_row += corner_cross.replace("┼", "┬")
    top_row += corner_tr
    lines.append(top_row)
    
    # Header row
    header_row = border_vertical
    for i, (header, w) in enumerate(zip(headers, col_widths)):
        header_row += f" {str(header):<{w-2}} {border_vertical}"
    lines.append(header_row)
    
    # Separator row
    sep_row = corner_tl.replace("┌", "├")
    for i, w in enumerate(col_widths):
        sep_row += border_char * w
        if i < len(col_widths) - 1:
            sep_row += corner_cross
    sep_row = sep_row.replace("├", "├").replace("┐", "┤")
    lines.append(sep_row)
    
    # Data rows - handle cell wrapping
    for row in rows:
        # Wrap each cell value to fit column width
        wrapped_cells = []
        max_wrapped_lines = 1
        for i, w in enumerate(col_widths):
            cell_value = str(row[i]) if i < len(row) else ""
            cell_width = w - 2  # Account for padding spaces
            wrapped = wrap_text(cell_value, cell_width)
            wrapped_cells.append(wrapped)
            max_wrapped_lines = max(max_wrapped_lines, len(wrapped))
        
        # Create multiple rows if cells wrap
        for line_idx in range(max_wrapped_lines):
            data_row = border_vertical
            for i, w in enumerate(col_widths):
                wrapped = wrapped_cells[i]
                # Get the line for this cell, or empty if no more lines
                cell_line = wrapped[line_idx] if line_idx < len(wrapped) else ""
                data_row += f" {cell_line:<{w-2}} {border_vertical}"
            lines.append(data_row)
    
    # Bottom border
    bot_row = corner_bl
    for i, w in enumerate(col_widths):
        bot_row += border_char * w
        if i < len(col_widths) - 1:
            bot_row += corner_cross.replace("┼", "┴")
    bot_row += corner_br
    lines.append(bot_row)
    
    return lines


def wrap_text(text: str, max_width: int) -> List[str]:
    """Wrap text at word boundaries, respecting max width.
    
    Args:
        text: Text to wrap
        max_width: Maximum width per line
    
    Returns:
        List of wrapped lines
    """
    if not text:
        return []
    
    words = text.split()
    if not words:
        return [text]
    
    lines = []
    current_line = []
    current_length = 0
    
    for word in words:
        # Add 1 for space between words (except first word)
        word_length = len(word) + (1 if current_line else 0)
        
        if current_length + word_length <= max_width:
            current_line.append(word)
            current_length += word_length
        else:
            # Start new line
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_length = len(word)
            
            # If single word is too long, truncate it
            if current_length > max_width:
                lines.append(word[:max_width])
                current_line = []
                current_length = 0
    
    # Add remaining line
    if current_line:
        lines.append(" ".join(current_line))
    
    return lines if lines else [text[:max_width]]


def format_boxed_text(title: str, lines: List[str], width: int = 80) -> List[str]:
    """Format text in a box with borders.
    
    Args:
        title: Box title
        lines: List of content lines
        width: Box width in characters
    
    Returns:
        List of formatted box lines
    """
    result = []
    border_char = "─"
    corner_tl = "┌"
    corner_tr = "┐"
    corner_bl = "└"
    corner_br = "┘"
    border_vertical = "│"
    
    # Content width (accounting for borders and padding)
    content_width = width - 4  # 2 spaces + 2 border chars
    
    # Top border with title
    title_line = f" {title} "
    top_border = corner_tl + border_char * (width - 2) + corner_tr
    if len(title_line) <= width - 4:
        # Insert title into top border
        title_start = (width - len(title_line) - 2) // 2
        top_border = corner_tl + border_char * (title_start - 1) + title_line + border_char * (width - title_start - len(title_line) - 1) + corner_tr
    result.append(top_border)
    
    # Content lines with proper word wrapping
    if not lines:
        # Empty box - just add border
        result.append(f"{border_vertical}{' ' * (width - 2)}{border_vertical}")
    else:
        for line in lines:
            # Wrap long lines at word boundaries
            wrapped_lines = wrap_text(line, content_width)
            for wrapped_line in wrapped_lines:
                result.append(f"{border_vertical} {wrapped_line:<{content_width}} {border_vertical}")
    
    # Bottom border
    result.append(corner_bl + border_char * (width - 2) + corner_br)
    
    return result


def log_table(logger, headers: List[str], rows: List[List[str]], width: int = 80, include_header: bool = False, suppress_prefix: bool = True):
    """Log a table using the logger. Header only on first line if include_header=True.
    
    Args:
        logger: Logger instance
        headers: Table column headers
        rows: Table data rows
        width: Table width in characters
        include_header: Whether to include timestamp/module/level on first line
        suppress_prefix: If True, use print() for continuation lines (cleaner output)
    """
    import datetime
    table_lines = format_table(headers, rows, width)
    
    # Log lines based on suppress_prefix setting
    if suppress_prefix:
        # All lines clean (no prefix) - use print for all
        for line in table_lines:
            print(line)
    else:
        # All lines with prefix - use logger for all
        for line in table_lines:
            logger.info(line)  # Formatter adds prefix automatically


def log_boxed(logger, title: str, lines: List[str], width: int = 80, include_timestamp: bool = False, suppress_prefix: bool = True):
    """Log boxed text using the logger. Timestamp in title if include_timestamp=True.
    
    Args:
        logger: Logger instance
        title: Box title
        lines: Content lines
        width: Box width in characters
        include_timestamp: Whether to add timestamp to title
        suppress_prefix: If True, use print() for continuation lines (cleaner output)
    """
    import datetime
    
    # Add timestamp to title if requested
    if include_timestamp:
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        title_with_time = f"{title} [{timestamp}]"
    else:
        title_with_time = title
    
    box_lines = format_boxed_text(title_with_time, lines, width)
    
    # Log lines based on suppress_prefix setting
    if suppress_prefix:
        # All lines clean (no prefix) - use print for all
        for line in box_lines:
            print(line)
    else:
        # All lines with prefix - use logger for all
        for line in box_lines:
            logger.info(line)  # Formatter adds prefix automatically


@dataclass
class SimulationResult:
    """Results from rolling MPC simulation."""
    timestamp: datetime
    current_state: CurrentState
    optimization_result: OptimizationResult
    baseline_schedule: dict
    explanation: Optional[str] = None  # LLM explanation for this step
    strategy: Optional[str] = None  # Strategic guidance for this step
    strategic_plan: Optional[StrategicPlan] = None  # LLM-generated 24h strategic plan


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
        generate_explanations: bool = False,  # Default to False - explanations are slow
        generate_strategic_plan: bool = True,  # Default to True - strategic planning is fast and useful
        suppress_prefix: bool = True,
    ):
        """Initialize simulator.
        
        Args:
            data_loader: Loader for historical data
            optimizer: MPCOptimizer instance
            reoptimize_interval_minutes: Time between re-optimizations (default 15)
            forecast_method: 'perfect' or 'persistence' for forecasts
            llm_explainer: Optional LLM explainer for generating explanations per step
            generate_explanations: Whether to generate explanations for each optimization step (default: False - slow)
            generate_strategic_plan: Whether to generate 24h strategic plan (default: True - fast and useful)
            suppress_prefix: If True, suppress timestamp/module/level prefix on continuation lines (default: True)
        """
        self.data_loader = data_loader
        self.optimizer = optimizer
        self.reoptimize_interval_minutes = reoptimize_interval_minutes
        self.forecast_method = forecast_method
        self.llm_explainer = llm_explainer
        self.generate_explanations = generate_explanations and (llm_explainer is not None)
        self.generate_strategic_plan = generate_strategic_plan and (llm_explainer is not None)
        self.suppress_prefix = suppress_prefix
        # Initialize forecast quality tracker for recalibration loop
        self.forecast_quality_tracker = ForecastQualityTracker()
        # Track cumulative pump usage hours for fairness/rotation
        self.pump_usage_hours: Dict[str, float] = {}
        # Track how long each pump has been on/off (in minutes) for rotation-aware min duration
        # Format: {pump_id: {"on_minutes": float, "off_minutes": float}}
        self.pump_durations: Dict[str, Dict[str, float]] = {}

    def simulate(
        self,
        start_time: datetime,
        end_time: datetime,
        horizon_minutes: int = 120,  # 2-hour tactical horizon
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
        # For the FIRST step, we start with a fresh/sensible default pump state
        # (not copying old system decisions). We'll start with one small pump ON
        # to satisfy min_pumps_on constraint and let optimizer decide the rest.
        initial_state = self.data_loader.get_state_at_time(start_time, include_pump_states=False)
        if initial_state is None:
            raise ValueError(f"No data available at {start_time}")
        
        # Override with sensible initial state: one small pump ON at minimum frequency
        # This satisfies min_pumps_on=1 and gives optimizer flexibility
        # Start with pump 2.1 to avoid bias toward group 1
        initial_pump_states = []
        for pump_id, _, _ in initial_state.pump_states:
            # Start with pump 2.1 (small, group 2) at minimum frequency, all others OFF
            if pump_id == '2.1':
                initial_pump_states.append((pump_id, True, 47.8))  # ON at min frequency
            else:
                initial_pump_states.append((pump_id, False, 0.0))  # OFF
        initial_state.pump_states = initial_pump_states

        simulated_l1 = initial_state.l1_m
        
        dt_hours = self.reoptimize_interval_minutes / 60.0
        
        # Track which pumps are currently running (for reference only)
        currently_running_pumps: Set[str] = {'2.1'}  # Start with initial pump
        
        # Track flush events: when L1 last reached flush_target_level_m
        last_flush_time: Optional[datetime] = None
        flush_target = self.optimizer.constraints.flush_target_level_m
        
        # Forecast error tracking
        forecast_errors = {
            'inflow': [],  # List of (forecast, actual, error_pct) tuples
            'price': [],
            'l1': [],  # Predicted vs actual L1
        }
        window_size = 10  # Track last N steps for error analysis
        
        while current_time <= end_time:
            # Get current state from historical data (environmental inputs only: inflow, price, L1)
            # Pump states always come from previous optimization (or initial default)
            current_state = self.data_loader.get_state_at_time(current_time, include_pump_states=False)
            if current_state is None:
                # Skip if no data
                current_time += timedelta(minutes=self.reoptimize_interval_minutes)
                continue
            
            # Update simulated L1 (in real MPC, this would come from plant/simulator)
            # For testing, we use historical L1 but could simulate it forward
            current_state.l1_m = simulated_l1
            
            # Set pump states from previous optimization result (for continuity constraints)
            # This is what the optimizer needs to know: which pumps were on/off in the previous step
            # Also update pump durations for rotation-aware min duration constraints
            if len(simulation.results) > 0:
                prev_result = simulation.results[-1]
                if prev_result.optimization_result.success and prev_result.optimization_result.schedules:
                    # Get pump states from previous optimization's first step
                    # Map schedules to pump_states format: (pump_id, is_on, frequency_hz)
                    prev_pump_states = {}
                    for schedule in prev_result.optimization_result.schedules[:len(current_state.pump_states)]:
                        prev_pump_states[schedule.pump_id] = (schedule.pump_id, schedule.is_on, schedule.frequency_hz)
                    
                    # Update current_state pump_states with previous optimization results
                    updated_pump_states = []
                    for pump_id, _, _ in current_state.pump_states:
                        if pump_id in prev_pump_states:
                            updated_pump_states.append(prev_pump_states[pump_id])
                        else:
                            updated_pump_states.append((pump_id, False, 0.0))
                    current_state.pump_states = updated_pump_states
                    
                    # Update pump durations: increment on/off time for each pump
                    dt_minutes = self.reoptimize_interval_minutes
                    for pump_id, is_on, _ in updated_pump_states:
                        if pump_id not in self.pump_durations:
                            self.pump_durations[pump_id] = {"on_minutes": 0.0, "off_minutes": 0.0}
                        
                        if is_on:
                            # Pump is on: increment on time, reset off time
                            self.pump_durations[pump_id]["on_minutes"] += dt_minutes
                            self.pump_durations[pump_id]["off_minutes"] = 0.0
                        else:
                            # Pump is off: increment off time, reset on time
                            self.pump_durations[pump_id]["off_minutes"] += dt_minutes
                            self.pump_durations[pump_id]["on_minutes"] = 0.0
            else:
                # First step: initialize pump durations based on initial pump states
                for pump_id, is_on, _ in current_state.pump_states:
                    if pump_id not in self.pump_durations:
                        self.pump_durations[pump_id] = {"on_minutes": 0.0, "off_minutes": 0.0}
                    # Start with 0 duration (will be updated after first optimization)
            # else: use default pump states (all off) from data loader
            
            # Track forecast errors from previous step (compare forecast vs actual)
            if len(simulation.results) > 0:
                prev_result = simulation.results[-1]
                if prev_result.optimization_result.success and prev_result.optimization_result.l1_trajectory:
                    # Get actual values for the previous forecast's first step
                    prev_time = prev_result.timestamp
                    prev_forecast = self.data_loader.get_forecast_from_time(
                        prev_time, 1, method=self.forecast_method  # Just first step
                    )
                    if prev_forecast and len(prev_forecast.inflow_m3_s) > 0:
                        # Compare forecast vs actual
                        forecast_inflow = prev_forecast.inflow_m3_s[0]
                        actual_inflow = current_state.inflow_m3_s
                        forecast_price = prev_forecast.price_c_per_kwh[0]
                        actual_price = current_state.price_c_per_kwh
                        
                        # Calculate errors
                        inflow_error_pct = abs(actual_inflow - forecast_inflow) / max(forecast_inflow, 0.1) * 100 if forecast_inflow > 0 else 0
                        price_error_pct = abs(actual_price - forecast_price) / max(forecast_price, 1.0) * 100 if forecast_price > 0 else 0
                        
                        forecast_errors['inflow'].append((forecast_inflow, actual_inflow, inflow_error_pct))
                        forecast_errors['price'].append((forecast_price, actual_price, price_error_pct))
                        
                        # Track L1 prediction error
                        predicted_l1 = prev_result.optimization_result.l1_trajectory[0] if prev_result.optimization_result.l1_trajectory else simulated_l1
                        l1_error_m = abs(simulated_l1 - predicted_l1)
                        forecast_errors['l1'].append((predicted_l1, simulated_l1, l1_error_m))
                        
                        # Recalibration Loop: Feed errors back into quality tracker
                        self.forecast_quality_tracker.add_error(
                            inflow_error=inflow_error_pct,
                            price_error=price_error_pct,
                            l1_error=l1_error_m,
                            timestamp=current_time
                        )
                        
                        # Keep only last N errors
                        for key in forecast_errors:
                            if len(forecast_errors[key]) > window_size:
                                forecast_errors[key].pop(0)
                        
                        # Log significant errors
                        if inflow_error_pct > 20:
                            logger.warning(f"⚠ Large inflow forecast error: {inflow_error_pct:.1f}% (forecast={forecast_inflow:.2f}, actual={actual_inflow:.2f} m³/s)")
                        if price_error_pct > 30:
                            logger.warning(f"⚠ Large price forecast error: {price_error_pct:.1f}% (forecast={forecast_price:.1f}, actual={actual_price:.1f} c/kWh)")
                        if l1_error_m > 0.5:
                            logger.warning(f"⚠ Large L1 prediction error: {l1_error_m:.2f}m (predicted={predicted_l1:.2f}, actual={simulated_l1:.2f} m)")
            
            # Calculate forecast quality (optimizer will handle safety margins)
            forecast_quality = self._assess_forecast_quality(forecast_errors)
            
            # Get forecast (2h tactical)
            forecast = self.data_loader.get_forecast_from_time(
                current_time, horizon_steps, method=self.forecast_method
            )
            if forecast is None:
                current_time += timedelta(minutes=self.reoptimize_interval_minutes)
                continue
            
            # Detect divergence and generate emergency response if needed
            divergence = None
            emergency_response = None
            if len(simulation.results) > 0:
                prev_result = simulation.results[-1]
                if prev_result.optimization_result.success and prev_result.optimization_result.l1_trajectory:
                    # Get previous forecast values for divergence detection
                    prev_time = prev_result.timestamp
                    prev_forecast = self.data_loader.get_forecast_from_time(
                        prev_time, 1, method=self.forecast_method
                    )
                    
                    predicted_l1 = prev_result.optimization_result.l1_trajectory[0]
                    prev_forecast_inflow = prev_forecast.inflow_m3_s[0] if prev_forecast and len(prev_forecast.inflow_m3_s) > 0 else None
                    prev_forecast_price = prev_forecast.price_c_per_kwh[0] if prev_forecast and len(prev_forecast.price_c_per_kwh) > 0 else None
                    
                    # Detect divergence
                    divergence = self.optimizer.detect_divergence(
                        current_state=current_state,
                        forecast=forecast,  # Use current forecast for structure
                        previous_prediction=predicted_l1,
                        previous_forecast_inflow=prev_forecast_inflow,
                        previous_forecast_price=prev_forecast_price,
                    )
                    
                    # Generate emergency response if divergence detected and LLM available
                    if divergence and self.llm_explainer:
                        try:
                            try:
                                loop = asyncio.get_event_loop()
                            except RuntimeError:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                            
                            emergency_response = loop.run_until_complete(
                                self.llm_explainer.generate_emergency_response(
                                    error_type=divergence['error_type'],
                                    error_magnitude=divergence['error_magnitude'],
                                    forecast_value=divergence['forecast_value'],
                                    actual_value=divergence['actual_value'],
                                    current_l1_m=current_state.l1_m,
                                    l1_min_m=self.optimizer.constraints.l1_min_m,
                                    l1_max_m=self.optimizer.constraints.l1_max_m,
                                    predicted_l1_m=predicted_l1,
                                )
                            )
                            if emergency_response:
                                logger.warning("")
                                emergency_lines = [
                                    f"🚨 EMERGENCY RESPONSE TRIGGERED",
                                    f"Error Type: {divergence['error_type'].upper()}",
                                    f"Severity: {emergency_response.severity.upper()}",
                                    f"Magnitude: {divergence['error_magnitude']:.2f}",
                                    "",
                                    f"Forecast: {divergence['forecast_value']:.2f}",
                                    f"Actual: {divergence['actual_value']:.2f}",
                                    "",
                                    f"Reasoning: {emergency_response.reasoning[:200]}...",
                                ]
                                log_boxed(logger, "EMERGENCY RESPONSE", emergency_lines, width=80, include_timestamp=False, suppress_prefix=self.suppress_prefix)
                        except Exception as e:
                            logger.warning(f"Failed to generate emergency response: {e}")
            
            # Get 24h forecast for strategic planning (if LLM available and enabled)
            strategic_plan = None
            if self.generate_strategic_plan and self.llm_explainer:
                try:
                    # Request 24h forecast (96 steps of 15 minutes)
                    forecast_24h_steps = 24 * 60 // self.optimizer.time_step_minutes  # 96 steps
                    forecast_24h = self.data_loader.get_forecast_from_time(
                        current_time, forecast_24h_steps, method=self.forecast_method
                    )
                    if forecast_24h:
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        
                        strategic_plan = loop.run_until_complete(
                            self.llm_explainer.generate_strategic_plan(
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
                            # Blank line before plan table
                            if self.suppress_prefix:
                                print()
                            else:
                                logger.info("")
                            # Plan type and confidence in table
                            plan_rows = [
                                ["Plan Type", strategic_plan.plan_type],
                            ]
                            if strategic_plan.forecast_confidence:
                                plan_rows.append(["Forecast Confidence", strategic_plan.forecast_confidence.upper()])
                            
                            log_table(logger, ["Field", "Value"], plan_rows, width=80, include_header=False, suppress_prefix=self.suppress_prefix)
                            
                            # Description in boxed section for full-width display and proper wrapping
                            if strategic_plan.description:
                                # Wrap description text properly
                                desc_lines = wrap_text(strategic_plan.description, 76)  # 80 - 4 for borders
                                # Blank line before description box
                                if self.suppress_prefix:
                                    print()
                                else:
                                    logger.info("")
                                log_boxed(logger, "STRATEGIC PLAN DESCRIPTION", desc_lines, width=80, include_timestamp=False, suppress_prefix=self.suppress_prefix)
                            
                            # Time periods table
                            if strategic_plan.time_periods:
                                period_rows = []
                                for start_hour, end_hour, strategy in strategic_plan.time_periods[:4]:  # Show first 4 periods
                                    period_rows.append([f"{start_hour:02d}:00 - {end_hour:02d}:00", strategy])
                                # Blank line before time periods table
                                if self.suppress_prefix:
                                    print()
                                else:
                                    logger.info("")
                                log_table(logger, ["Time Period", "Strategy"], period_rows, width=80, include_header=False, suppress_prefix=self.suppress_prefix)
                            
                            # Reasoning in box (full text, properly wrapped)
                            if strategic_plan.reasoning:
                                # Split by newlines and process each paragraph
                                paragraphs = [p.strip() for p in strategic_plan.reasoning.split('\n\n') if p.strip()]
                                reasoning_lines = []
                                for para in paragraphs:
                                    # Split each paragraph by newlines (preserve intentional line breaks)
                                    para_lines = [line.strip() for line in para.split('\n') if line.strip()]
                                    for line in para_lines:
                                        # Wrap very long lines by sentences for better readability
                                        if len(line) > 200:
                                            import re
                                            sentences = re.split(r'([.!?]\s+)', line)
                                            current_sentence = ""
                                            for i in range(0, len(sentences), 2):
                                                if i + 1 < len(sentences):
                                                    sentence = sentences[i] + sentences[i+1]
                                                else:
                                                    sentence = sentences[i]
                                                if len(current_sentence) + len(sentence) > 200:
                                                    if current_sentence:
                                                        reasoning_lines.append(current_sentence.strip())
                                                    current_sentence = sentence
                                                else:
                                                    current_sentence += sentence
                                            if current_sentence:
                                                reasoning_lines.append(current_sentence.strip())
                                        else:
                                            reasoning_lines.append(line)
                                    # Add blank line between paragraphs
                                    if para != paragraphs[-1]:
                                        reasoning_lines.append("")
                                # Blank line before reasoning box
                                if self.suppress_prefix:
                                    print()
                                else:
                                    logger.info("")
                                log_boxed(logger, "STRATEGIC REASONING", reasoning_lines, width=80, include_timestamp=False, suppress_prefix=self.suppress_prefix)
                            
                            # Log recalibration loop status
                            quality_patterns = self.forecast_quality_tracker.get_error_patterns()
                            if quality_patterns['sample_size'] > 0:
                                recal_rows = [
                                    ["Quality", quality_patterns['overall_quality']],
                                    ["Trend", quality_patterns['trend']],
                                    ["Confidence", quality_patterns['confidence']],
                                    ["Sample Size", str(quality_patterns['sample_size'])],
                                ]
                                # Blank line before recalibration table
                                if self.suppress_prefix:
                                    print()
                                else:
                                    logger.info("")
                                log_table(logger, ["Metric", "Value"], recal_rows, width=80, include_header=False, suppress_prefix=self.suppress_prefix)
                except Exception as e:
                    logger.warning(f"  Failed to generate strategic plan: {e}")
            
            # Get baseline schedule for comparison
            baseline_schedule = self.data_loader.get_baseline_schedule_at_time(current_time)
            
            # Log current state in readable format
            step_num = len(simulation.results) + 1
            # Blank line before step header
            if self.suppress_prefix:
                print()
            else:
                logger.info("")
            log_boxed(logger, f"OPTIMIZATION STEP {step_num} | {current_time.strftime('%Y-%m-%d %H:%M:%S')}", [], width=80, include_timestamp=False, suppress_prefix=self.suppress_prefix)
            
            # Log system state as table
            system_state_rows = [
                ["Tunnel Level (L1)", f"{current_state.l1_m:.2f} m", f"[{self.optimizer.constraints.l1_min_m:.1f} - {self.optimizer.constraints.l1_max_m:.1f} m]"],
                ["Inflow (F1)", f"{current_state.inflow_m3_s:.2f} m³/s", ""],
                ["Outflow (F2)", f"{current_state.outflow_m3_s:.2f} m³/s", ""],
                ["Electricity Price", f"{current_state.price_c_per_kwh:.1f} c/kWh", ""],
            ]
            log_table(logger, ["Parameter", "Value", "Range/Status"], system_state_rows, width=80, include_header=False, suppress_prefix=self.suppress_prefix)
            
            # Log constraints table
            l1_min = self.optimizer.constraints.l1_min_m
            l1_max = self.optimizer.constraints.l1_max_m
            l1_current = current_state.l1_m
            
            # Check individual constraint compliance
            l1_above_min = l1_current >= l1_min
            l1_below_max = l1_current <= l1_max
            l1_in_range = l1_above_min and l1_below_max
            
            # Check pump constraints
            num_active_pumps = len([s for s in current_state.pump_states if s[1]])  # Count pumps that are ON
            min_pumps_ok = num_active_pumps >= self.optimizer.constraints.min_pumps_on
            
            constraints_rows = [
                ["L1 Min", f"{l1_min:.2f} m", f"{'✓ OK' if l1_above_min else '✗ VIOLATED'}"],
                ["L1 Max", f"{l1_max:.2f} m", f"{'✓ OK' if l1_below_max else '✗ VIOLATED'}"],
                ["L1 Current", f"{l1_current:.2f} m", f"{'✓ IN RANGE' if l1_in_range else '✗ VIOLATION'}"],
                ["Min Pumps On", f"{self.optimizer.constraints.min_pumps_on}", f"{'✓ OK' if min_pumps_ok else f'✗ VIOLATED (only {num_active_pumps})'}"],
                ["Active Pumps", f"{num_active_pumps}", f"{'✓' if min_pumps_ok else '✗'}"],
                ["Min On Duration", f"{self.optimizer.constraints.min_pump_on_duration_minutes} min", "⚠ Time-based"],
                ["Min Off Duration", f"{self.optimizer.constraints.min_pump_off_duration_minutes} min", "⚠ Time-based"],
            ]
            
            # Show frequency range from pump specs (use min/max from all pumps)
            freq_range_str = "47.8-50.0 Hz"  # Default
            if self.optimizer.pumps:
                # Get min/max from all pumps
                all_min_freqs = [spec.min_frequency_hz for spec in self.optimizer.pumps.values()]
                all_max_freqs = [spec.max_frequency_hz for spec in self.optimizer.pumps.values()]
                if all_min_freqs and all_max_freqs:
                    min_freq = min(all_min_freqs)
                    max_freq = max(all_max_freqs)
                    if min_freq == max_freq:
                        freq_range_str = f"{min_freq:.1f} Hz"
                    else:
                        freq_range_str = f"{min_freq:.1f}-{max_freq:.1f} Hz"
            
            # Note: Frequency violation check and constraints table logging
            # will be done after optimization result is available (see below)
            constraints_rows.append(["Allow L1 Violations", f"{'Yes' if self.optimizer.constraints.allow_l1_violations else 'No'}", ""])
            if self.optimizer.constraints.allow_l1_violations:
                constraints_rows.append(["Violation Tolerance", f"{self.optimizer.constraints.l1_violation_tolerance_m:.2f} m", ""])
                constraints_rows.append(["Violation Penalty", f"{self.optimizer.constraints.l1_violation_penalty:.1f}", ""])
            
            # Log pump states as table
            pump_rows = []
            active_pumps = []
            for pump_id, is_on, freq in current_state.pump_states:
                status = "ON" if is_on else "OFF"
                freq_str = f"{freq:.1f} Hz" if is_on else "---"
                pump_rows.append([pump_id, status, freq_str])
                if is_on:
                    active_pumps.append(pump_id)
            
            if pump_rows:
                # Blank line before pump table
                if self.suppress_prefix:
                    print()
                else:
                    logger.info("")
                log_table(logger, ["Pump ID", "Status", "Frequency"], pump_rows, width=80, include_header=True, suppress_prefix=self.suppress_prefix)
                logger.info(f"  Active pumps: {len(active_pumps)} ({', '.join(active_pumps) if active_pumps else 'None'})")
            
            # Run optimization (with strategic plan if available)
            # Blank line before optimization box
            if self.suppress_prefix:
                print()
            else:
                logger.info("")
            opt_info_lines = ["Running optimization..."]
            if strategic_plan:
                opt_info_lines.append(f"Strategic Plan: {strategic_plan.plan_type}")
            if len(forecast_errors['inflow']) > 0:
                avg_inflow_error = np.mean([e[2] for e in forecast_errors['inflow'][-5:]])  # Last 5 steps
                avg_price_error = np.mean([e[2] for e in forecast_errors['price'][-5:]])
                opt_info_lines.append(f"Forecast Quality: Inflow MAE={avg_inflow_error:.1f}%, Price MAE={avg_price_error:.1f}%")
                if forecast_quality['quality_level'] != 'good':
                    opt_info_lines.append(f"Quality Level: {forecast_quality['quality_level'].upper()} - Applying safety margins")
            log_boxed(logger, "OPTIMIZATION", opt_info_lines, width=80, include_timestamp=False, suppress_prefix=self.suppress_prefix)
            
            # Check if we're in critical conditions (disable rotation for safety)
            l1 = current_state.l1_m
            l1_range = self.optimizer.constraints.l1_max_m - self.optimizer.constraints.l1_min_m
            dist_to_min = (l1 - self.optimizer.constraints.l1_min_m) / l1_range
            dist_to_max = (self.optimizer.constraints.l1_max_m - l1) / l1_range
            is_critical = (dist_to_min < 0.15 or dist_to_max < 0.15)  # Within 15% of bounds
            
            # Calculate hours since last flush (for daily flush constraint)
            hours_since_last_flush = None
            if last_flush_time is not None:
                hours_since_last_flush = (current_time - last_flush_time).total_seconds() / 3600.0
            else:
                # If never flushed, use a large value to encourage first flush
                hours_since_last_flush = 25.0  # Slightly over 24h to trigger flush
            
            try:
                opt_result = self.optimizer.solve_optimization(
                    current_state=current_state,
                    forecast=forecast,
                    mode=OptimizationMode.FULL,
                    timeout_seconds=30,
                    strategic_plan=strategic_plan,  # Pass strategic plan to influence optimization
                    forecast_quality=forecast_quality,  # Pass forecast quality for safety margins
                    emergency_response=emergency_response,  # Pass emergency response if divergence detected
                    hours_since_last_flush=hours_since_last_flush,  # Pass flush tracking
                    pump_usage_hours=self.pump_usage_hours,  # Pass usage for fairness/rotation
                    pump_durations=self.pump_durations,  # Pass durations for rotation-aware min duration
                )
                result_rows = [
                    ["Mode", opt_result.mode.value.upper()],
                    ["Success", "✓" if opt_result.success else "✗"],
                    ["Solve Time", f"{opt_result.solve_time_seconds:.2f} s"],
                ]
                # Add violation info if present
                if opt_result.l1_violations > 0:
                    result_rows.append(["L1 Violations", f"{opt_result.l1_violations}", "⚠ WARNING"])
                    result_rows.append(["Max Violation", f"{opt_result.max_violation_m:.3f} m", "⚠ WARNING"])
                log_table(logger, ["Status", "Value", "Note"], result_rows, width=80, include_header=False, suppress_prefix=self.suppress_prefix)
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                logger.warning("")
                error_lines = [
                    f"Error: {str(e)}",
                    f"Error Type: {type(e).__name__}",
                    "Falling back to RULE_BASED mode"
                ]
                # Add traceback if it's a division by zero error
                if "division by zero" in str(e).lower() or "ZeroDivisionError" in str(type(e)):
                    error_lines.append("")
                    error_lines.append("Traceback (last 5 lines):")
                    tb_lines = error_details.strip().split('\n')
                    error_lines.extend(tb_lines[-5:])
                log_boxed(logger, "OPTIMIZATION FAILED", error_lines, width=80, include_timestamp=False, suppress_prefix=self.suppress_prefix)
                # Fallback on error
                opt_result = self.optimizer.solve_optimization(
                    current_state=current_state,
                    forecast=forecast,
                    mode=OptimizationMode.RULE_BASED,
                    timeout_seconds=10,
                    strategic_plan=strategic_plan,  # Pass strategic plan to fallback too
                    forecast_quality=forecast_quality,  # Pass forecast quality for safety margins
                    emergency_response=emergency_response,  # Pass emergency response if divergence detected
                    hours_since_last_flush=hours_since_last_flush,  # Pass flush tracking
                    pump_usage_hours=self.pump_usage_hours,  # Pass usage for fairness/rotation (unused in rule-based)
                    pump_durations=self.pump_durations,  # Pass durations for rotation-aware min duration
                )
                fallback_rows = [
                    ["Mode", opt_result.mode.value.upper()],
                    ["Success", "✓" if opt_result.success else "✗"],
                ]
                log_table(logger, ["Status", "Value"], fallback_rows, width=80, include_header=False, suppress_prefix=self.suppress_prefix)
            
            # Check frequency constraints from optimization result (not from current_state)
            # This checks the frequencies that were actually optimized, not historical values
            freq_ok = True
            freq_violations = []
            if opt_result.success and opt_result.schedules:
                # Check frequencies from optimization result schedules (time_step == 0)
                for sched in opt_result.schedules:
                    if sched.time_step == 0 and sched.is_on:
                        # Get pump spec for this pump
                        pump_spec = self.optimizer.pumps.get(sched.pump_id)
                        if pump_spec:
                            min_freq = pump_spec.min_frequency_hz
                            max_freq = pump_spec.max_frequency_hz
                            # Check if frequency is within valid range for this specific pump
                            if sched.frequency_hz < min_freq or sched.frequency_hz > max_freq:
                                freq_ok = False
                                freq_violations.append(f"{sched.pump_id}: {sched.frequency_hz:.1f} Hz (range: {min_freq:.1f}-{max_freq:.1f} Hz)")
                        else:
                            # Fallback: use default range if pump spec not found
                            if sched.frequency_hz < 47.8 or sched.frequency_hz > 50.0:
                                freq_ok = False
                                freq_violations.append(f"{sched.pump_id}: {sched.frequency_hz:.1f} Hz (spec not found)")
            
            # Add frequency constraint row with actual results from optimization
            constraints_rows.append(["Pump Frequency", freq_range_str, f"{'✓ OK' if freq_ok else '✗ VIOLATED (' + ', '.join(freq_violations) + ')'}"])
            
            # Log constraints table now that we have optimization results
            # Blank line before constraints table
            if self.suppress_prefix:
                print()
            else:
                logger.info("")
            log_table(logger, ["Constraint", "Value", "Status"], constraints_rows, width=80, include_header=False, suppress_prefix=self.suppress_prefix)
            
            # Log optimization result
            if opt_result.success:
                next_step_schedules = [s for s in opt_result.schedules if s.time_step == 0]
                # Blank line before schedule table
                if self.suppress_prefix:
                    print()
                else:
                    logger.info("")
                schedule_rows = []
                optimized_pumps = []
                total_flow = 0.0
                total_power = 0.0
                for sched in next_step_schedules:
                    if sched.is_on:
                        optimized_pumps.append(sched.pump_id)
                        schedule_rows.append([
                            sched.pump_id,
                            f"{sched.frequency_hz:.1f} Hz",
                            f"{sched.flow_m3_s:.2f} m³/s",
                            f"{sched.power_kw:.1f} kW"
                        ])
                        total_flow += sched.flow_m3_s
                        total_power += sched.power_kw
                
                if schedule_rows:
                    log_table(logger, ["Pump", "Frequency", "Flow", "Power"], schedule_rows, width=80, include_header=False, suppress_prefix=self.suppress_prefix)
                    summary_rows = [
                        ["Active Pumps", f"{len(optimized_pumps)} ({', '.join(optimized_pumps)})"],
                        ["Total Outflow", f"{total_flow:.2f} m³/s"],
                        ["Total Power", f"{total_power:.1f} kW"],
                    ]
                    if opt_result.l1_trajectory:
                        predicted_l1 = opt_result.l1_trajectory[0] if len(opt_result.l1_trajectory) > 0 else current_state.l1_m
                        # Check constraint compliance
                        l1_status = "✓" if self.optimizer.constraints.l1_min_m <= predicted_l1 <= self.optimizer.constraints.l1_max_m else "✗"
                        summary_rows.append(["Predicted L1 (next)", f"{predicted_l1:.2f} m", f"{l1_status} [{self.optimizer.constraints.l1_min_m:.1f} - {self.optimizer.constraints.l1_max_m:.1f} m]"])
                        # Check if predicted L1 violates constraints
                        if predicted_l1 < self.optimizer.constraints.l1_min_m:
                            violation = self.optimizer.constraints.l1_min_m - predicted_l1
                            summary_rows.append(["⚠ L1 Violation (below)", f"{violation:.3f} m", f"BELOW MIN ({self.optimizer.constraints.l1_min_m:.2f} m)"])
                        elif predicted_l1 > self.optimizer.constraints.l1_max_m:
                            violation = predicted_l1 - self.optimizer.constraints.l1_max_m
                            summary_rows.append(["⚠ L1 Violation (above)", f"{violation:.3f} m", f"ABOVE MAX ({self.optimizer.constraints.l1_max_m:.2f} m)"])
                    # Add overall violation summary if any
                    if opt_result.l1_violations > 0:
                        summary_rows.append(["⚠ Total Violations", f"{opt_result.l1_violations} steps", f"Max: {opt_result.max_violation_m:.3f} m"])
                        # Log detailed violation info
                        logger.warning(f"⚠ Constraint Violations: {opt_result.l1_violations} L1 violations detected (max: {opt_result.max_violation_m:.3f} m)")
                    log_table(logger, ["Metric", "Value", "Range/Status"], summary_rows, width=80, include_header=False, suppress_prefix=self.suppress_prefix)
                else:
                    log_boxed(logger, "OPTIMIZED SCHEDULE", ["No pumps active"], width=80, include_timestamp=False, suppress_prefix=self.suppress_prefix)
            else:
                log_boxed(logger, "OPTIMIZATION RESULT", ["✗ Optimization failed - using fallback"], width=80, include_timestamp=False, suppress_prefix=self.suppress_prefix)
            
            # Generate explanation for this step if enabled
            explanation = None
            strategy = None
            if self.generate_explanations and self.llm_explainer:
                try:
                    # Get strategic guidance
                    strategic_guidance = self.optimizer.derive_strategic_guidance(forecast)
                    strategy = ", ".join(set(strategic_guidance[:4]))
                    
                    # Blank line before strategy guidance box
                    if self.suppress_prefix:
                        print()
                    else:
                        logger.info("")
                    log_boxed(logger, "STRATEGY GUIDANCE", [strategy], width=80, include_timestamp=False, suppress_prefix=self.suppress_prefix)
                    
                    # Compute metrics for this step
                    metrics = self._compute_step_metrics(opt_result, forecast, current_state)
                    
                    # Build comprehensive state description for LLM
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
                    
                    # Generate LLM explanation asynchronously
                    logger.debug("GENERATING LLM EXPLANATION...")
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
                            strategic_plan=strategic_plan,
                        )
                    )
                    # Blank line before LLM explanation box
                    if self.suppress_prefix:
                        print()
                    else:
                        logger.info("")
                    # Split explanation by newlines and ensure proper word wrapping
                    if explanation:
                        # First split by explicit newlines, then by sentences for better line breaks
                        # Split by double newlines first (paragraph breaks)
                        paragraphs = [p.strip() for p in explanation.split('\n\n') if p.strip()]
                        explanation_lines = []
                        for para in paragraphs:
                            # Split each paragraph by newlines (preserve intentional line breaks)
                            para_lines = [line.strip() for line in para.split('\n') if line.strip()]
                            for line in para_lines:
                                # Further split very long lines by sentences for better wrapping
                                # If a line is very long (>200 chars), split by sentence endings
                                if len(line) > 200:
                                    import re
                                    sentences = re.split(r'([.!?]\s+)', line)
                                    # Rejoin sentences in pairs to avoid too many short lines
                                    current_sentence = ""
                                    for i in range(0, len(sentences), 2):
                                        if i + 1 < len(sentences):
                                            sentence = sentences[i] + sentences[i+1]
                                        else:
                                            sentence = sentences[i]
                                        if len(current_sentence) + len(sentence) > 200:
                                            if current_sentence:
                                                explanation_lines.append(current_sentence.strip())
                                            current_sentence = sentence
                                        else:
                                            current_sentence += sentence
                                    if current_sentence:
                                        explanation_lines.append(current_sentence.strip())
                                else:
                                    explanation_lines.append(line)
                        if not explanation_lines:
                            explanation_lines = ["No explanation available"]
                    else:
                        explanation_lines = ["No explanation available"]
                    log_boxed(logger, "LLM EXPLANATION", explanation_lines, width=80, include_timestamp=False, suppress_prefix=self.suppress_prefix)
                except Exception as e:
                    logger.warning(f"  Failed to generate explanation: {e}")
            
            # Update currently running pumps (for reference only)
            if opt_result.success and opt_result.schedules:
                for schedule in opt_result.schedules:
                    if schedule.time_step == 0:
                        pump_id = schedule.pump_id
                        if schedule.is_on:
                            currently_running_pumps.add(pump_id)
                        else:
                            currently_running_pumps.discard(pump_id)
            
            # Store result
            simulation_result = SimulationResult(
                timestamp=current_time,
                current_state=current_state,
                optimization_result=opt_result,
                baseline_schedule=baseline_schedule,
                explanation=explanation,
                strategy=strategy,
                strategic_plan=strategic_plan,
            )
            simulation.results.append(simulation_result)
            
            # Track trajectories
            simulation.optimized_l1_trajectory.append(simulated_l1)
            baseline_state = self.data_loader.get_state_at_time(current_time)
            if baseline_state:
                simulation.baseline_l1_trajectory.append(baseline_state.l1_m)
            
            # Check if flush occurred (L1 reached flush_target_level_m)
            # Consider it a flush if L1 is at or below flush target (within 0.1m tolerance)
            if simulated_l1 <= flush_target + 0.1:
                if last_flush_time is None or (current_time - last_flush_time).total_seconds() > 3600:  # At least 1h since last flush
                    last_flush_time = current_time
                    logger.debug(f"Flush detected: L1={simulated_l1:.3f}m reached flush target {flush_target}m at {current_time}")
            
            # Calculate energy and cost for this time step
            dt_hours = self.reoptimize_interval_minutes / 60.0
            
            # Update cumulative pump usage hours for fairness/rotation (only first step of horizon)
            if opt_result.success and opt_result.schedules:
                for schedule in opt_result.schedules:
                    if schedule.time_step == 0 and schedule.is_on:
                        pid = schedule.pump_id
                        self.pump_usage_hours[pid] = self.pump_usage_hours.get(pid, 0.0) + dt_hours
            
            # Optimized energy/cost (from optimization result, but only for current step)
            # For rolling simulation, we track cumulative
            if opt_result.success and opt_result.schedules:
                # Sum up power from schedules for first time step
                step_energy = 0.0
                step_cost = 0.0
                for schedule in opt_result.schedules:
                    if schedule.time_step == 0 and schedule.is_on:
                        step_energy += schedule.power_kw * dt_hours
                        step_cost += schedule.power_kw * dt_hours * (current_state.price_c_per_kwh / 100.0)
                
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
                    baseline_cost += pump_data['power_kw'] * dt_hours * (current_state.price_c_per_kwh / 100.0)
            
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
    
    def _assess_forecast_quality(self, forecast_errors: Dict) -> Dict:
        """Assess forecast quality based on recent errors.
        
        Returns:
            Dict with quality_level ('good', 'fair', 'poor') and metrics
        """
        if len(forecast_errors['inflow']) == 0:
            return {'quality_level': 'good', 'inflow_mae': 0, 'price_mae': 0, 'l1_mae': 0}
        
        # Calculate mean absolute errors over recent window
        recent_inflow_errors = [e[2] for e in forecast_errors['inflow'][-5:]]  # Last 5 steps
        recent_price_errors = [e[2] for e in forecast_errors['price'][-5:]]
        recent_l1_errors = [e[2] for e in forecast_errors['l1'][-5:]]
        
        inflow_mae = np.mean(recent_inflow_errors) if recent_inflow_errors else 0
        price_mae = np.mean(recent_price_errors) if recent_price_errors else 0
        l1_mae = np.mean(recent_l1_errors) if recent_l1_errors else 0
        
        # Determine quality level
        # Good: errors < 10%, Fair: 10-25%, Poor: > 25%
        max_error = max(inflow_mae, price_mae)
        if max_error < 10 and l1_mae < 0.3:
            quality_level = 'good'
        elif max_error < 25 and l1_mae < 0.5:
            quality_level = 'fair'
        else:
            quality_level = 'poor'
        
        return {
            'quality_level': quality_level,
            'inflow_mae': inflow_mae,
            'price_mae': price_mae,
            'l1_mae': l1_mae,
        }
    
    def _adjust_constraints_for_forecast_quality(
        self, constraints, forecast_quality: Dict
    ) -> Dict:
        """Adjust constraints based on forecast quality to add safety margins.
        
        Args:
            constraints: SystemConstraints instance
            forecast_quality: Quality assessment dict
        
        Returns:
            Dict with adjusted l1_min_m and l1_max_m
        """
        quality_level = forecast_quality['quality_level']
        inflow_mae = forecast_quality['inflow_mae']
        
        # Base constraints
        adjusted_min = constraints.l1_min_m
        adjusted_max = constraints.l1_max_m
        
        # Add safety margins based on forecast quality
        if quality_level == 'poor':
            # Large errors: significant safety margins
            # Reduce max by up to 1.5m to protect against surge, increase min by 0.3m for buffer
            safety_margin_max = min(1.5, inflow_mae / 100 * 5)  # Proportional to error
            safety_margin_min = 0.3
            adjusted_max = constraints.l1_max_m - safety_margin_max
            adjusted_min = constraints.l1_min_m + safety_margin_min
        elif quality_level == 'fair':
            # Medium errors: moderate safety margins
            safety_margin_max = min(0.8, inflow_mae / 100 * 3)
            safety_margin_min = 0.2
            adjusted_max = constraints.l1_max_m - safety_margin_max
            adjusted_min = constraints.l1_min_m + safety_margin_min
        # 'good' quality: use base constraints
        
        # Ensure adjusted constraints are still valid
        adjusted_min = max(constraints.l1_min_m * 0.8, adjusted_min)  # Don't go too low
        adjusted_max = min(constraints.l1_max_m * 1.1, adjusted_max)  # Don't go too high
        adjusted_max = max(adjusted_min + 0.5, adjusted_max)  # Ensure min < max
        
        return {
            'l1_min_m': adjusted_min,
            'l1_max_m': adjusted_max,
        }
    
    def _compute_step_metrics(
        self,
        result: OptimizationResult,
        forecast: ForecastData,
        current_state: CurrentState,
    ) -> ScheduleMetrics:
        """Compute metrics for a single optimization step."""
        if not result.l1_trajectory:
            # Forecast prices are already in c/kWh in ForecastData
            min_price = min(forecast.price_c_per_kwh)
            max_price = max(forecast.price_c_per_kwh)
            return ScheduleMetrics(
                total_energy_kwh=result.total_energy_kwh,
                total_cost_eur=result.total_cost_eur,
                avg_l1_m=current_state.l1_m,
                min_l1_m=current_state.l1_m,
                max_l1_m=current_state.l1_m,
                num_pumps_used=len([s for s in result.schedules if s.time_step == 0 and s.is_on]),
                avg_outflow_m3_s=sum(s.flow_m3_s for s in result.schedules if s.time_step == 0 and s.is_on),
                price_range_c_per_kwh=(min_price, max_price),
                risk_level="normal",
                optimization_mode=result.mode.value,
            )
        
        min_price = min(forecast.price_c_per_kwh)
        max_price = max(forecast.price_c_per_kwh)
        return ScheduleMetrics(
            total_energy_kwh=result.total_energy_kwh,
            total_cost_eur=result.total_cost_eur,
            avg_l1_m=sum(result.l1_trajectory) / len(result.l1_trajectory),
            min_l1_m=min(result.l1_trajectory),
            max_l1_m=max(result.l1_trajectory),
            num_pumps_used=len(set(s.pump_id for s in result.schedules if s.is_on)),
            avg_outflow_m3_s=sum(s.flow_m3_s for s in result.schedules if s.time_step == 0 and s.is_on),
            price_range_c_per_kwh=(min_price, max_price),
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
        
        # Calculate pump operating hours
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
        # Use mass balance: Total Volume Pumped = Total Inflow - Change in Tunnel Storage
        # Both systems handle the same inflow, so volumes should be nearly identical
        # (only differ by tunnel storage changes)
        
        # Calculate total inflow over the period
        total_inflow_volume = 0.0
        for result in simulation.results:
            # Get inflow for this time step
            current_state = self.data_loader.get_state_at_time(result.timestamp)
            if current_state:
                total_inflow_volume += current_state.inflow_m3_s * dt_hours * 3600  # Convert to m³
        
        # Calculate tunnel storage change
        # Tunnel area = tunnel_volume / L1_range = 50000 / 8 = 6250 m²
        tunnel_area_m2 = self.optimizer.constraints.tunnel_volume_m3 / (self.optimizer.constraints.l1_max_m - self.optimizer.constraints.l1_min_m)
        
        # Get initial and final L1 for both trajectories
        if len(simulation.optimized_l1_trajectory) > 0 and len(simulation.baseline_l1_trajectory) > 0:
            optimized_l1_initial = simulation.optimized_l1_trajectory[0]
            optimized_l1_final = simulation.optimized_l1_trajectory[-1]
            baseline_l1_initial = simulation.baseline_l1_trajectory[0]
            baseline_l1_final = simulation.baseline_l1_trajectory[-1]
            
            # Storage change = (L1_final - L1_initial) × tunnel_area
            optimized_storage_change = (optimized_l1_final - optimized_l1_initial) * tunnel_area_m2
            baseline_storage_change = (baseline_l1_final - baseline_l1_initial) * tunnel_area_m2
            
            # Total volume pumped = inflow - storage_change
            total_optimized_volume = total_inflow_volume - optimized_storage_change
            total_baseline_volume = total_inflow_volume - baseline_storage_change
        else:
            # Fallback to summing flows if trajectories not available
            total_optimized_volume = sum(
                sum(s.flow_m3_s * dt_hours * 3600 for s in result.optimization_result.schedules if s.time_step == 0 and s.is_on)
                for result in simulation.results
            )
            total_baseline_volume = sum(
                sum(pump_data['flow_m3_s'] * dt_hours * 3600 for pump_data in result.baseline_schedule.values() if pump_data['is_on'])
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


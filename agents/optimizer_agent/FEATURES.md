# Optimizer Agent Features

This document consolidates all features, error handling strategies, and implementation details for the optimizer agent.

---

## Table of Contents

1. [Forecast Methods](#forecast-methods)
2. [Forecast Error Handling](#forecast-error-handling)
3. [Reactive Error Handling](#reactive-error-handling)
4. [LLM Strategic Planning](#llm-strategic-planning)
5. [LLM Emergency Response](#llm-emergency-response)

---

## Forecast Methods

The test simulator uses different methods to simulate forecasts for testing the optimizer's behavior under various forecast accuracy scenarios.

### 1. Perfect Forecast (`method='perfect'`)

Uses historical future data as a "perfect forecast" - simulating perfect foresight.

**How it works:**
- Starting from the current timestamp, it looks forward in the historical data
- Extracts the actual future values for inflow and price
- Returns these as the forecast

**Use cases:**
- Testing optimal performance (best-case scenario)
- Validating optimization logic without forecast error noise
- Benchmarking against baseline when optimizer has perfect information

### 2. Persistence Forecast (`method='persistence'`)

Uses the last known value repeated forward - simulating a naive forecast.

**How it works:**
- Takes the inflow and price value from the previous time step
- Repeats these values for all future time steps in the forecast horizon

**Use cases:**
- Testing robustness to forecast errors
- Simulating realistic forecast limitations
- Testing how optimizer handles constant forecast assumptions

**Usage:**
```bash
# Perfect forecast
python test_optimizer_with_data.py --forecast-method perfect

# Persistence forecast
python test_optimizer_with_data.py --forecast-method persistence
```

---

## Forecast Error Handling

### Problem Statement

When forecasts (inflow, price) are wrong, the MPC optimizer may:
- Make sub-optimal decisions based on incorrect assumptions
- Violate safety constraints (L1 bounds) if inflow is severely underestimated
- Miss cost-saving opportunities if price forecast is inaccurate
- Accumulate errors over the optimization horizon

### Multi-Layer Strategy

#### Layer 1: Forecast Error Detection & Tracking

**Purpose**: Monitor forecast accuracy in real-time and detect large errors.

**Implementation**:
- Track forecast vs actual for each time step
- Calculate forecast error metrics:
  - **Inflow Error**: `|actual_inflow - forecast_inflow| / actual_inflow`
  - **Price Error**: `|actual_price - forecast_price| / actual_price`
  - **MAE** (Mean Absolute Error) over recent N steps
  - **Bias**: Systematic over/under-forecasting

**Error Thresholds**:
- **Small errors** (< 10%): Normal operation, minor impact
- **Medium errors** (10-25%): Trigger conservative adjustments
- **Large errors** (> 25%): Activate robust optimization mode

#### Layer 2: Robust Optimization with Safety Margins

**Purpose**: Add safety buffers when forecast uncertainty is high.

**Implementation**:
- **Dynamic Safety Margins**: Adjust L1 bounds based on forecast error
  - If inflow forecast error > 20%: Reduce L1_max by 0.5m (buffer for surge)
  - If price forecast error > 30%: Use conservative cost estimates
- **Forecast Quality Weights**: Adjust optimization weights
  - High confidence: Trust forecast, optimize aggressively
  - Low confidence: Add safety margins, be more conservative

#### Layer 3: Forecast Quality Assessment

**Purpose**: Adjust optimization behavior based on historical forecast quality.

**Implementation**:
- Track forecast errors over sliding window (default: 50 steps)
- Calculate quality metrics:
  - Overall quality (good, fair, poor)
  - Mean Absolute Error (MAE) for each error type
  - Trend analysis (improving, stable, worsening)
  - Forecast confidence assessment (high, medium, low)

**Class**: `ForecastQualityTracker`

**Methods**:
- `add_error()`: Add forecast errors to tracker
- `get_error_patterns()`: Analyze patterns and return summary statistics
- `get_surge_period_confidence()`: Assess confidence for surge periods

---

## Reactive Error Handling

### Detection Phase

**What triggers detection:**

1. **L1 Divergence**: `|actual_L1 - predicted_L1| > 0.5m`
2. **Inflow Surge**: `actual_inflow > forecast_inflow * 1.3` (30% higher)
3. **Price Spike**: `actual_price > forecast_price * 1.5` (50% higher)
4. **Cumulative Error**: Multiple consecutive errors indicating systematic issue

**Method**: `MPCOptimizer.detect_divergence()`

### Optimizer Actions (Automatic)

**Immediate Actions:**
1. **Re-optimize immediately** with updated actual values
2. **Apply emergency safety margins**:
   - If inflow surge: Reduce L1_max by 1.0-1.5m
   - If price spike: Prioritize minimum pumping only
   - If L1 diverging: Increase safety margin weight by 2x
3. **Switch to conservative mode**:
   - Increase safety margin weight
   - Reduce cost optimization weight
   - Prioritize constraint satisfaction

**Constraint Adjustments**:
- **Poor forecast quality**: L1 bounds tightened by 0.5-1.5m
- **High error rate**: Safety margin weight increased 1.5-2x
- **Emergency mode**: Cost optimization reduced to 0.3x

### Integration Flow

```
1. Detect Divergence
   ↓
2. Optimizer: Immediate Re-optimization
   - Apply emergency safety margins
   - Adjust weights for conservative mode
   ↓
3. LLM: Generate Emergency Strategy (optional)
   - Analyze error type and severity
   - Recommend immediate actions
   - Explain reasoning
   ↓
4. Optimizer: Execute Emergency Plan
   - Apply LLM-recommended adjustments
   - Re-optimize with emergency constraints
   ↓
5. Monitor & Adjust
   - Track if error persists
   - Continue emergency mode if needed
   - Return to normal when stable
```

---

## LLM Strategic Planning

### Overview

The LLM acts as an adaptive strategist that:
1. **Analyzes forecast error patterns** and adjusts the 24h strategic plan accordingly
2. **Recommends PUMP_CONSERVATIVE** when forecast uncertainty is high
3. **Suggests building larger buffers** before surge periods with poor forecast confidence
4. **Implements a recalibration loop** that learns from errors over time

### Enhanced Strategic Planning

#### A. Analyze Forecast Error Patterns
- Receives historical error data from `ForecastQualityTracker`
- Analyzes overall quality, trend, and confidence
- Adjusts strategic plan based on error patterns:
  - If errors are **worsening**: More conservative approach
  - If errors are **improving**: Can be more aggressive
  - If errors are **stable**: Balanced approach

#### B. Recommend PUMP_CONSERVATIVE Strategy
- When forecast confidence is **LOW**: Recommends `PUMP_CONSERVATIVE`
- When forecast uncertainty is **HIGH**: Suggests conservative approach
- Applies larger safety margins when confidence is low

**Weight Adjustments for PUMP_CONSERVATIVE**:
- **Cost weight**: 0.5x (reduce cost optimization significantly)
- **Energy weight**: 0.6x (reduce energy optimization)
- **Safety margin weight**: 2.0x (double safety margin weight)
- **Smoothness weight**: 1.1x (maintain stability)

#### C. Build Larger Buffer Before Surge Periods
- Identifies surge periods in forecast (inflow > 1.3x average)
- Assesses confidence for each surge period
- If surge confidence is **LOW**: Recommends building larger buffer before surge
- Suggests more aggressive pumping **before** surge to protect against uncertainty

### Recalibration Loop

**Purpose**: Feed learnings back into strategic planning

**Flow**:
```
1. Track Errors
   ↓
2. Update ForecastQualityTracker
   ↓
3. Analyze Error Patterns
   ↓
4. Feed to LLM for Strategic Planning
   ↓
5. LLM Adjusts Strategy Based on Errors
   ↓
6. Repeat (continuous learning)
```

### Available Strategies

- **PUMP_AGGRESSIVE**: Emphasize cost optimization, allow more pumping (high confidence)
- **PUMP_MINIMAL**: Minimize pumping, prioritize safety
- **PUMP_CONSERVATIVE**: Conservative approach when forecast uncertainty is high (NEW)
- **MAINTAIN_BUFFER**: Build buffer before surge/expensive periods
- **BALANCED**: Balanced approach with normal weights

---

## LLM Emergency Response

### Overview

When actual data diverges from forecast data, the **LLM** can generate emergency strategies that the optimizer then applies.

### Step 1: LLM Generates Emergency Strategy

**Method**: `LLMExplainer.generate_emergency_response()`

**LLM Actions:**
1. **Analyzes the error**:
   - Determines severity (low, medium, high, critical)
   - Understands the nature of the error
   - Considers current system state (L1, constraints)

2. **Generates Emergency Response**:
   - **Immediate Actions**: List of specific actions to take
   - **Reasoning**: Explains why actions are necessary
   - **Constraint Adjustments**: Suggests L1 bounds changes
   - **Weight Adjustments**: Suggests optimization weight changes

### Step 2: Optimizer Applies Emergency Response

**Method**: `MPCOptimizer.apply_emergency_response()`

**Optimizer Actions:**

1. **Constraint Adjustments** (based on error type):
   - **Inflow Surge**: 
     - Reduce L1_max by 1.0-1.5m (protect against overflow)
     - Increase L1_min by 0.3m (add buffer)
   - **Price Spike**: 
     - No constraint changes (safety first)
   - **L1 Divergence**: 
     - Tighten bounds around current L1 position

2. **Weight Adjustments** (based on severity):
   - **High/Critical Severity**:
     - Safety margin weight: **2.0x** (double)
     - Cost weight: **0.3x** (reduce by 70%)
     - Energy weight: **0.5x** (reduce by 50%)
   - **Medium Severity**:
     - Safety margin weight: **1.5x**
     - Cost weight: **0.6x**
     - Energy weight: **0.7x**

3. **Re-optimization**:
   - Immediately re-optimizes with adjusted constraints and weights
   - Prioritizes safety over cost optimization
   - Uses emergency mode settings

### Error Types Handled

1. **Inflow Surge**: Sudden increase in wastewater inflow
2. **Price Spike**: Unexpected electricity price increase
3. **L1 Divergence**: Tunnel level not following predicted trajectory
4. **Systematic Bias**: Consistent forecast errors over time

### Severity Levels

- **Critical**: Requires immediate action, all safety measures
- **High**: Significant adjustments, prioritize safety
- **Medium**: Moderate adjustments, balanced approach
- **Low**: Minor adjustments, continue normal operation

---

## Integration Points

### In `test_simulator.py`:
- Track forecast errors after each step
- Compare actual vs predicted values
- Trigger adaptive re-optimization
- Apply reactive corrections
- Initialize `ForecastQualityTracker`
- Pass tracker to LLM for strategic planning

### In `optimizer.py`:
- Accept forecast quality/error information
- Adjust constraints based on forecast uncertainty
- Modify weights based on forecast confidence
- Implement robust optimization modes
- Detect divergence automatically
- Apply emergency responses

### In `explainability.py`:
- Generate 24h strategic plans based on forecast quality
- Generate emergency responses for significant errors
- Analyze forecast error patterns
- Recommend conservative strategies when needed

---

## Example Scenarios

### Scenario 1: Low Forecast Confidence

**Situation**:
- Historical errors: Inflow MAE = 28%, Price MAE = 22%
- Trend: Worsening (errors increasing over time)
- Confidence: LOW

**LLM Response**:
- PLAN_TYPE: PUMP_CONSERVATIVE
- Prioritizes safety with conservative pumping strategy
- Doubles safety margin weight, reduces cost optimization

### Scenario 2: Inflow Surge Detected

**Detection**: Actual inflow = 4.0 m³/s, Forecast = 2.0 m³/s (100% error)

**Optimizer Actions**:
1. Immediately re-optimize with actual inflow
2. Reduce L1_max from 8.0m to 6.5m (safety margin)
3. Increase safety margin weight by 2x
4. Activate all available pumps if L1 > 6.0m

**LLM Actions** (optional):
1. Generate emergency strategy: "Inflow surge detected - activating all pumps"
2. Explain: "Forecast underestimated inflow by 100%. This could cause tunnel overflow."
3. Recommend: "Activate all pumps, reduce L1_max to 6.5m, monitor every 5 minutes"

### Scenario 3: Surge Period with Low Confidence

**Situation**:
- Forecast: Inflow surge at hour 14-16 (3.5 m³/s)
- Historical surge forecast errors: HIGH (30%+ MAE)
- Surge confidence: LOW

**LLM Response**:
- Hours 0-10: PUMP_AGGRESSIVE - Build buffer during cheap prices
- Hours 10-14: MAINTAIN_BUFFER - Continue building buffer before surge
- Hours 14-18: PUMP_CONSERVATIVE - Conservative approach for surge period
- Reasoning: "Surge forecasted but historical surge forecasts have 30%+ error rate. Building larger buffer to protect against potential forecast underestimation."

---

## Benefits

1. **Adaptive Learning**: System learns from forecast errors and improves over time
2. **Risk Management**: Automatically becomes conservative when forecasts are unreliable
3. **Safety First**: Prioritizes safety when confidence is low
4. **Cost Optimization**: Optimizes aggressively when confidence is high
5. **Surge Protection**: Builds larger buffers when surge forecasts are uncertain
6. **Explainable**: LLM provides reasoning for all strategic and emergency decisions
7. **Coordinated Response**: LLM and optimizer work together for optimal safety

---

## Future Enhancements

1. **Bias Correction**: Automatically apply correction factors for systematic biases
2. **Model Updates**: Suggest forecast model updates based on error patterns
3. **Confidence Intervals**: Use probabilistic forecasts with confidence intervals
4. **Temporal Patterns**: Learn time-of-day or weather-dependent error patterns
5. **Multi-model Ensemble**: Combine multiple forecast sources for better confidence
6. **Adaptive Re-optimization Frequency**: Adjust re-optimization interval based on forecast quality


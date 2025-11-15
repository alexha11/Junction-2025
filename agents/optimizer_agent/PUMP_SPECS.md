# Hardcoded Pump Specifications

## Rationale

Previously, the optimizer extracted pump specifications from historical operational data using `get_pump_specs_from_data()`. This created **circular reasoning**: we were calibrating a new strategy based on the old system's decisions, which had constraint violations.

Now pump specs are **hardcoded** to represent **physical pump capacities** (not old system strategy).

## Pump Specifications

Based on analysis of the maximum observed operational values in `Hackathon_HSY_data.xlsx`:

### Small Pumps (~0.5 m³/s)
- **1.1**: 0.513 m³/s, 191.7 kW, L1 slope: 3.83 kW/m
- **2.1**: 0.500 m³/s, 196.3 kW, L1 slope: 3.93 kW/m

### Big Pumps (~1.0 m³/s)
- **1.2**: 1.003 m³/s, 380.1 kW, L1 slope: 7.60 kW/m
- **1.4**: 0.947 m³/s, 400.7 kW, L1 slope: 8.01 kW/m
- **2.2**: 1.002 m³/s, 407.0 kW, L1 slope: 8.14 kW/m
- **2.3**: 0.986 m³/s, 396.2 kW, L1 slope: 7.92 kW/m
- **2.4**: 0.993 m³/s, 373.2 kW, L1 slope: 7.46 kW/m

### Big Pumps (continued)
- **1.3**: 1.0 m³/s, 400 kW, L1 slope: 8.0 kW/m (now included in optimization)

### Fixed Hardware Specifications
- **Min frequency**: 47.8 Hz (industry standard)
- **Max frequency**: 50.0 Hz (industry standard)
- **Preferred range**: 47.8-49.0 Hz
- **L1 reference**: 4.0 m (for power correction)

## Power vs L1 Relationship

The `power_vs_l1_slope_kw_per_m` represents the **lifting height effect**:
- Higher L1 = less lifting height needed = less power required
- Approximately **4 kW/m for small pumps**, **8 kW/m for big pumps**
- This is a physical relationship (not strategy), extracted from pump curves

## Initial Pump State

The simulator now starts with a **fresh/sensible default**:
- **Pump 1.1** (small): ON at 47.8 Hz (minimum frequency)
- **All others**: OFF

This satisfies `min_pumps_on=1` constraint while giving the optimizer maximum flexibility. We no longer copy the old system's pump states at midnight.

## Benefits of Hardcoding

✅ **Independent** from old strategy decisions  
✅ **Deterministic** (no data analysis uncertainty)  
✅ **Faster** initialization (no statistical analysis)  
✅ **Portable** (can test without full Excel file if needed)  
✅ **Transparent** (specs are visible in code)

## What We Still Use from CSV

Only **environmental inputs** (physical constraints, not old decisions):
1. **Water level L1** - current physical state
2. **Inflow F1** - water coming in (cannot control)
3. **Electricity price** - external economic constraint

We do NOT use:
- ❌ Old pump flow decisions (was output from old system)
- ❌ Old pump frequency decisions (was output from old system)
- ❌ Old pump power measurements (result of old decisions)
- ❌ Old total outflow F2 (result of old decisions)

## Location

Hardcoded specs are in: `agents/optimizer_agent/test_optimizer_with_data.py:28-38`

The old extraction method `get_pump_specs_from_data()` is now deprecated but kept in `test_data_loader.py` for reference.

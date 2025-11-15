#!/usr/bin/env python3
"""
Quick test to verify pump rotation logic triggers after 6 hours.
Runs just 8 hours of simulation and reports pump operating hours.
"""
import sys
from pathlib import Path
from datetime import timedelta
import logging

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.optimizer_agent.test_data_loader import HSYDataLoader
from agents.optimizer_agent.test_optimizer_with_data import create_optimizer_from_data
from agents.optimizer_agent.test_simulator import RollingMPCSimulator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def main():
    # Load data
    data_file = Path(__file__).parent / "Hackathon_HSY_data.xlsx"
    logger.info(f"Loading data from {data_file}")
    data_loader = HSYDataLoader(str(data_file), price_type="normal")
    
    # Create optimizer
    optimizer = create_optimizer_from_data(data_loader)
    logger.info(f"Optimizer created with {len(optimizer.pumps)} pumps")
    
    # Create simulator (no LLM for speed)
    simulator = RollingMPCSimulator(
        data_loader=data_loader,
        optimizer=optimizer,
        reoptimize_interval_minutes=15,
        forecast_method='perfect',
        llm_explainer=None,
        generate_explanations=False,
        generate_strategic_plan=False,
        suppress_prefix=True,
    )
    
    # Run just 8 hours
    data_start, _ = data_loader.get_data_range()
    simulation_start = data_start
    simulation_end = simulation_start + timedelta(hours=8)
    
    logger.info(f"Running simulation: {simulation_start} to {simulation_end} (8 hours)")
    logger.info("=" * 80)
    
    simulation = simulator.simulate(
        start_time=simulation_start,
        end_time=simulation_end,
        horizon_minutes=120,  # 2-hour tactical horizon
    )
    
    logger.info("=" * 80)
    logger.info(f"Simulation complete: {len(simulation.results)} steps")
    
    # Calculate pump operating hours
    pump_hours = {}
    dt_hours = 15 / 60.0  # 15 minutes
    
    for result in simulation.results:
        for schedule in result.optimization_result.schedules:
            if schedule.time_step == 0 and schedule.is_on:
                pump_id = schedule.pump_id
                pump_hours[pump_id] = pump_hours.get(pump_id, 0.0) + dt_hours
    
    # Group by capacity
    small_pumps = []
    big_pumps = []
    for pid in optimizer.pumps.keys():
        if optimizer.pumps[pid].max_flow_m3_s <= 0.5 + 1e-6:
            small_pumps.append(pid)
        else:
            big_pumps.append(pid)
    
    print("\n" + "=" * 80)
    print("PUMP OPERATING HOURS (8-hour simulation)")
    print("=" * 80)
    print("\nSmall Pumps (0.5 m³/s):")
    for pid in sorted(small_pumps):
        hours = pump_hours.get(pid, 0.0)
        print(f"  {pid}: {hours:.2f}h")
    
    print("\nBig Pumps (1.0 m³/s):")
    for pid in sorted(big_pumps):
        hours = pump_hours.get(pid, 0.0)
        print(f"  {pid}: {hours:.2f}h")
    
    # Check if rotation happened
    print("\n" + "=" * 80)
    if len(pump_hours) > 1:
        print("✓ SUCCESS: Multiple pumps were used")
        print(f"  Total pumps active: {len(pump_hours)}")
    else:
        print("✗ FAILED: Only one pump was used")
        print("  Rotation logic may not be working correctly")
    print("=" * 80)

if __name__ == "__main__":
    main()

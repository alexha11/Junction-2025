"""Main test script for testing optimizer with Hackathon_HSY_data.xlsx."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

import os
from dotenv import load_dotenv

from .test_data_loader import HSYDataLoader
from .test_simulator import RollingMPCSimulator
from .test_metrics import MetricsCalculator
from .optimizer import MPCOptimizer, PumpSpec, SystemConstraints
from .explainability import LLMExplainer, ScheduleMetrics


def create_optimizer_from_data(data_loader: HSYDataLoader) -> MPCOptimizer:
    """Create optimizer with hardcoded pump specifications.
    
    These specs represent physical pump capacities (not old system strategy):
    - Small pumps (1.1, 2.1): ~0.5 m³/s, ~190-195 kW
    - Big pumps (1.2, 1.3, 1.4, 2.2, 2.3, 2.4): ~1.0 m³/s, ~375-410 kW
    """
    # Hardcoded pump specifications (identical hardware within each type)
    # Small pumps (1.1, 2.1): Same model/capacity
    # Big pumps (1.2, 1.3, 1.4, 2.2, 2.3, 2.4): Same model/capacity
    pump_specs_data = {
        '1.1': {'max_flow_m3_s': 0.5, 'max_power_kw': 200, 'power_vs_l1_slope_kw_per_m': 4.0},
        '1.2': {'max_flow_m3_s': 1.0, 'max_power_kw': 400, 'power_vs_l1_slope_kw_per_m': 8.0},
        '1.3': {'max_flow_m3_s': 1.0, 'max_power_kw': 400, 'power_vs_l1_slope_kw_per_m': 8.0},
        '1.4': {'max_flow_m3_s': 1.0, 'max_power_kw': 400, 'power_vs_l1_slope_kw_per_m': 8.0},
        '2.1': {'max_flow_m3_s': 0.5, 'max_power_kw': 200, 'power_vs_l1_slope_kw_per_m': 4.0},
        '2.2': {'max_flow_m3_s': 1.0, 'max_power_kw': 400, 'power_vs_l1_slope_kw_per_m': 8.0},
        '2.3': {'max_flow_m3_s': 1.0, 'max_power_kw': 400, 'power_vs_l1_slope_kw_per_m': 8.0},
        '2.4': {'max_flow_m3_s': 1.0, 'max_power_kw': 400, 'power_vs_l1_slope_kw_per_m': 8.0},
    }
    
    # Create pump specs from hardcoded values
    pumps = []
    for pump_id in sorted(pump_specs_data.keys()):
        spec_data = pump_specs_data[pump_id]
        pumps.append(
            PumpSpec(
                pump_id=pump_id,
                max_flow_m3_s=spec_data['max_flow_m3_s'],
                max_power_kw=spec_data['max_power_kw'],
                min_frequency_hz=47.8,  # Fixed hardware specification
                max_frequency_hz=50.0,  # Fixed hardware specification
                preferred_freq_min_hz=47.8,
                preferred_freq_max_hz=49.0,
                power_vs_l1_slope_kw_per_m=spec_data['power_vs_l1_slope_kw_per_m'],
                power_l1_reference_m=4.0,
            )
        )
    
    # Create constraints (adjust based on actual data if needed)
    constraints = SystemConstraints(
        l1_min_m=0.0,
        l1_max_m=8.0,
        tunnel_volume_m3=50000.0,  # Approximate - could be calculated from data
        min_pumps_on=1,
        min_pump_on_duration_minutes=120,
        min_pump_off_duration_minutes=120,
        flush_frequency_days=1,
        flush_target_level_m=0.5,
    )
    
    optimizer = MPCOptimizer(
        pumps=pumps,
        constraints=constraints,
        time_step_minutes=15,
        tactical_horizon_minutes=120,  # 2-hour tactical horizon
        strategic_horizon_minutes=1440,
    )
    
    return optimizer


def main():
    """Main test function."""
    # Load environment variables from .env file
    # Priority: agent's own .env, then project root, then current dir
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent.parent
    env_files = [
        script_dir / ".env",  # Agent's own .env (highest priority)
        project_root / ".env",  # Project root
        Path(".env"),  # Current directory
    ]
    
    env_loaded = False
    loaded_from = None
    for env_file in env_files:
        if env_file.exists():
            load_dotenv(env_file, override=False)  # Don't override existing env vars
            env_loaded = True
            loaded_from = env_file
            break
    
    if not env_loaded:
        # Try loading from current directory as fallback (load_dotenv searches automatically)
        result = load_dotenv(override=False)
        if result:
            env_loaded = True
            loaded_from = "auto-detected"
    
    # Log which .env file was loaded (after logging is set up)
    
    # Setup logging
    # Suppress httpx INFO level HTTP request logs (only show WARNING/ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    parser = argparse.ArgumentParser(
        description="Test optimizer with Hackathon_HSY_data.xlsx"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--data-file",
        type=str,
        default="Hackathon_HSY_data.xlsx",
        help="Path to Excel data file",
    )
    parser.add_argument(
        "--start-days",
        type=int,
        default=0,
        help="Days from start of data to begin simulation (default: 0)",
    )
    parser.add_argument(
        "--simulation-days",
        type=int,
        default=7,
        help="Number of days to simulate (default: 7)",
    )
    parser.add_argument(
        "--forecast-method",
        type=str,
        choices=["perfect", "persistence"],
        default="perfect",
        help="Forecast method: 'perfect' uses historical data, 'persistence' uses last value (default: perfect)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Optional output file path for saving results (JSON/CSV)",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use LLM for strategic planning (enabled by default if API keys are available). Use --explanations to also enable per-step explanations.",
    )
    parser.add_argument(
        "--explanations",
        action="store_true",
        help="Enable per-step LLM explanations (slow, requires --use-llm)",
    )
    parser.add_argument(
        "--no-strategic-plan",
        action="store_true",
        help="Disable LLM strategic planning (faster, but less optimal decisions)",
    )
    parser.add_argument(
        "--show-log-prefix",
        action="store_true",
        help="Show timestamp/module/level prefix on all log lines (default: only first line of tables/boxes)",
    )
    parser.add_argument(
        "--price-type",
        type=str,
        choices=["normal", "high"],
        default="normal",
        help="Electricity price column to use: 'normal' (everyday) or 'high' (peak variation) (default: normal)",
    )
    
    args = parser.parse_args()
    
    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    logger = logging.getLogger(__name__)
    
    # Log .env loading status
    if env_loaded:
        logger.info(f"✓ Loaded .env file from: {loaded_from}")
    else:
        logger.warning("⚠ No .env file found in any checked location")
    
    # Load data
    data_file_path = Path(__file__).parent / args.data_file
    if not data_file_path.exists():
        print(f"Error: Data file not found: {data_file_path}")
        return 1
    
    print(f"Loading data from: {data_file_path}")
    print(f"Using electricity price: {args.price_type}")
    data_loader = HSYDataLoader(str(data_file_path), price_type=args.price_type)
    
    # Get data range
    data_start, data_end = data_loader.get_data_range()
    print(f"Data range: {data_start} to {data_end}")
    
    # Calculate simulation window
    simulation_start = data_start + timedelta(days=args.start_days)
    simulation_end = simulation_start + timedelta(days=args.simulation_days)
    
    # Clamp to available data
    if simulation_end > data_end:
        simulation_end = data_end
        simulation_start = simulation_end - timedelta(days=args.simulation_days)
    
    print(f"Simulation window: {simulation_start} to {simulation_end}")
    print(f"Forecast method: {args.forecast_method}")
    print()
    
    # Create optimizer
    print("Initializing optimizer with hardcoded pump specifications...")
    optimizer = create_optimizer_from_data(data_loader)
    print(f"  Configured {len(optimizer.pumps)} pumps (2 small ~0.5 m³/s, 5 big ~1.0 m³/s, 1 offline)")
    print()
    
    # Initialize LLM explainer only if explicitly requested via --use-llm flag
    # Disabled by default for faster tests
    llm_explainer = None
    api_base = os.getenv("FEATHERLESS_API_BASE")
    api_key = os.getenv("FEATHERLESS_API_KEY")
    
    # Enable LLM only if explicitly requested (disabled by default for tests)
    should_use_llm = args.use_llm
    
    if should_use_llm:
        # Log what we found (without exposing the key)
        logger.info(f"Environment check: FEATHERLESS_API_BASE={'set' if api_base else 'not set'}")
        logger.info(f"Environment check: FEATHERLESS_API_KEY={'set' if api_key else 'not set'}")
        
        if api_base and api_key:
            llm_explainer = LLMExplainer(
                api_base=api_base,
                api_key=api_key,
                model=os.getenv("LLM_MODEL", "llama-3.1-8b-instruct"),
            )
            logger.info("✓ LLM explainer enabled")
            logger.info(f"  API Base: {api_base}")
            logger.info(f"  Model: {llm_explainer.model}")
            if args.explanations:
                print("✓ LLM explainer enabled (strategic planning + per-step explanations)")
            else:
                print("✓ LLM explainer enabled (strategic planning only, use --explanations for per-step)")
        else:
            missing = []
            if not api_base:
                missing.append("FEATHERLESS_API_BASE")
            if not api_key:
                missing.append("FEATHERLESS_API_KEY")
            if args.use_llm:
                logger.warning(f"⚠ LLM requested but {', '.join(missing)} not set")
                logger.info("Checked .env locations: current directory, project root, script directory")
                if env_loaded:
                    logger.info(f"Note: .env file was loaded from {loaded_from}, but it may not contain these variables")
                print(f"⚠ LLM requested but {', '.join(missing)} not set. Strategic planning and explanations will be skipped.")
    else:
        logger.info("LLM explainer: Not available (API keys not found). Use --use-llm to enable if keys are set elsewhere.")
    
    # Create simulator
    simulator = RollingMPCSimulator(
        data_loader=data_loader,
        optimizer=optimizer,
        reoptimize_interval_minutes=15,
        forecast_method=args.forecast_method,
        llm_explainer=llm_explainer,
        generate_explanations=args.explanations and (llm_explainer is not None),  # Only if explicitly requested
        generate_strategic_plan=(llm_explainer is not None) and not args.no_strategic_plan,  # Enabled by default if LLM available
        suppress_prefix=not args.show_log_prefix,  # Suppress prefix unless flag is set
    )
    
    # Run simulation
    print("Running rolling MPC simulation...")
    print("This may take several minutes depending on data size and optimizer settings.")
    print()
    
    try:
        simulation = simulator.simulate(
            start_time=simulation_start,
            end_time=simulation_end,
            horizon_minutes=120,  # 2-hour tactical horizon
        )
        
        print(f"Simulation completed: {len(simulation.results)} optimization steps")
        if args.use_llm and llm_explainer:
            explanations_generated = sum(1 for r in simulation.results if r.explanation is not None)
            print(f"  Generated {explanations_generated} LLM explanations (one per optimization step)")
        print()
        
        # Compare with baseline
        print("Calculating metrics and comparing with baseline...")
        comparison_metrics = simulator.compare_with_baseline(simulation)
        
        # Generate report (LLM explainer is already initialized above)
        # Disable LLM explanations in tests by default (only enable if explicitly requested)
        metrics_calculator = MetricsCalculator(
            simulator, 
            llm_explainer=llm_explainer,
            generate_explanations=args.explanations and (llm_explainer is not None),  # Only if explicitly requested
        )
        
        if args.use_llm and llm_explainer and args.explanations:
            logger.info("Generating additional LLM explanation for overall simulation summary...")
            print("Generating overall simulation summary explanation (this may take a moment)...")
        
        report = metrics_calculator.generate_comparison_report(
            simulation, comparison_metrics
        )
        
        # Print report
        print()
        print(report.summary)
        print()
        print("KEY FINDINGS:")
        for finding in report.key_findings:
            print(f"  {finding}")
        print()
        
        # Save results if requested
        if args.output:
            output_path = Path(args.output)
            if output_path.suffix.lower() == '.json':
                import json
                output_data = {
                    'simulation': {
                        'start_time': simulation.start_time.isoformat(),
                        'end_time': simulation.end_time.isoformat(),
                        'num_steps': len(simulation.results),
                    },
                    'metrics': report.metrics,
                    'key_findings': report.key_findings,
                }
                with open(output_path, 'w') as f:
                    json.dump(output_data, f, indent=2)
                print(f"Results saved to: {output_path}")
            else:
                print(f"Warning: Unsupported output format: {output_path.suffix}")
        
        return 0
        
    except Exception as e:
        print(f"Error during simulation: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())


#!/usr/bin/env python3
"""Quick test script for demo simulator WebSocket."""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add repo root to path for imports
_script_dir = Path(__file__).resolve().parent
_repo_root = _script_dir.parent.parent  # Go up from optimizer_agent -> agents -> Junction-2025
_repo_root_str = str(_repo_root)
if _repo_root_str not in sys.path:
    sys.path.insert(0, _repo_root_str)

try:
    import websockets
except ImportError:
    print("Error: websockets package not installed.")
    print("Install it with: pip install websockets")
    sys.exit(1)


async def test_demo_websocket(
    base_url: str = "ws://localhost:8000",
    speed_multiplier: float = 10.0,
    start_time: str = None,
    end_time: str = None,
):
    """Test the demo simulator WebSocket endpoint.
    
    Args:
        base_url: WebSocket base URL (default: ws://localhost:8000)
        speed_multiplier: Simulation speed (default: 10.0 = 10x faster)
        start_time: ISO format start time (optional)
        end_time: ISO format end time (optional)
    """
    # Build WebSocket URL with query parameters
    url = f"{base_url}/system/demo/simulate"
    params = [f"speed_multiplier={speed_multiplier}"]
    
    if start_time:
        params.append(f"start_time={start_time}")
    if end_time:
        params.append(f"end_time={end_time}")
    
    if params:
        url += "?" + "&".join(params)
    
    print("=" * 70)
    print("Demo Simulator WebSocket Test")
    print("=" * 70)
    print(f"Connecting to: {url}")
    print(f"Speed multiplier: {speed_multiplier}x")
    print()
    
    try:
        async with websockets.connect(url) as websocket:
            print("✓ Connected to WebSocket")
            print("Waiting for messages...")
            print("-" * 70)
            
            step_count = 0
            start_received = False
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "unknown")
                    
                    if msg_type == "simulation_start":
                        start_received = True
                        print(f"\n🚀 SIMULATION START")
                        print(f"   Start time: {data.get('start_time')}")
                        print(f"   End time: {data.get('end_time')}")
                        print(f"   Total steps: {data.get('total_steps')}")
                        print(f"   Interval: {data.get('reoptimize_interval_minutes')} minutes")
                        print("-" * 70)
                    
                    elif msg_type == "simulation_step":
                        step_count += 1
                        step = data.get("step", 0)
                        total = data.get("total_steps", 0)
                        timestamp = data.get("timestamp", "")
                        
                        state = data.get("state", {})
                        optimization = data.get("optimization", {})
                        
                        print(f"\n📊 Step {step + 1}/{total} - {timestamp}")
                        print(f"   L1 Level: {state.get('l1_m', 0):.2f} m")
                        print(f"   Inflow: {state.get('inflow_m3_s', 0):.3f} m³/s")
                        print(f"   Outflow: {state.get('outflow_m3_s', 0):.3f} m³/s")
                        print(f"   Price: {state.get('price_c_per_kwh', 0):.2f} c/kWh")
                        
                        if optimization.get("success"):
                            print(f"   ✓ Optimization: {optimization.get('mode', 'unknown')}")
                            print(f"   Energy: {optimization.get('total_energy_kwh', 0):.2f} kWh")
                            print(f"   Cost: {optimization.get('total_cost_eur', 0):.2f} EUR")
                            
                            schedules = optimization.get("schedules", [])
                            active_pumps = [s["pump_id"] for s in schedules if s.get("is_on")]
                            if active_pumps:
                                print(f"   Active pumps: {', '.join(active_pumps)}")
                        else:
                            print(f"   ✗ Optimization failed")
                        
                        # Show LLM-generated content
                        has_explanation = data.get("explanation") is not None
                        has_strategy = data.get("strategy") is not None
                        has_plan = data.get("strategic_plan") is not None
                        
                        if has_explanation or has_strategy or has_plan:
                            if data.get("explanation"):
                                explanation = data.get("explanation")
                                print(f"   💡 Explanation: {explanation[:100]}..." if len(explanation) > 100 else f"   💡 Explanation: {explanation}")
                            if data.get("strategy"):
                                print(f"   📊 Strategy: {data.get('strategy')}")
                            if data.get("strategic_plan"):
                                plan = data.get("strategic_plan")
                                print(f"   🎯 Strategic Plan: {plan.get('plan_type', 'N/A')} ({plan.get('forecast_confidence', 'N/A')} confidence)")
                        elif step == 0:  # Only show debug on first step
                            print(f"   ⚠ Debug: No LLM content (explanation={has_explanation}, strategy={has_strategy}, plan={has_plan})")
                    
                    elif msg_type == "simulation_summary":
                        print("\n" + "=" * 70)
                        print("📈 SIMULATION SUMMARY")
                        print("=" * 70)
                        
                        comparison = data.get("comparison", {})
                        if comparison:
                            energy_savings = comparison.get("energy_savings_percent", 0)
                            cost_savings = comparison.get("cost_savings_percent", 0)
                            
                            print(f"Energy reduction: {energy_savings:.2f}%")
                            print(f"Cost reduction: {cost_savings:.2f}%")
                            print(f"Total steps: {data.get('total_steps', 0)}")
                        
                        print("=" * 70)
                        break
                    
                    elif msg_type == "error":
                        print(f"\n❌ ERROR: {data.get('message', 'Unknown error')}")
                        break
                    
                    else:
                        print(f"\n⚠ Unknown message type: {msg_type}")
                        print(json.dumps(data, indent=2))
                
                except json.JSONDecodeError as e:
                    print(f"\n❌ Failed to parse JSON: {e}")
                    print(f"Raw message: {message[:200]}")
                except Exception as e:
                    print(f"\n❌ Error processing message: {e}")
                    print(f"Message type: {msg_type if 'msg_type' in locals() else 'unknown'}")
            
            if not start_received:
                print("\n⚠ Warning: Did not receive simulation_start message")
            
            print(f"\n✓ Received {step_count} simulation steps")
            print("Connection closed")
    
    except websockets.exceptions.ConnectionClosed:
        print("\n⚠ WebSocket connection closed by server")
    except ConnectionRefusedError:
        print(f"\n❌ Connection refused. Is the backend running on {base_url}?")
        print("Start the backend with: cd backend && uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test demo simulator WebSocket")
    parser.add_argument(
        "--url",
        type=str,
        default="ws://localhost:8000",
        help="WebSocket base URL (default: ws://localhost:8000)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=10.0,
        help="Speed multiplier (default: 10.0 = 10x faster)",
    )
    parser.add_argument(
        "--start-time",
        type=str,
        help="Start time in ISO format (e.g., 2024-11-15T00:00:00)",
    )
    parser.add_argument(
        "--end-time",
        type=str,
        help="End time in ISO format (e.g., 2024-11-16T00:00:00)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to simulate (default: 1, used if start/end not specified)",
    )
    
    args = parser.parse_args()
    
    # If start_time not provided, calculate from data file
    if not args.start_time:
        # Try to get data range from data loader
        try:
            # Ensure repo_root is in sys.path (should already be added at module level)
            script_dir = Path(__file__).resolve().parent
            repo_root = script_dir.parent.parent  # Go up from optimizer_agent -> agents -> Junction-2025
            repo_root_str = str(repo_root)
            if repo_root_str not in sys.path:
                sys.path.insert(0, repo_root_str)
            from agents.optimizer_agent.test_data_loader import HSYDataLoader
            
            # Try multiple locations for data file
            data_file = None
            possible_paths = [
                script_dir / "Hackathon_HSY_data.xlsx",
                repo_root / "sample" / "Valmet" / "Hackathon_HSY_data.xlsx",
                repo_root / "agents" / "optimizer_agent" / "Hackathon_HSY_data.xlsx",
            ]
            
            for path in possible_paths:
                if path.exists():
                    data_file = path
                    break
            
            if data_file and data_file.exists():
                loader = HSYDataLoader(str(data_file), use_price_agent=True, use_weather_agent=True)
                data_start, data_end = loader.get_data_range()
                args.start_time = data_start.isoformat()
                if not args.end_time:
                    args.end_time = (data_start + timedelta(days=args.days)).isoformat()
            else:
                print("⚠ Data file not found, using default times")
                args.start_time = "2024-11-15T00:00:00"
                if not args.end_time:
                    args.end_time = (datetime.fromisoformat(args.start_time) + timedelta(days=args.days)).isoformat()
        except Exception as e:
            print(f"⚠ Could not determine times: {e}")
            import traceback
            traceback.print_exc()
            args.start_time = "2024-11-15T00:00:00"
            if not args.end_time:
                args.end_time = (datetime.fromisoformat(args.start_time) + timedelta(days=args.days)).isoformat()
    
    asyncio.run(test_demo_websocket(
        base_url=args.url,
        speed_multiplier=args.speed,
        start_time=args.start_time,
        end_time=args.end_time,
    ))


if __name__ == "__main__":
    main()


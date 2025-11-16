#!/usr/bin/env python3
"""Simple WebSocket test script to see all messages."""
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("Installing websockets library...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets


async def test_websocket():
    uri = "ws://localhost:8000/system/demo/simulate?speed_multiplier=10.0"
    
    print("=" * 80)
    print("WebSocket Test - Showing ALL Messages")
    print("=" * 80)
    print(f"Connecting to: {uri}")
    print("=" * 80)
    print()
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected!")
            print()
            
            message_count = 0
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    message_type = data.get("type", "unknown")
                    message_count += 1
                    
                    # Skip keepalive silently
                    if message_type == "keepalive":
                        continue
                    
                    print(f"\n{'='*80}")
                    print(f"Message #{message_count} - Type: {message_type}")
                    print(f"{'='*80}")
                    
                    if message_type == "simulation_start":
                        print(f"  Start: {data.get('start_time')}")
                        print(f"  End: {data.get('end_time')}")
                        print(f"  Total Steps: {data.get('total_steps')}")
                    
                    elif message_type == "simulation_step":
                        step = data.get('step', 0) + 1
                        total = data.get('total_steps', 0)
                        print(f"  Step: {step}/{total}")
                        print(f"  Timestamp: {data.get('timestamp')}")
                        if data.get('state'):
                            state = data['state']
                            print(f"  L1: {state.get('l1_m', 'N/A')}m")
                            print(f"  Inflow: {state.get('inflow_m3_s', 'N/A')} m³/s")
                    
                    elif message_type == "simulation_summary":
                        print(f"  Simulation Complete!")
                        print(json.dumps(data, indent=2, default=str))
                    
                    elif message_type == "error":
                        print(f"  ERROR: {data.get('message')}")
                        print(json.dumps(data, indent=2, default=str))
                    
                    else:
                        print(json.dumps(data, indent=2, default=str))
                    
                    print()
                
                except json.JSONDecodeError as e:
                    print(f"\n❌ Failed to parse message #{message_count}: {e}")
                    print(f"Raw message: {message[:200]}")
                    print()
    
    except ConnectionRefusedError:
        print("❌ Connection refused. Is the backend running?")
        print("   Start it with: cd backend && python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(test_websocket())
    except KeyboardInterrupt:
        print("\n\nStopped by user")


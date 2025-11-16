#!/usr/bin/env python3
"""Test WebSocket and display JSON messages."""
import asyncio
import json
import sys
from datetime import datetime, timedelta

try:
    import websockets
except ImportError:
    print("Installing websockets library...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets


async def test_websocket_json():
    """Connect to WebSocket and display all JSON messages."""
    uri = "ws://localhost:8000/system/demo/simulate?speed_multiplier=10.0"
    
    # Use a short time range for quick testing
    end_time = (datetime.now() + timedelta(minutes=30)).isoformat()
    
    print("=" * 80)
    print("WebSocket JSON Message Viewer")
    print("=" * 80)
    print(f"Connecting to: {uri}")
    print(f"Will simulate until: {end_time}")
    print("=" * 80)
    print()
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✓ WebSocket connected!")
            print()
            
            message_count = 0
            max_messages = 5  # Show first 5 messages
            
            try:
                async with asyncio.timeout(60):  # 60 second timeout
                    async for message in websocket:
                        data = json.loads(message)
                        message_type = data.get("type", "unknown")
                        
                        # Skip keepalive messages (just count them silently)
                        if message_type == "keepalive":
                            continue
                        
                        message_count += 1
                        print(f"\n{'='*80}")
                        print(f"Message #{message_count} - Type: {message_type}")
                        print(f"{'='*80}")
                        print(json.dumps(data, indent=2, default=str))
                        print()
                        
                        if message_type == "error":
                            print("✗ Error received, stopping...")
                            break
                        
                        if message_type == "simulation_summary":
                            print("✓ Simulation completed!")
                            break
                        
                        if message_count >= max_messages:
                            print(f"\n✓ Received {max_messages} messages. Stopping (restart backend to see more)...")
                            break
                
            except asyncio.TimeoutError:
                if message_count > 0:
                    print(f"\n✓ Received {message_count} messages (timeout after 60s)")
                else:
                    print("\n⚠ No messages received within 60 seconds")
            
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"✗ WebSocket connection failed with status {e.status_code}")
        if e.status_code == 404:
            print("  Endpoint not found. Make sure the backend is running.")
        return False
    except ConnectionRefusedError:
        print("⚠ Backend not running. Start backend first:")
        print("  cd backend")
        print("  python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
        return False
    except Exception as e:
        print(f"✗ WebSocket error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    print("\nStarting WebSocket JSON viewer...")
    print("Press Ctrl+C to stop\n")
    
    try:
        success = asyncio.run(test_websocket_json())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nStopped by user")
        sys.exit(0)


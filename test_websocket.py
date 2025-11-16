#!/usr/bin/env python3
"""Test script to verify WebSocket connection."""
import asyncio
import json
import sys
import logging
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_websocket():
    """Test WebSocket connection to demo simulator."""
    try:
        import websockets
    except ImportError:
        logger.error("✗ websockets library not installed. Install with: pip install websockets")
        return False
    
    uri = "ws://localhost:8000/system/demo/simulate"
    # Test with a short simulation
    end_time = (datetime.now() + timedelta(hours=1)).isoformat()
    
    logger.info(f"Testing WebSocket connection to: {uri}")
    logger.info(f"Will simulate until: {end_time}")
    
    try:
        async with websockets.connect(uri) as websocket:
            logger.info("✓ WebSocket connection established!")
            
            # Wait for messages
            message_count = 0
            max_messages = 10  # Limit to avoid running forever
            
            try:
                async with asyncio.timeout(30):  # 30 second timeout
                    async for message in websocket:
                        data = json.loads(message)
                        message_type = data.get("type", "unknown")
                        
                        if message_type == "simulation_start":
                            logger.info("✓ Received simulation_start message")
                            logger.info(f"  Parameters: {json.dumps(data.get('parameters', {}), indent=2)}")
                            message_count += 1
                        
                        elif message_type == "simulation_step":
                            message_count += 1
                            if message_count == 1:
                                logger.info("✓ Received simulation_step message")
                                logger.info(f"  Time step: {data.get('time_step', 'N/A')}")
                                logger.info(f"  L1: {data.get('state', {}).get('l1_volume_m3', 'N/A')} m³")
                                logger.info(f"  L2: {data.get('state', {}).get('l2_m', 'N/A')} m")
                                logger.info(f"  Pumps ON: {data.get('metrics', {}).get('pumps_on', 'N/A')}")
                            
                            if message_count >= max_messages:
                                logger.info(f"✓ Received {message_count} messages, test successful!")
                                break
                        
                        elif message_type == "simulation_summary":
                            logger.info("✓ Received simulation_summary message")
                            logger.info(f"  Total steps: {data.get('total_steps', 'N/A')}")
                            logger.info(f"  Total cost: {data.get('metrics', {}).get('total_cost_eur', 'N/A')} EUR")
                            break
                        
                        elif message_type == "error":
                            logger.error(f"✗ Received error: {data.get('message', 'Unknown error')}")
                            return False
                        
                        else:
                            logger.debug(f"Received message type: {message_type}")
                
            except asyncio.TimeoutError:
                if message_count > 0:
                    logger.info(f"✓ WebSocket test successful! Received {message_count} messages (timeout after 30s)")
                    return True
                else:
                    logger.warning("⚠ WebSocket connected but no messages received within 30s")
                    return False
            
            logger.info("✓ WebSocket test completed successfully!")
            return True
            
    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(f"✗ WebSocket connection failed with status {e.status_code}")
        if e.status_code == 404:
            logger.error("  Endpoint not found. Make sure the backend is running and the route is registered.")
        return False
    except ConnectionRefusedError:
        logger.warning("⚠ Backend not running (this is OK if you're only testing digital twin)")
        return None
    except Exception as e:
        logger.error(f"✗ WebSocket connection failed: {e}")
        return False


async def test_websocket_endpoint_available():
    """Test if WebSocket endpoint is available via HTTP check."""
    try:
        import httpx
        
        # Check if the endpoint exists (WebSocket upgrade will fail, but we can check the response)
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                # Try to connect to the WebSocket endpoint with HTTP
                response = await client.get("http://localhost:8000/system/demo/simulate")
                logger.info(f"WebSocket endpoint status: {response.status_code}")
                if response.status_code == 426:  # Upgrade Required (WebSocket)
                    logger.info("✓ WebSocket endpoint is available (requires WebSocket upgrade)")
                    return True
                elif response.status_code == 200:
                    logger.warning("⚠ Endpoint returned 200, might not be a WebSocket endpoint")
                    return False
                else:
                    logger.warning(f"⚠ Endpoint returned {response.status_code}")
                    return False
            except httpx.ConnectError:
                logger.warning("⚠ Backend not running")
                return None
    except ImportError:
        logger.error("✗ httpx library not installed")
        return False
    except Exception as e:
        logger.error(f"✗ Error checking endpoint: {e}")
        return False


async def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("WebSocket Connection Test")
    logger.info("=" * 60)
    
    # First check if endpoint is available
    logger.info("\n[1/2] Checking WebSocket endpoint availability...")
    endpoint_available = await test_websocket_endpoint_available()
    
    # Then test actual WebSocket connection
    logger.info("\n[2/2] Testing WebSocket connection...")
    websocket_works = await test_websocket()
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    
    if endpoint_available is True:
        logger.info("ENDPOINT  ✓ PASS")
    elif endpoint_available is False:
        logger.info("ENDPOINT  ✗ FAIL")
    else:
        logger.info("ENDPOINT  ⚠ SKIP")
    
    if websocket_works is True:
        logger.info("WEBSOCKET ✓ PASS")
        logger.info("\n✓ WebSocket is working!")
        return 0
    elif websocket_works is False:
        logger.info("WEBSOCKET ✗ FAIL")
        logger.error("\n✗ WebSocket connection failed. Check logs above.")
        return 1
    else:
        logger.info("WEBSOCKET ⚠ SKIP")
        logger.info("\n⚠ Backend not running. Start backend to test WebSocket.")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


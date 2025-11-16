"""REST API endpoints for demo simulator."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Dict, List

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

# Load .env file explicitly (since os.getenv() doesn't auto-load it)
try:
    from dotenv import load_dotenv
    _repo_root = Path(__file__).resolve().parents[4]  # backend/app/api/routes -> Junction-2025
    env_path = _repo_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger_env = logging.getLogger(__name__)
        logger_env.debug(f"Loaded .env file from: {env_path}")
    else:
        logger_env = logging.getLogger(__name__)
        logger_env.warning(f".env file not found at: {env_path}")
except ImportError:
    # python-dotenv not available, os.getenv() will only use actual environment variables
    logger_env = logging.getLogger(__name__)
    logger_env.debug("python-dotenv not available, using environment variables only")

# Add agents to path for importing DemoSimulator
_repo_root = Path(__file__).resolve().parents[4]  # backend/app/api/routes -> Junction-2025
_repo_root_str = str(_repo_root)
if _repo_root_str not in sys.path:
    sys.path.insert(0, _repo_root_str)

try:
    from agents.optimizer_agent.demo_simulator import DemoSimulator
    from agents.optimizer_agent.test_data_loader import HSYDataLoader
    from agents.optimizer_agent.optimizer import MPCOptimizer
    from agents.optimizer_agent.test_optimizer_with_data import create_optimizer_from_data
    from agents.optimizer_agent.explainability import LLMExplainer
    DEMO_SIMULATOR_AVAILABLE = True
except ImportError as e:
    DEMO_SIMULATOR_AVAILABLE = False
    logging.getLogger(__name__).warning(f"Demo simulator not available: {e}")

router = APIRouter(prefix="/system/demo", tags=["demo"])
logger = logging.getLogger(__name__)

# In-memory simulation state storage
_simulation_state: Dict[str, Any] = {}
_simulation_task: Optional[asyncio.Task] = None
_simulation_lock = asyncio.Lock()  # Lock for thread-safe access


class SimulationStartRequest(BaseModel):
    speed_multiplier: float = 1.0
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    data_file: str = "Hackathon_HSY_data.xlsx"


class SimulationStatusResponse(BaseModel):
    status: str  # "idle", "running", "completed", "error"
    current_step: Optional[int] = None
    total_steps: Optional[int] = None
    last_message: Optional[Dict[str, Any]] = None
    messages: Optional[list[Dict[str, Any]]] = None  # All messages
    error: Optional[str] = None


def clean_nan_for_json(obj: Any) -> Any:
    """Recursively clean NaN, Infinity, and -Infinity values from a dict/list for JSON serialization.
    
    Replaces NaN with None, Infinity with a large number (1e10), and -Infinity with -1e10.
    """
    if isinstance(obj, dict):
        return {key: clean_nan_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_for_json(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj):
            return None
        elif math.isinf(obj):
            return 1e10 if obj > 0 else -1e10
        else:
            return obj
    else:
        return obj


async def _run_simulation_background(
    speed_multiplier: float,
    start_time: Optional[str],
    end_time: Optional[str],
    data_file: str,
):
    """Run simulation in background and store state."""
    global _simulation_state, _simulation_task
    
    try:
        _simulation_state = {
            "status": "running",
            "current_step": 0,
            "total_steps": 0,
            "last_message": None,
            "error": None,
            "messages": [],
        }
        
        # Parse start/end times
        start_dt = None
        end_dt = None
        
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                _simulation_state["status"] = "error"
                _simulation_state["error"] = f"Invalid start_time format: {start_time}"
                return
        
        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            except ValueError:
                _simulation_state["status"] = "error"
                _simulation_state["error"] = f"Invalid end_time format: {end_time}"
                return
        
        # Find data file
        data_file_path = None
        possible_paths = [
            _repo_root / "agents" / "optimizer_agent" / data_file,
            _repo_root / "sample" / "Valmet" / data_file,
            _repo_root / "sample" / data_file,
        ]
        
        for path in possible_paths:
            if path.exists():
                data_file_path = path
                break
        
        if not data_file_path:
            _simulation_state["status"] = "error"
            _simulation_state["error"] = f"Data file not found: {data_file}"
            return
        
        # Initialize data loader
        data_loader = HSYDataLoader(
            excel_file=str(data_file_path),
            price_type='normal',
        )
        
        # Get data range if times not provided
        if not start_dt or not end_dt:
            data_start, data_end = data_loader.get_data_range()
            start_dt = start_dt or data_start
            end_dt = end_dt or (start_dt.replace(hour=23, minute=59, second=59) if not end_dt else end_dt)
        
        # Validate time range
        if end_dt <= start_dt:
            _simulation_state["status"] = "error"
            _simulation_state["error"] = f"end_time must be after start_time. Got: {start_dt} to {end_dt}"
            return
        
        # Create optimizer
        optimizer = create_optimizer_from_data(data_loader)
        
        # Initialize LLM explainer if credentials are available
        from app.config import get_settings
        settings = get_settings()
        
        llm_explainer = None
        featherless_api_base = settings.featherless_api_base or os.getenv("FEATHERLESS_API_BASE")
        featherless_api_key = settings.featherless_api_key or os.getenv("FEATHERLESS_API_KEY")
        llm_model = settings.llm_model or os.getenv("LLM_MODEL", "llama-3.1-8b-instruct")
        
        # Log LLM configuration status
        logger.info("=" * 60)
        logger.info("LLM Configuration Check:")
        logger.info(f"  FEATHERLESS_API_BASE: {'✅ SET' if featherless_api_base else '❌ NOT SET'}")
        if featherless_api_base:
            logger.info(f"    Value: {featherless_api_base[:50]}..." if len(featherless_api_base) > 50 else f"    Value: {featherless_api_base}")
        logger.info(f"  FEATHERLESS_API_KEY: {'✅ SET' if featherless_api_key else '❌ NOT SET'}")
        logger.info(f"  LLM_MODEL: {llm_model}")
        logger.info("=" * 60)
        
        if featherless_api_base and featherless_api_key:
            llm_explainer = LLMExplainer(
                api_base=featherless_api_base,
                api_key=featherless_api_key,
                model=llm_model,
            )
            logger.info(f"✅ LLM Explainer initialized successfully")
            logger.info(f"   Model: {llm_model}")
            logger.info(f"   API Base: {featherless_api_base[:50]}...")
            logger.info(f"   Features: explanations={'enabled' if llm_explainer else 'disabled'}, strategic_plan={'enabled' if llm_explainer else 'disabled'}")
        else:
            logger.warning("❌ LLM Explainer NOT initialized - missing credentials")
            logger.warning("   Simulation will run without LLM explanations and strategic plans")
            if not featherless_api_base:
                logger.warning("   Missing: FEATHERLESS_API_BASE")
            if not featherless_api_key:
                logger.warning("   Missing: FEATHERLESS_API_KEY")
            logger.warning(f"   Set these in .env file at: {_repo_root / '.env'}")
        
        # Create callback to store messages (async version for thread safety)
        async def store_message_async(data: dict) -> bool:
            """Store message in simulation state. Returns True to continue simulation."""
            async with _simulation_lock:
                try:
                    msg_type = data.get("type", "unknown")
                    cleaned_data = clean_nan_for_json(data)
                    _simulation_state["last_message"] = cleaned_data
                    _simulation_state["messages"].append(cleaned_data)
                    
                    total_msgs = len(_simulation_state["messages"])
                    logger.info(f"📝 Stored message: type={msg_type}, step={data.get('step', 'N/A')}, total_messages={total_msgs}")
                    
                    if msg_type == "simulation_start":
                        _simulation_state["total_steps"] = data.get("total_steps", 0)
                        logger.info(f"✅ Simulation started: {_simulation_state['total_steps']} steps")
                    elif msg_type == "simulation_step":
                        step = data.get("step", 0)
                        _simulation_state["current_step"] = step + 1
                        logger.info(f"📊 Step {step + 1}/{_simulation_state.get('total_steps', '?')} stored (total messages: {total_msgs})")
                    elif msg_type == "simulation_summary":
                        _simulation_state["status"] = "completed"
                        logger.info("✅ Simulation completed")
                    elif msg_type == "error":
                        _simulation_state["status"] = "error"
                        _simulation_state["error"] = data.get("message", "Unknown error")
                        logger.error(f"❌ Simulation error: {_simulation_state['error']}")
                    
                    return True  # Continue simulation
                except Exception as e:
                    logger.error(f"Error storing message: {e}", exc_info=True)
                    return True  # Continue anyway
        
        # Create simulator with async callback
        simulator = DemoSimulator(
            data_loader=data_loader,
            optimizer=optimizer,
            reoptimize_interval_minutes=15,
            update_callback=store_message_async,  # Use async callback for thread safety
            llm_explainer=llm_explainer,
            generate_explanations=llm_explainer is not None,
            generate_strategic_plan=llm_explainer is not None,
        )
        
        # Run simulation
        logger.info(f"Starting background simulation: {start_dt} to {end_dt}, speed={speed_multiplier}x")
        await simulator.run_simulation(
            start_time=start_dt,
            end_time=end_dt,
            speed_multiplier=speed_multiplier,
        )
        
        if _simulation_state["status"] == "running":
            _simulation_state["status"] = "completed"
        
    except Exception as e:
        logger.error(f"Simulation error: {e}", exc_info=True)
        _simulation_state["status"] = "error"
        _simulation_state["error"] = str(e)
    finally:
        _simulation_task = None


@router.post("/simulate/start", response_model=Dict[str, str])
async def start_simulation(request: SimulationStartRequest = Body(...)):
    """Start simulation in background."""
    global _simulation_state, _simulation_task
    
    if not DEMO_SIMULATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Demo simulator not available")
    
    if _simulation_task is not None and not _simulation_task.done():
        raise HTTPException(status_code=409, detail="Simulation already running")
    
    # Reset state
    _simulation_state = {
        "status": "running",
        "current_step": 0,
        "total_steps": 0,
        "last_message": None,
        "error": None,
        "messages": [],
    }
    
    # Start background task
    _simulation_task = asyncio.create_task(
        _run_simulation_background(
            speed_multiplier=request.speed_multiplier,
            start_time=request.start_time,
            end_time=request.end_time,
            data_file=request.data_file,
        )
    )
    
    return {"status": "started", "message": "Simulation started in background"}


@router.get("/simulate/status", response_model=SimulationStatusResponse)
async def get_simulation_status():
    """Get current simulation status."""
    global _simulation_state
    
    async with _simulation_lock:
        if not _simulation_state:
            return SimulationStatusResponse(
                status="idle",
                current_step=None,
                total_steps=None,
                last_message=None,
                messages=None,
                error=None,
            )
        
        # Create a copy of messages to avoid race conditions
        messages_copy = list(_simulation_state.get("messages", []))
        
        return SimulationStatusResponse(
            status=_simulation_state.get("status", "idle"),
            current_step=_simulation_state.get("current_step"),
            total_steps=_simulation_state.get("total_steps"),
            last_message=_simulation_state.get("last_message"),
            messages=messages_copy,
            error=_simulation_state.get("error"),
        )


@router.post("/simulate/stop", response_model=Dict[str, str])
async def stop_simulation():
    """Stop running simulation."""
    global _simulation_state, _simulation_task
    
    if _simulation_task is None or _simulation_task.done():
        return {"status": "stopped", "message": "No simulation running"}
    
    # Cancel task
    _simulation_task.cancel()
    try:
        await _simulation_task
    except asyncio.CancelledError:
        pass
    
    _simulation_task = None
    _simulation_state["status"] = "idle"
    
    return {"status": "stopped", "message": "Simulation stopped"}




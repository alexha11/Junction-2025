from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field

from agents.common import BaseMCPAgent


class SystemStatePayload(BaseModel):
    timestamp: datetime
    tunnel_level_m: float
    tunnel_level_l2_m: float
    inflow_m3_s: float
    outflow_m3_s: float
    pumps: List[dict]


class SystemStateRequest(BaseModel):
    pass


class TunnelVolumeRequest(BaseModel):
    level: float = Field(gt=0)


class PumpEfficiencyRequest(BaseModel):
    pump_id: str
    flow: float
    head: float


class SystemStatusAgent(BaseMCPAgent):
    """
    System Status Agent - DEPRECATED
    
    This agent is deprecated and will be removed in a future version.
    Please use the digital twin integration via the backend API instead:
    - GET /system/state - Get current system state from digital twin
    - GET /system/digital-twin/state - Get raw OPC UA values
    
    The digital twin provides real-time data from the OPC UA server,
    replacing the synthetic data previously returned by this agent.
    """
    
    def __init__(self) -> None:
        super().__init__(name="system-status-agent")
        import warnings
        warnings.warn(
            "SystemStatusAgent is deprecated. Use digital twin integration via backend API instead.",
            DeprecationWarning,
            stacklevel=2
        )

    def configure(self) -> None:
        self.register_tool("get_current_system_state", self.get_current_state)
        self.register_tool("get_tunnel_volume", self.get_tunnel_volume)
        self.register_tool("get_pump_efficiency", self.get_pump_efficiency)

    def get_current_state(self, _: SystemStateRequest) -> SystemStatePayload:
        """
        Get current system state - DEPRECATED.
        
        This method returns synthetic placeholder data.
        For production use, call the backend API endpoint /system/state
        which uses the digital twin for real-time data.
        """
        now = datetime.utcnow()
        return SystemStatePayload(
            timestamp=now,
            tunnel_level_m=3.4,
            tunnel_level_l2_m=3.1,
            inflow_m3_s=2.2,
            outflow_m3_s=2.0,
            pumps=[{"pump_id": f"P{i+1}", "frequency_hz": 48.0, "state": "on"} for i in range(8)],
        )

    def get_tunnel_volume(self, request: TunnelVolumeRequest) -> float:
        return 5000 * request.level  # placeholder linearization

    def get_pump_efficiency(self, request: PumpEfficiencyRequest) -> float:
        if request.head == 0:
            return 0.0
        return min(1.0, (request.flow / request.head) * 0.1)


def serve() -> None:
    SystemStatusAgent().serve()


if __name__ == "__main__":
    serve()

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

try:
    from .models import ScheduleDecision
except ImportError:  # pragma: no cover
    from models import ScheduleDecision


PUMP_IDS = ["1.1", "1.2", "1.3", "1.4", "2.1", "2.2", "2.3", "2.4"]


def build_command_payload(decision: ScheduleDecision) -> dict:
    on_set = set(decision.pumps_on)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "effective_timestamp": decision.timestamp.isoformat(),
        "commands": [
            {
                "pump_id": pid,
                "on": pid in on_set,
                "frequency_hz": 50.0 if pid in on_set else 0.0,
            }
            for pid in PUMP_IDS
        ],
        "meta": {
            "outflow_m3_s": decision.outflow_m3_s,
            "inflow_m3_s": decision.inflow_m3_s,
            "flush_active": decision.flush_active,
        },
    }


@dataclass
class OpcUaCommandPublisher:
    endpoint: str
    node_map_path: Path

    def publish_payload(self, payload: dict) -> None:
        from opcua import Client  # type: ignore

        with self.node_map_path.open("r", encoding="utf-8") as f:
            node_map = json.load(f)

        on_map = {c["pump_id"]: bool(c["on"]) for c in payload["commands"]}
        hz_map = {c["pump_id"]: float(c["frequency_hz"]) for c in payload["commands"]}

        client = Client(self.endpoint)
        client.connect()
        try:
            objects = client.get_objects_node()
            station = None
            for child in objects.get_children():
                if child.get_browse_name().Name == "PumpStation":
                    station = child
                    break
            if station is None:
                raise RuntimeError("PumpStation node not found for OPC UA command publishing")

            children = {n.get_browse_name().Name: n for n in station.get_children()}
            for pid in PUMP_IDS:
                cfg = node_map.get(pid)
                if not cfg:
                    continue
                on_name = cfg.get("on")
                freq_name = cfg.get("frequency")
                if on_name in children:
                    children[on_name].set_value(on_map.get(pid, False))
                if freq_name in children:
                    children[freq_name].set_value(hz_map.get(pid, 0.0))
        finally:
            client.disconnect()

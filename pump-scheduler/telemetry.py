from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Iterable, Iterator, List, Protocol, Tuple

try:
    from .data_loader import LevelVolumeCurve, build_level_volume_curve, load_hsy_csv
    from .models import TimeStepData
except ImportError:  # pragma: no cover - allows running as script
    from data_loader import LevelVolumeCurve, build_level_volume_curve, load_hsy_csv
    from models import TimeStepData


DEFAULT_OPC_NODE_MAP: Dict[str, str] = {
    "timestamp": "SimulationTime",
    "level": "WaterLevelInTunnel.L2.m",
    "volume": "WaterVolumeInTunnel.L1.m3",
    "inflow": "InflowToTunnel.F1.m3per15min",
    "price_normal": "ElectricityPrice.2.Normal.ckwh",
    "price_high": "ElectricityPrice.1.High.ckwh",
}


class TelemetrySource(Protocol):
    def load_series(self) -> Tuple[List[TimeStepData], LevelVolumeCurve]:
        raise NotImplementedError


@dataclass
class OpcUaTelemetrySource:
    endpoint: str = "opc.tcp://127.0.0.1:4840/wastewater/"
    steps: int = 96
    poll_seconds: float = 0.2
    connect_retries: int = 30
    retry_delay_seconds: float = 2.0
    price_column: str = "normal"
    node_map_path: Path | None = None

    def _connect_client(self):
        try:
            from opcua import Client  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "opcua package not installed. Install with: pip install opcua"
            ) from exc

        client = Client(self.endpoint)
        connected = False
        last_error = None
        for _ in range(self.connect_retries):
            try:
                client.connect()
                connected = True
                break
            except Exception as exc:  # pragma: no cover
                last_error = exc
                time.sleep(self.retry_delay_seconds)
        if not connected:
            raise RuntimeError(f"Failed to connect OPC UA endpoint {self.endpoint}: {last_error}")
        return client

    def load_series(self) -> Tuple[List[TimeStepData], LevelVolumeCurve]:
        node_map = self._load_node_map()
        client = self._connect_client()
        try:
            station_node = self._find_pump_station_node(client)
            var_nodes = self._browse_name_to_node(station_node)
            series: List[TimeStepData] = []
            points = []

            last_ts = None
            while len(series) < self.steps:
                sample = self._read_one(var_nodes, node_map)
                if sample is None:
                    time.sleep(self.poll_seconds)
                    continue

                ts, level, volume, inflow_m3_s, price_c_per_kwh = sample
                if last_ts is not None and ts == last_ts:
                    time.sleep(self.poll_seconds)
                    continue

                series.append(
                    TimeStepData(
                        timestamp=ts,
                        level_m=level,
                        volume_m3=volume,
                        inflow_m3_s=inflow_m3_s,
                        price_c_per_kwh=price_c_per_kwh,
                    )
                )
                points.append((level, volume))
                last_ts = ts
                time.sleep(self.poll_seconds)

            curve = build_level_volume_curve(points)
            return series, curve
        finally:
            client.disconnect()

    def iter_samples(self) -> Iterator[TimeStepData]:
        node_map = self._load_node_map()
        while True:
            client = self._connect_client()
            try:
                station_node = self._find_pump_station_node(client)
                var_nodes = self._browse_name_to_node(station_node)
                last_ts = None
                while True:
                    ts, level, volume, inflow_m3_s, price_c_per_kwh = self._read_one(var_nodes, node_map)
                    if last_ts is None or ts != last_ts:
                        yield TimeStepData(
                            timestamp=ts,
                            level_m=level,
                            volume_m3=volume,
                            inflow_m3_s=inflow_m3_s,
                            price_c_per_kwh=price_c_per_kwh,
                        )
                        last_ts = ts
                    time.sleep(self.poll_seconds)
            except Exception:
                # Reconnect loop for resilient long-running operation.
                time.sleep(self.retry_delay_seconds)
            finally:
                try:
                    client.disconnect()
                except Exception:
                    pass

    def collect_horizon_from_stream(self, horizon_steps: int) -> Tuple[List[TimeStepData], LevelVolumeCurve]:
        history: Deque[TimeStepData] = deque(maxlen=horizon_steps)
        points: Deque[Tuple[float, float]] = deque(maxlen=horizon_steps)
        for sample in self.iter_samples():
            history.append(sample)
            points.append((sample.level_m, sample.volume_m3))
            if len(history) >= horizon_steps:
                break
        series = list(history)
        curve = build_level_volume_curve(list(points))
        return series, curve

    def _load_node_map(self) -> Dict[str, str]:
        if self.node_map_path is None:
            return dict(DEFAULT_OPC_NODE_MAP)
        with self.node_map_path.open("r", encoding="utf-8") as f:
            custom = json.load(f)
        node_map = dict(DEFAULT_OPC_NODE_MAP)
        node_map.update(custom)
        return node_map

    def _find_pump_station_node(self, client):
        objects = client.get_objects_node()
        for child in objects.get_children():
            browse = child.get_browse_name()
            if browse.Name == "PumpStation":
                return child
        raise RuntimeError("PumpStation node not found on OPC UA server")

    def _browse_name_to_node(self, station_node) -> Dict[str, object]:
        result = {}
        for node in station_node.get_children():
            name = node.get_browse_name().Name
            result[name] = node
        return result

    def _read_one(self, var_nodes: Dict[str, object], node_map: Dict[str, str]):
        required = ["timestamp", "level", "volume", "inflow"]
        for key in required:
            if node_map[key] not in var_nodes:
                raise RuntimeError(f"Missing OPC UA node for {key}: {node_map[key]}")

        ts_raw = var_nodes[node_map["timestamp"]].get_value()
        level = float(var_nodes[node_map["level"]].get_value())
        volume = float(var_nodes[node_map["volume"]].get_value())
        inflow_m3_per_15min = float(var_nodes[node_map["inflow"]].get_value())

        price_key = "price_high" if self.price_column == "high" else "price_normal"
        if node_map[price_key] not in var_nodes:
            raise RuntimeError(f"Missing OPC UA node for {price_key}: {node_map[price_key]}")
        price_c_per_kwh = float(var_nodes[node_map[price_key]].get_value())

        timestamp = self._parse_timestamp(ts_raw)
        inflow_m3_s = inflow_m3_per_15min / 900.0
        return timestamp, level, volume, inflow_m3_s, price_c_per_kwh

    def _parse_timestamp(self, value) -> datetime:
        if isinstance(value, datetime):
            return value
        as_str = str(value).strip()
        try:
            return datetime.fromisoformat(as_str)
        except ValueError:
            # Fallback for common format variations from industrial systems.
            return datetime.strptime(as_str.split("+")[0], "%Y-%m-%d %H:%M:%S")

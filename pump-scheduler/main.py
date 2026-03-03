from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Deque

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from command_publisher import OpcUaCommandPublisher, build_command_payload
from data_loader import build_level_volume_curve
from database import SchedulerRepository
from scheduler import PumpScheduler
from telemetry import OpcUaTelemetrySource

PUMP_IDS = ["1.1", "1.2", "1.3", "1.4", "2.1", "2.2", "2.3", "2.4"]
DT_HOURS = 0.25


def _to_jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def _build_visualization_payload(
    repo: SchedulerRepository, step_minutes: int = 15
) -> dict:
    recent_desc = repo.list_recent_decisions(limit=3000)
    recent_asc = list(reversed(recent_desc))
    valid = [
        d
        for d in recent_asc
        if isinstance(d, dict) and "pumps_on" in d and "timestamp" in d
    ]
    if not valid:
        return {
            "l1_history": [],
            "pump_status": [],
            "daily_runtime_hours": {pid: 0.0 for pid in PUMP_IDS},
        }

    def _parse_ts(d: dict) -> datetime | None:
        try:
            return datetime.fromisoformat(str(d.get("timestamp")))
        except Exception:
            return None

    # Keep only the latest contiguous segment to avoid mixing old replay loops.
    contiguous_desc = []
    prev_ts = None
    for d in reversed(valid):
        ts = _parse_ts(d)
        if ts is None:
            continue
        if prev_ts is not None and ts > prev_ts:
            break
        contiguous_desc.append(d)
        prev_ts = ts
    contiguous = list(reversed(contiguous_desc))

    latest = contiguous[-1]
    latest_dt = _parse_ts(latest)
    if latest_dt is None:
        return {
            "l1_history": [],
            "pump_status": [],
            "daily_runtime_hours": {pid: 0.0 for pid in PUMP_IDS},
        }
    latest_day = latest_dt.date()
    today_valid = [
        d for d in contiguous if (_parse_ts(d) and _parse_ts(d).date() == latest_day)
    ]

    daily_runtime_hours = {pid: 0.0 for pid in PUMP_IDS}
    for d in today_valid:
        on = set(d.get("pumps_on", []))
        for pid in PUMP_IDS:
            if pid in on:
                daily_runtime_hours[pid] += step_minutes / 60.0

    latest_on = set(latest.get("pumps_on", []))
    pump_status = []
    for pid in PUMP_IDS:
        is_on = pid in latest_on
        on_steps = 0
        on_since = None
        if is_on:
            for d in reversed(contiguous):
                if pid in set(d.get("pumps_on", [])):
                    on_steps += 1
                else:
                    break
            if on_steps > 0:
                on_since = contiguous[-on_steps]["timestamp"]
        pump_status.append(
            {
                "pump_id": pid,
                "is_on": is_on,
                "on_since": on_since,
                "on_duration_minutes": on_steps * step_minutes,
                "runtime_today_hours": round(daily_runtime_hours[pid], 2),
            }
        )

    l1_history = [
        {"timestamp": d["timestamp"], "level_m": d.get("level_after_m")}
        for d in contiguous[-192:]
        if d.get("level_after_m") is not None
    ]

    return {
        "l1_history": l1_history,
        "pump_status": pump_status,
        "daily_runtime_hours": daily_runtime_hours,
    }


def _build_constraint_checks(
    latest_constraints: dict | None,
    latest_decision: dict | None,
    visualization: dict | None,
) -> list[dict]:
    checks: list[dict] = []
    if not latest_constraints:
        return checks

    l1 = latest_constraints.get("l1_bounds", {})
    min_viol = int(l1.get("violations_min_steps", 0))
    max_viol = int(l1.get("violations_max_steps", 0))
    checks.append(
        {
            "id": "l1_bounds",
            "label": "L1 bounds (0-8 m)",
            "ok": (min_viol == 0 and max_viol == 0),
            "detail": f"violations min/max: {min_viol} / {max_viol}",
        }
    )

    pumps_on = len((latest_decision or {}).get("pumps_on", []))
    checks.append(
        {
            "id": "continuous_pumping",
            "label": "At least one pump on",
            "ok": pumps_on > 0,
            "detail": f"active pumps: {pumps_on}",
        }
    )

    checks.append(
        {
            "id": "anti_short_cycling",
            "label": "Min 2h ON/OFF rule",
            "ok": True,
            "detail": "hard-guard enforced at execution",
        }
    )

    smooth = latest_constraints.get("smooth_outflow", {})
    out_std = float(smooth.get("outflow_std_m3_s", 0.0))
    checks.append(
        {
            "id": "smooth_outflow",
            "label": "Smooth outflow",
            "ok": out_std <= 0.9,
            "detail": f"std(outflow): {out_std:.3f} m3/s (target <= 0.9)",
        }
    )

    flush = latest_constraints.get("daily_flush", {})
    flush_days = int(flush.get("days_reaching_target", 0))
    checks.append(
        {
            "id": "daily_flush",
            "label": "Daily flush target (L1 < 0.5 m)",
            "ok": flush_days >= 1,
            "detail": f"days reaching target: {flush_days}",
        }
    )

    rb = latest_constraints.get("runtime_balance", {})
    rb_viol = int(rb.get("balance_violation_days", 0))
    checks.append(
        {
            "id": "runtime_balance",
            "label": "Pump runtime balance",
            "ok": rb_viol == 0,
            "detail": f"violation days: {rb_viol}",
        }
    )

    eff = latest_constraints.get("efficiency", {})
    sec = float(eff.get("specific_energy_kwh_per_m3", 0.0))
    checks.append(
        {
            "id": "efficiency",
            "label": "Energy efficiency (kWh/m3)",
            "ok": sec <= 0.30,
            "detail": f"specific energy: {sec:.3f} kWh/m3 (target <= 0.30)",
        }
    )

    checks.append(
        {
            "id": "near_full_speed",
            "label": "Near full speed operation",
            "ok": True,
            "detail": "discrete full-speed pump dispatch",
        }
    )

    _ = visualization
    return checks


def build_constraints_report(summary, latest_decision) -> dict:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "latest_timestamp": latest_decision.timestamp.isoformat(),
        "l1_bounds": {
            "min_m": 0.0,
            "max_m": 8.0,
            "violations_min_steps": summary.violation_l1_min_steps,
            "violations_max_steps": summary.violation_l1_max_steps,
        },
        "continuous_pumping": {"always_on": True},
        "anti_short_cycling": {"min_on_off_hours": 2.0, "enforced": True},
        "near_full_speed_operation": {
            "control_mode": "discrete full-speed pump selection"
        },
        "smooth_outflow": {"outflow_std_m3_s": summary.outflow_std_m3_s},
        "daily_flush": {
            "target_level_m": 0.5,
            "days_reaching_target": summary.daily_flush_hits,
        },
        "efficiency": {
            "specific_energy_kwh_per_m3": summary.specific_energy_kwh_per_m3
        },
        "runtime_balance": {
            "per_pump_runtime_hours": summary.per_pump_runtime_hours,
            "max_daily_runtime_spread_hours": summary.max_daily_runtime_spread_hours,
            "balance_violation_days": summary.daily_runtime_balance_violations,
        },
        "telemetry": {"source": "opcua", "mode": "continuous"},
    }


class SchedulerService:
    def __init__(self) -> None:
        self.opc_endpoint = os.getenv(
            "OPCUA_ENDPOINT", "opc.tcp://opcua-server:4840/wastewater/"
        )
        self.opc_poll_seconds = float(os.getenv("OPC_POLL_SECONDS", "0.2"))
        self.rolling_steps = int(os.getenv("ROLLING_STEPS", "192"))
        self.min_history_steps = int(os.getenv("MIN_HISTORY_STEPS", "32"))
        self.reoptimize_every_samples = int(os.getenv("REOPTIMIZE_EVERY_SAMPLES", "1"))
        self.price_column = os.getenv("PRICE_COLUMN", "normal")
        self.control_step_minutes = int(os.getenv("CONTROL_STEP_MINUTES", "15"))
        self.command_mode = os.getenv("COMMAND_MODE", "db")  # db|opcua|none
        self.command_opc_endpoint = os.getenv(
            "COMMAND_OPCUA_ENDPOINT", self.opc_endpoint
        )
        self.command_node_map = os.getenv("COMMAND_NODE_MAP", "")
        self.telemetry_node_map = os.getenv("OPC_NODE_MAP", "")
        self.db_path = Path(os.getenv("DB_PATH", "/app/data/scheduler.db"))
        self.sim_speed_node = os.getenv("SIMULATION_SPEED_NODE", "SimulationSpeedup")

        self.repo = SchedulerRepository(self.db_path)
        self.scheduler = PumpScheduler()
        self.telemetry = OpcUaTelemetrySource(
            endpoint=self.opc_endpoint,
            poll_seconds=self.opc_poll_seconds,
            price_column=self.price_column,
            node_map_path=(
                Path(self.telemetry_node_map) if self.telemetry_node_map else None
            ),
        )
        self.opc_publisher = None
        if self.command_mode == "opcua":
            if not self.command_node_map:
                raise ValueError("COMMAND_NODE_MAP is required when COMMAND_MODE=opcua")
            self.opc_publisher = OpcUaCommandPublisher(
                endpoint=self.command_opc_endpoint,
                node_map_path=Path(self.command_node_map),
            )

        self._history: Deque = deque(
            maxlen=max(self.rolling_steps, self.min_history_steps)
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._live_pump_states = {
            pid: {"is_on": False, "steps_in_state": 10_000} for pid in PUMP_IDS
        }

    def get_simulation_speed(self) -> float | None:
        try:
            from opcua import Client  # type: ignore

            client = Client(self.opc_endpoint)
            client.connect()
            try:
                objects = client.get_objects_node()
                station = None
                for child in objects.get_children():
                    if child.get_browse_name().Name == "PumpStation":
                        station = child
                        break
                if station is None:
                    return None
                for node in station.get_children():
                    if node.get_browse_name().Name == self.sim_speed_node:
                        return float(node.get_value())
                return None
            finally:
                client.disconnect()
        except Exception:
            return None

    def set_simulation_speed(self, value: float) -> float:
        speed = max(1.0, min(5000.0, float(value)))
        from opcua import Client  # type: ignore

        last_error = None
        for _ in range(5):
            client = Client(self.opc_endpoint)
            try:
                client.connect()
                objects = client.get_objects_node()
                station = None
                for child in objects.get_children():
                    if child.get_browse_name().Name == "PumpStation":
                        station = child
                        break
                if station is None:
                    raise RuntimeError("PumpStation node not found")
                for node in station.get_children():
                    if node.get_browse_name().Name == self.sim_speed_node:
                        node.set_value(float(speed))
                        return speed
                raise RuntimeError(f"{self.sim_speed_node} node not found")
            except Exception as exc:
                last_error = exc
                time.sleep(0.2)
            finally:
                try:
                    client.disconnect()
                except Exception:
                    pass
        raise RuntimeError(f"Failed to set simulation speed: {last_error}")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        sample_count = 0
        cycles = 0

        for sample in self.telemetry.iter_samples():
            if self._stop_event.is_set():
                break

            sample_count += 1
            self._history.append(sample)

            if len(self._history) < self.min_history_steps:
                self.repo.save_cycle(
                    decision={
                        "timestamp": sample.timestamp.isoformat(),
                        "status": "warming_up",
                        "pumps_on": [],
                        "inflow_m3_s": sample.inflow_m3_s,
                        "outflow_m3_s": 0.0,
                        "level_before_m": sample.level_m,
                        "level_after_m": sample.level_m,
                        "flush_active": False,
                    },
                    summary={"status": "warming_up"},
                    constraints={"status": "warming_up"},
                    operations={
                        "status": "warming_up",
                        "samples_collected": len(self._history),
                        "samples_required": self.min_history_steps,
                        "latest_timestamp": sample.timestamp.isoformat(),
                    },
                )
                continue

            if sample_count % max(1, self.reoptimize_every_samples) != 0:
                continue

            series = list(self._history)
            curve = build_level_volume_curve([(s.level_m, s.volume_m3) for s in series])
            decisions, summary = self.scheduler.run(series, curve)
            latest = decisions[-1]
            latest = self._enforce_min_duration_guard(latest)

            latest_dict = _to_jsonable(asdict(latest))
            summary_dict = _to_jsonable(asdict(summary))
            constraints = build_constraints_report(summary, latest)

            operations = {
                "status": "running",
                "cycle": cycles + 1,
                "latest_timestamp": latest.timestamp.isoformat(),
                "latest_inflow_m3_s": latest.inflow_m3_s,
                "latest_outflow_m3_s": latest.outflow_m3_s,
                "latest_price_c_per_kwh": latest.price_c_per_kwh,
                "pumps_on": latest.pumps_on,
                "flush_active": latest.flush_active,
                "rolling_steps": len(series),
            }

            self.repo.save_cycle(latest_dict, summary_dict, constraints, operations)

            if self.command_mode != "none":
                payload = build_command_payload(latest)
                dispatched = False
                if self.opc_publisher is not None:
                    try:
                        self.opc_publisher.publish_payload(payload)
                        dispatched = True
                    except Exception:
                        dispatched = False
                self.repo.enqueue_command(payload, self.command_mode, dispatched)

            cycles += 1
            print(
                f"cycle={cycles} ts={latest.timestamp.isoformat()} "
                f"inflow={latest.inflow_m3_s:.3f} outflow={latest.outflow_m3_s:.3f} "
                f"pumps={','.join(latest.pumps_on)}"
            )

            time.sleep(0.001)

    def _enforce_min_duration_guard(self, latest):
        min_steps = 8  # 2h at 15 min control interval
        proposed_on = set(latest.pumps_on)
        forced_on = set()
        forced_off = set()

        for pid, st in self._live_pump_states.items():
            if st["is_on"] and st["steps_in_state"] < min_steps:
                forced_on.add(pid)
            if (not st["is_on"]) and st["steps_in_state"] < min_steps:
                forced_off.add(pid)

        final_on = (proposed_on | forced_on) - forced_off
        if not final_on:
            candidates = [
                p for p in self.scheduler.pumps if p.pump_id not in forced_off
            ]
            if not candidates:
                candidates = self.scheduler.pumps
            best = max(candidates, key=lambda p: (p.efficiency, p.flow_m3_s))
            final_on.add(best.pump_id)

        level = latest.level_before_m
        outflow = sum(
            self.scheduler._pump_flow_at_level(
                self.scheduler._pump_map[pid], level
            )  # noqa: SLF001
            for pid in final_on
        )
        power = sum(
            self.scheduler._pump_power_at_level(
                self.scheduler._pump_map[pid], level
            )  # noqa: SLF001
            for pid in final_on
        )
        latest.pumps_on = sorted(final_on)
        latest.outflow_m3_s = outflow
        latest.total_power_kw = power
        latest.energy_kwh = power * DT_HOURS
        latest.cost_eur = latest.energy_kwh * (latest.price_c_per_kwh / 100.0)

        on_set = set(latest.pumps_on)
        for pid, st in self._live_pump_states.items():
            now_on = pid in on_set
            if now_on == st["is_on"]:
                st["steps_in_state"] += 1
            else:
                st["is_on"] = now_on
                st["steps_in_state"] = 1

        return latest


service = SchedulerService()
app = FastAPI(title="Pump Scheduler Status", version="1.0.0")


@app.on_event("startup")
def _startup() -> None:
    service.start()


@app.on_event("shutdown")
def _shutdown() -> None:
    service.stop()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/status")
def api_status() -> dict:
    latest_decision = service.repo.get_latest("decisions")
    latest_constraints = service.repo.get_latest("constraints")
    visualization = _build_visualization_payload(
        service.repo, step_minutes=service.control_step_minutes
    )
    return {
        "operations": service.repo.get_operations(),
        "latest_decision": latest_decision,
        "latest_summary": service.repo.get_latest("summaries"),
        "latest_constraints": latest_constraints,
        "recent_decisions": service.repo.list_recent_decisions(limit=20),
        "pending_commands_count": service.repo.count_pending_commands(),
        "recent_commands": service.repo.list_commands(limit=10, only_pending=False),
        "visualization": visualization,
        "constraint_checks": _build_constraint_checks(
            latest_constraints, latest_decision, visualization
        ),
        "simulation_speedup": service.get_simulation_speed(),
    }


@app.get("/api/simulation/speed")
def get_simulation_speed() -> dict:
    return {"speedup": service.get_simulation_speed()}


@app.post("/api/simulation/speed")
def set_simulation_speed(speedup: float = Query(..., ge=1.0, le=5000.0)) -> dict:
    try:
        value = service.set_simulation_speed(speedup)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"speedup": value}


@app.get("/api/commands")
def api_commands(
    limit: int = Query(50, ge=1, le=500), pending_only: bool = False
) -> dict:
    return {
        "commands": service.repo.list_commands(limit=limit, only_pending=pending_only)
    }


@app.post("/api/commands/{command_id}/ack")
def ack_command(command_id: int) -> dict:
    try:
        service.repo.mark_command_dispatched(command_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "command_id": command_id}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <title>Pump Scheduler Status</title>
  <style>
    body { font-family: sans-serif; margin: 20px; background: #f4f6f8; color: #1f2937; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 12px; }
    .card { background: white; border-radius: 8px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
    .split { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; align-items: stretch; }
    .panel { display: flex; flex-direction: column; min-height: 0; }
    .panel .card { flex: 1; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { border-bottom: 1px solid #e5e7eb; text-align: left; padding: 6px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .state-on { color: #166534; font-weight: 700; }
    .state-off { color: #991b1b; font-weight: 700; }
    .check-ok { color: #166534; font-weight: 700; }
    .check-bad { color: #991b1b; font-weight: 700; }
    .check-neutral { color: #92400e; font-weight: 700; }
    #l1chart { width: 100%; height: 220px; border: 1px solid #e5e7eb; border-radius: 6px; background: #fff; }
    @media (max-width: 900px) { .split { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <h2>Pump Scheduler Live Status</h2>
  <div class='grid'>
    <div class='card'><b>Cycle</b><div id='cycle' class='mono'>-</div></div>
    <div class='card'><b>Timestamp</b><div id='ts' class='mono'>-</div></div>
    <div class='card'><b>Inflow / Outflow (m3/s)</b><div id='flow' class='mono'>-</div></div>
    <div class='card'><b>Pumps On</b><div id='pumps' class='mono'>-</div></div>
    <div class='card'><b>Constraints</b><div id='constraints' class='mono'>-</div></div>
    <div class='card'><b>Pending Commands</b><div id='pending' class='mono'>-</div></div>
    <div class='card'>
      <b>Simulation Speed</b>
      <div id='simspeed' class='mono' style='margin: 6px 0;'>-</div>
      <div style='display:flex; gap:6px; margin-top:6px;'>
        <button onclick='applySpeedPreset(1)'>Real-time (1x)</button>
        <button onclick='applySpeedPreset(100)'>100x</button>
        <button onclick='applySpeedPreset(900)'>900x</button>
        <button onclick='applySpeedPreset(1800)'>1800x</button>
      </div>
      <div id='speedmsg' class='mono' style='margin-top:6px; font-size:12px;'></div>
    </div>
  </div>

  <h3>Recent Decisions</h3>
  <div class='card'>
    <table>
      <thead><tr><th>Timestamp</th><th>Inflow</th><th>Outflow</th><th>Pumps</th><th>Flush</th></tr></thead>
      <tbody id='rows'></tbody>
    </table>
  </div>
  <h3>L1 Level Trend</h3>
  <div class='card'>
    <svg id='l1chart' viewBox='0 0 800 220' preserveAspectRatio='none'>
      <polyline id='l1line' fill='none' stroke='#0ea5e9' stroke-width='2' points='' />
    </svg>
  </div>
  <div class='split'>
    <div class='panel'>
      <h3>Pump Runtime</h3>
      <div class='card'>
        <table>
          <thead><tr><th>Pump</th><th>On</th><th>On Since</th><th>Current On Duration (min)</th><th>Runtime Today (h)</th></tr></thead>
          <tbody id='pumprows'></tbody>
        </table>
      </div>
    </div>
    <div class='panel'>
      <h3>Constraints</h3>
      <div class='card'>
        <table>
          <thead><tr><th>Status</th><th>Constraint</th><th>Detail</th></tr></thead>
          <tbody id='constraints-list'></tbody>
        </table>
      </div>
    </div>
  </div>
  <h3>Recent Commands</h3>
  <div class='card'>
    <table>
      <thead><tr><th>ID</th><th>Effective TS</th><th>Dispatched</th><th>Mode</th><th>Created</th></tr></thead>
      <tbody id='cmdrows'></tbody>
    </table>
  </div>

<script>
async function refresh() {
  const r = await fetch('/api/status');
  const d = await r.json();
  const op = d.operations || {};
  const c = d.latest_constraints || {};
  const viz = d.visualization || {};
  const checks = d.constraint_checks || [];
  document.getElementById('cycle').textContent = op.cycle ?? op.status ?? '-';
  document.getElementById('ts').textContent = op.latest_timestamp ?? '-';
  document.getElementById('flow').textContent = `${(op.latest_inflow_m3_s ?? '-')} / ${(op.latest_outflow_m3_s ?? '-')}`;
  document.getElementById('pumps').textContent = (op.pumps_on || []).join(', ') || '-';
  const okCount = checks.filter(x => x.ok === true).length;
  const badCount = checks.filter(x => x.ok === false).length;
  document.getElementById('constraints').textContent = `ok: ${okCount}, failing: ${badCount}`;
  const cl = document.getElementById('constraints-list');
  cl.innerHTML = '';
  checks.forEach(ch => {
    const div = document.createElement('tr');
    const cls = ch.ok === true ? 'check-ok' : (ch.ok === false ? 'check-bad' : 'check-neutral');
    const state = ch.ok === true ? 'PASS' : (ch.ok === false ? 'FAIL' : 'INFO');
    div.innerHTML = `<td class='${cls}'>${state}</td><td>${ch.label}</td><td>${ch.detail}</td>`;
    cl.appendChild(div);
  });
  document.getElementById('pending').textContent = d.pending_commands_count ?? '-';
  const sim = d.simulation_speedup;
  document.getElementById('simspeed').textContent = sim ? `${sim.toFixed(0)}x` : 'unavailable';

  const levels = viz.l1_history || [];
  if (levels.length > 1) {
    const vals = levels.map(x => Number(x.level_m));
    const minV = Math.min(...vals);
    const maxV = Math.max(...vals);
    const span = Math.max(0.001, maxV - minV);
    const points = vals.map((v, i) => {
      const x = (i / (vals.length - 1)) * 800;
      const y = 210 - ((v - minV) / span) * 200;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });
    document.getElementById('l1line').setAttribute('points', points.join(' '));
  } else {
    document.getElementById('l1line').setAttribute('points', '');
  }

  const pumpRows = document.getElementById('pumprows');
  pumpRows.innerHTML = '';
  (viz.pump_status || []).forEach(p => {
    const tr = document.createElement('tr');
    const stateClass = p.is_on ? 'state-on' : 'state-off';
    const stateText = p.is_on ? 'ON' : 'OFF';
    tr.innerHTML = `<td class='mono'>${p.pump_id}</td><td class='${stateClass}'>${stateText}</td><td class='mono'>${p.on_since || '-'}</td><td>${p.on_duration_minutes ?? 0}</td><td>${p.runtime_today_hours ?? 0}</td>`;
    pumpRows.appendChild(tr);
  });

  const rows = document.getElementById('rows');
  rows.innerHTML = '';
  (d.recent_decisions || []).slice(0, 20).forEach(item => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td class='mono'>${item.timestamp || '-'}</td><td>${item.inflow_m3_s ?? '-'}</td><td>${item.outflow_m3_s ?? '-'}</td><td class='mono'>${(item.pumps_on || []).join(', ')}</td><td>${item.flush_active ?? '-'}</td>`;
    rows.appendChild(tr);
  });

  const cmdRows = document.getElementById('cmdrows');
  cmdRows.innerHTML = '';
  (d.recent_commands || []).forEach(cmd => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${cmd.id}</td><td class='mono'>${cmd.payload?.effective_timestamp || '-'}</td><td>${cmd.dispatched}</td><td>${cmd.dispatch_mode}</td><td class='mono'>${cmd.created_at}</td>`;
    cmdRows.appendChild(tr);
  });
}

async function applySpeedPreset(v) {
  const msg = document.getElementById('speedmsg');
  msg.textContent = `Setting ${v}x...`;
  try {
    const r = await fetch(`/api/simulation/speed?speedup=${encodeURIComponent(v)}`, { method: 'POST' });
    if (!r.ok) {
      const t = await r.text();
      msg.textContent = `Failed: ${t}`;
      return;
    }
    msg.textContent = `Set to ${v}x`;
    await refresh();
  } catch (e) {
    msg.textContent = `Failed: ${e}`;
  }
}
setInterval(refresh, 2000);
refresh();
</script>
</body>
</html>
"""

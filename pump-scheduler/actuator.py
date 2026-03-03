from __future__ import annotations

import os
import time
from pathlib import Path

from command_publisher import OpcUaCommandPublisher
from database import SchedulerRepository


def main() -> int:
    db_path = Path(os.getenv("DB_PATH", "/app/data/scheduler.db"))
    mode = os.getenv("ACTUATOR_MODE", "dryrun")  # dryrun|opcua
    poll_seconds = float(os.getenv("ACTUATOR_POLL_SECONDS", "1.0"))
    opc_endpoint = os.getenv("COMMAND_OPCUA_ENDPOINT", "opc.tcp://opcua-server:4840/wastewater/")
    command_node_map = os.getenv("COMMAND_NODE_MAP", "")

    repo = SchedulerRepository(db_path)

    publisher = None
    if mode == "opcua":
        if not command_node_map:
            raise ValueError("COMMAND_NODE_MAP is required for ACTUATOR_MODE=opcua")
        publisher = OpcUaCommandPublisher(endpoint=opc_endpoint, node_map_path=Path(command_node_map))

    print(f"actuator starting mode={mode} poll_seconds={poll_seconds}")
    while True:
        constraints = repo.get_latest("constraints")
        if constraints is not None and constraints.get("status") != "warming_up":
            l1_bounds = constraints.get("l1_bounds", {})
            min_viol = int(l1_bounds.get("violations_min_steps", 0))
            max_viol = int(l1_bounds.get("violations_max_steps", 0))
            if min_viol > 0 or max_viol > 0:
                print(
                    "actuator safety hold: constraints violated "
                    f"(min={min_viol}, max={max_viol}); skipping dispatch"
                )
                time.sleep(poll_seconds)
                continue

        pending = repo.fetch_pending_commands(limit=50)
        if not pending:
            time.sleep(poll_seconds)
            continue

        for cmd in pending:
            cmd_id = cmd["id"]
            payload = cmd["payload"]
            try:
                if publisher is not None:
                    publisher.publish_payload(payload)
                repo.mark_command_dispatched(cmd_id)
                print(f"actuator dispatched command_id={cmd_id} effective={payload.get('effective_timestamp')}")
            except Exception as exc:
                print(f"actuator failed command_id={cmd_id} error={exc}")

        time.sleep(0.01)


if __name__ == "__main__":
    raise SystemExit(main())

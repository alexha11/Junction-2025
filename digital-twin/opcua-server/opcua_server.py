import os
import time
import sqlite3
from typing import Dict, cast
from threading import Thread
import pathlib

import pandas as pd
import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from opcua import Server, ua, Node

from parse_historical_data import PARQUET_DATA_FILE_PATH


SERVER_URI = "http://localhost:4840/wastewater"
SPEEDUP = int(os.environ.get("SPEEDUP", 900))


class HistoricalData:
    def __init__(self, file_path: str = PARQUET_DATA_FILE_PATH):
        self.hist_df = pd.read_parquet(file_path)
        self.hist_df.index = pd.to_datetime(self.hist_df.index)
        self.hist_df.sort_index(inplace=True)
        self.current_idx = 0
        self.simulation_time = None

    def get_current_row(self) -> pd.Series | None:
        if self.current_idx < len(self.hist_df):
            self.current_idx += 1
            return self.hist_df.iloc[self.current_idx]
        return None

    def reload_history(self, file_path: str) -> None:
        """
        Replace the current historical dataset with a new parquet file.
        Assumes the new file has compatible columns. Does not recreate
        OPC nodes — this keeps node IDs stable. If columns change you
        should extend this to recreate variables.
        """
        if not pathlib.Path(file_path).exists():
            raise FileNotFoundError(file_path)
        self.hist_data = HistoricalData(file_path)
        # reset simulation time shown in server
        if self.simulation_time:
            self.simulation_time.set_value(str(pd.Timestamp.now()))
        print(f"Reloaded history from {file_path}")


class WastewaterOPCUAServer:
    def __init__(self, endpoint: str = "opc.tcp://0.0.0.0:4840/wastewater/"):
        self.server = Server()
        self.server.set_endpoint(endpoint)
        self.hist_data = HistoricalData()
        self.var_map: Dict[str, Node] = {}
        self.simulation_time_var = None
        self._setup_database()
        self._setup_server()

    def _setup_server(self) -> None:
        idx = self.server.register_namespace(SERVER_URI)

        objects = self.server.get_objects_node()
        self.station = objects.add_object(idx, "PumpStation")
        self.idx = idx

    def _setup_database(self):
        self.conn = sqlite3.connect("historical_opc_data.db", check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS variable_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                variable_name TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                value REAL NOT NULL
            )
        """
        )
        self.conn.commit()

    def add_variable(
        self,
        df_name: str,
        display_name: str,
        initial=0.0,
        writable=False,
        historize=True,
    ) -> Node:
        opc_var = self.station.add_variable(self.idx, display_name, initial)
        if writable:
            opc_var.set_writable()

        if historize:
            opc_var.set_attribute(ua.AttributeIds.Historizing, ua.DataValue(True))

        self.var_map[df_name] = opc_var
        return opc_var

    def _store_variable_history(
        self, variable_name: str, timestamp: pd.Timestamp, value: float
    ):
        self.conn.execute(
            "INSERT INTO variable_history (variable_name, timestamp, value) VALUES (?, ?, ?)",
            (variable_name, timestamp.isoformat(), value),
        )
        self.conn.commit()

    def create_all_variables(self) -> None:
        data_columns = list(self.hist_data.hist_df.columns)

        for col_name in data_columns:
            display_name = self.get_display_name(data_columns.index(col_name))

            self.add_variable(col_name, display_name)

        self.simulation_time_var = self.station.add_variable(
            self.idx, "SimulationTime", str(pd.Timestamp.now())
        )
        self.simulation_time_var.set_writable(False)

    def get_display_name(self, position: int) -> str:
        ordered_column_display_names = [
            "WaterLevelInTunnel.L2.m",
            "WaterVolumeInTunnel.L1.m3",
            "SumOfPumpedFlowToWwtp.F2.m3h",
            "InflowToTunnel.F1.m3per15min",
            "PumpFlow.1.1.m3h",
            "PumpFlow.1.2.m3h",
            "PumpFlow.1.3.m3h",
            "PumpFlow.1.4.m3h",
            "PumpFlow.2.1.m3h",
            "PumpFlow.2.2.m3h",
            "PumpFlow.2.3.m3h",
            "PumpFlow.2.4.m3h",
            "PumpEfficiency.1.1.kw",
            "PumpEfficiency.1.2.kw",
            "PumpEfficiency.1.3.kw",
            "PumpEfficiency.1.4.kw",
            "PumpEfficiency.2.1.kw",
            "PumpEfficiency.2.2.kw",
            "PumpEfficiency.2.3.kw",
            "PumpEfficiency.2.4.kw",
            "PumpFrequency.1.1.hz",
            "PumpFrequency.1.2.hz",
            "PumpFrequency.1.3.hz",
            "PumpFrequency.1.4.hz",
            "PumpFrequency.2.1.hz",
            "PumpFrequency.2.2.hz",
            "PumpFrequency.2.3.hz",
            "PumpFrequency.2.4.hz",
            "ElectricityPrice.1.High.ckwh",
            "ElectricityPrice.2.Normal.ckwh",
        ]

        data_columns = list(self.hist_data.hist_df.columns)
        if 0 <= position < len(data_columns):
            display_name = ordered_column_display_names[position]
            return display_name
        else:
            raise IndexError("Position out of range of data columns")

    def update_variables(self, row: pd.Series, sim_timestamp: pd.Timestamp) -> None:
        for col_name, opc_var in self.var_map.items():
            if col_name in row.index:
                try:
                    value = row[col_name]
                    if pd.notna(value):
                        float_value = float(value)
                        opc_var.set_value(ua.Variant(float_value, ua.VariantType.Float))

                        self._store_variable_history(
                            col_name, sim_timestamp, float_value
                        )
                except (ValueError, TypeError) as e:
                    print(
                        f"Warning: Could not convert {col_name}={row[col_name]} to float: {e}"
                    )

    def update_simulation_time(self, timestamp: pd.Timestamp) -> None:
        if self.simulation_time_var:
            self.simulation_time_var.set_value(str(timestamp))

    def start(self) -> None:
        self.server.start()
        print(f"OPC UA server started at: {self.server.get_application_uri()}")

    def stop(self) -> None:
        self.server.stop()
        print("OPC UA server stopped.")


class SimulationController:
    def __init__(self, hist_data: HistoricalData, speedup: int = 1):
        self.hist_data = hist_data
        self.speedup = speedup  # 1 = real-time, 10 = 10x faster, 900 = 900x faster

    def run_simulation(self, opc_server: WastewaterOPCUAServer) -> None:
        print(f"Starting simulation with {self.speedup}x speedup")

        try:
            while True:
                for timestamp, row in self.hist_data.hist_df.iterrows():
                    print(f"Updating to timestamp: {timestamp}")

                    opc_server.update_variables(row, cast(pd.Timestamp, timestamp))
                    opc_server.update_simulation_time(cast(pd.Timestamp, timestamp))

                    time.sleep(900 / self.speedup)

                print("Simulation completed, restarting...")
        except KeyboardInterrupt:
            print("Simulation stopped by user")


def start_control_api(opc_server: WastewaterOPCUAServer, host="0.0.0.0", port=8000):
    app = FastAPI()

    @app.post("/reload-history")
    async def reload_history(
        file: UploadFile | None = File(None), filename: str | None = None
    ):
        # Ensure a single sandboxed data directory
        data_dir = pathlib.Path("./data")
        data_dir.mkdir(parents=True, exist_ok=True)

        # allow only safe filenames (alphanum, dot, underscore, hyphen)
        SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

        # helper to validate a name stays inside data_dir
        def _safe_target(name: str) -> pathlib.Path | None:
            if not name:
                return None
            # strip any directory components
            name = pathlib.Path(name).name
            if not SAFE_NAME_RE.fullmatch(name):
                return None
            target = data_dir / name
            try:
                # ensure resolved parent is exactly data_dir (prevents traversal)
                if target.resolve().parent != data_dir.resolve():
                    return None
            except Exception:
                return None
            return target

        # Uploaded file case
        if file is not None:
            raw_name = getattr(file, "filename", "") or ""
            target = _safe_target(raw_name)
            if target is None:
                return JSONResponse(
                    {"ok": False, "error": "invalid or unsafe filename"},
                    status_code=400,
                )
            content = await file.read()
            target.write_bytes(content)
            try:
                opc_server.hist_data.reload_history(str(target))
            except Exception as e:
                return JSONResponse(
                    {"ok": False, "error": f"Unable to reload history: {e}"},
                    status_code=500,
                )
            return {"ok": True, "path": str(target)}

        # Named file already present in ./data
        if filename:
            target = _safe_target(filename)
            if target is None:
                return JSONResponse(
                    {"ok": False, "error": "invalid or unsafe filename"},
                    status_code=400,
                )
            if not target.exists():
                return JSONResponse(
                    {"ok": False, "error": "file not found in data directory"},
                    status_code=404,
                )
            try:
                opc_server.hist_data.reload_history(str(target))
            except Exception as e:
                return JSONResponse(
                    {"ok": False, "error": f"Unable to reload history: {e}"},
                    status_code=500,
                )
            return {"ok": True, "path": str(target)}

        return JSONResponse(
            {"ok": False, "error": "no file or filename provided"}, status_code=400
        )


def main():
    opc_server = WastewaterOPCUAServer()
    simulation_controller = SimulationController(opc_server.hist_data, speedup=SPEEDUP)

    opc_server.create_all_variables()
    opc_server.start()

    start_control_api(opc_server)

    try:
        simulation_controller.run_simulation(opc_server)
    finally:
        opc_server.stop()


if __name__ == "__main__":
    main()

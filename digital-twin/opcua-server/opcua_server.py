import os
import time
from typing import Dict, cast

import pandas as pd
from opcua import Server, ua, Node

from parse_historical_data import PARQUET_DATA_FILE_PATH


SERVER_URI = "http://localhost:4840/wastewater"
SPEEDUP = int(os.environ.get("MCP_SERVER_PORT", 900))


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


class WastewaterOPCUAServer:
    def __init__(self, endpoint: str = "opc.tcp://0.0.0.0:4840/wastewater/"):
        self.server = Server()
        self.server.set_endpoint(endpoint)
        self.hist_data = HistoricalData()
        self.var_map: Dict[str, Node] = {}
        self.simulation_time_var = None
        self._setup_server()

    def _setup_server(self) -> None:
        idx = self.server.register_namespace(SERVER_URI)

        objects = self.server.get_objects_node()
        self.station = objects.add_object(idx, "PumpStation")
        self.idx = idx

    def add_variable(
        self, df_name: str, display_name: str, initial=0.0, writable=False
    ) -> Node:
        opc_var = self.station.add_variable(self.idx, display_name, initial)
        if writable:
            opc_var.set_writable()
        self.var_map[df_name] = opc_var
        return opc_var

    def create_all_variables(self) -> None:
        data_columns = list(self.hist_data.hist_df.columns)

        for col_name in data_columns:
            display_name = col_name.replace("_", " ").title().replace(" ", "")

            self.add_variable(col_name, display_name)

        self.simulation_time_var = self.station.add_variable(
            self.idx, "SimulationTime", str(pd.Timestamp.now())
        )
        self.simulation_time_var.set_writable(False)

    def update_variables(self, row: pd.Series) -> None:
        for col_name, opc_var in self.var_map.items():
            if col_name in row.index:
                try:
                    value = row[col_name]
                    if pd.notna(value):
                        float_value = float(value)
                        opc_var.set_value(ua.Variant(float_value, ua.VariantType.Float))
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

                    opc_server.update_variables(row)
                    opc_server.update_simulation_time(cast(pd.Timestamp, timestamp))

                    time.sleep(900 / self.speedup)

                print("Simulation completed, restarting...")
        except KeyboardInterrupt:
            print("Simulation stopped by user")


def main():
    opc_server = WastewaterOPCUAServer()
    simulation_controller = SimulationController(opc_server.hist_data, speedup=SPEEDUP)

    opc_server.create_all_variables()
    opc_server.start()

    try:
        simulation_controller.run_simulation(opc_server)
    finally:
        opc_server.stop()


if __name__ == "__main__":
    main()

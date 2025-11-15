from datetime import datetime
from opcua import Client

DEFAULT_OPCUA_SERVER_URL = "opc.tcp://localhost:4840/wastewater/"


async def get_digital_twin_current_state(self):
    try:
        now = datetime.now()
        self._logger.debug(
            "Fetching current digital twin synthetic system state", now.isoformat()
        )

        client = Client(DEFAULT_OPCUA_SERVER_URL)
        client.connect()

        # Read all pump station variables
        objects = client.get_objects_node()
        values = {}

        for child in objects.get_children():
            browse_name = str(child.get_browse_name())
            if "PumpStation" in browse_name:
                pump_vars = child.get_children()

                for var in pump_vars:
                    var_name = str(var.get_browse_name()).replace("2:", "")
                    value = var.get_value()
                    values[var_name] = value

        client.disconnect()
        return values
    except Exception as e:
        self._logger.error("Error connecting to digital twin OPC UA server: %s", e)
        return {}

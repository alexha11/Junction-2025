from opcua import Client
import time

client = Client("opc.tcp://localhost:4840/wastewater/")
try:
    client.connect()
    print("Connected")

    objects = client.get_objects_node()
    children = objects.get_children()
    print(f"Available objects: {[child.get_browse_name() for child in children]}")

    pump_station = None
    for child in children:
        if "PumpStation" in str(child.get_browse_name()):
            pump_station = child
            break

    if pump_station:
        variables = pump_station.get_children()
        print(f"Found {len(variables)} variables")

        for i, var in enumerate(variables[:50]):
            try:
                value = var.get_value()
                name = var.get_browse_name()
                print(f"  {name}: {value}")
            except Exception as e:
                print(f"  Error reading {var}: {e}")

        print("\nMonitoring updates for 10 seconds...")
        for _ in range(10):
            try:
                sim_time = None
                for var in variables:
                    if "SimulationTime" in str(var.get_browse_name()):
                        sim_time = var.get_value()
                        break
                if sim_time:
                    print(f"Current simulation time: {sim_time}")
            except:
                pass
            time.sleep(1)

finally:
    client.disconnect()
    print("Disconnected")

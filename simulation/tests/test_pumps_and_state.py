from simulation.dataset import DEFAULT_DATA_PATH
from simulation.pumps import PumpCommand, build_fleet_from_historical_data
from simulation.state import PumpingSimulation, SimulationState
from simulation.tunnel import TunnelModel


def test_build_fleet_from_dataset():
    fleet = build_fleet_from_historical_data(dataset_path=DEFAULT_DATA_PATH)
    assert fleet.curves, "Expected pump curves to be derived from dataset"


def test_simulation_step_decreases_volume_when_pumping():
    fleet = build_fleet_from_historical_data(dataset_path=DEFAULT_DATA_PATH)
    tunnel = TunnelModel()
    sim = PumpingSimulation(tunnel=tunnel, fleet=fleet)
    initial_level = 6.0
    initial_volume = tunnel.volume_from_level(initial_level)
    state = SimulationState(level_m=initial_level, volume_m3=initial_volume)
    commands = [PumpCommand(pump_id=next(iter(fleet.curves.keys())), frequency_hz=50.0)]
    result = sim.step(state=state, inflow_m3_s=0.5, commands=commands)
    assert result.state.volume_m3 < initial_volume
    assert result.total_outflow_m3_s > 0.5

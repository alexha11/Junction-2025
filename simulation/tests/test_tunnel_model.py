import pytest

from simulation.tunnel import TunnelModel


def test_volume_level_round_trip_mid_levels():
    model = TunnelModel()
    sample_levels = [0.2, 1.0, 4.5, 6.2, 8.0]
    for level in sample_levels:
        volume = model.volume_from_level(level)
        round_trip_level = model.level_from_volume(volume)
        assert round_trip_level == pytest.approx(level, rel=1e-2, abs=1e-2)


def test_volume_monotonicity():
    model = TunnelModel()
    levels = [0.0, 0.4, 1.5, 5.9, 7.0, 8.6, 10.0]
    volumes = [model.volume_from_level(level) for level in levels]
    assert volumes == sorted(volumes)

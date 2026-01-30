import pytest

from server.services.config_service import ConfigService


def test_validate_strategy_type_accepts_known():
    service = ConfigService()
    assert service._validate_strategy_type("graph") == "graph"
    assert service._validate_strategy_type("GRID") == "grid"
    assert service._validate_strategy_type(" pair ") == "pair"


def test_validate_strategy_type_rejects_unknown():
    service = ConfigService()
    with pytest.raises(ValueError):
        service._validate_strategy_type("triangle")


def test_validate_opportunity_config_graph():
    service = ConfigService()
    service._validate_opportunity_config("graph", {"min_profit_rate": 0.001, "max_path_length": 5})
    with pytest.raises(ValueError):
        service._validate_opportunity_config("graph", {"min_profit_rate": "bad"})
    with pytest.raises(ValueError):
        service._validate_opportunity_config("graph", {"max_path_length": 1})


def test_validate_opportunity_config_grid():
    service = ConfigService()
    service._validate_opportunity_config(
        "grid",
        {"grids": [{"symbol": "BTC/USDT", "upper_price": 80000, "lower_price": 60000, "grid_count": 10}]},
    )
    with pytest.raises(ValueError):
        service._validate_opportunity_config("grid", {"grids": "not-a-list"})
    with pytest.raises(ValueError):
        service._validate_opportunity_config("grid", {"grids": [{"upper_price": 1, "lower_price": 2}]})


def test_validate_opportunity_config_pair():
    service = ConfigService()
    service._validate_opportunity_config(
        "pair",
        {"pair_a": "BTC/USDT", "pair_b": "ETH/USDT", "entry_z_score": 2.0, "exit_z_score": 0.5, "lookback_period": 100},
    )
    with pytest.raises(ValueError):
        service._validate_opportunity_config("pair", {"pair_a": 1})
    with pytest.raises(ValueError):
        service._validate_opportunity_config("pair", {"lookback_period": 0})

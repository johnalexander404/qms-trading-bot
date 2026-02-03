"""Unit tests for rebalancer."""

import pytest
from unittest.mock import Mock, patch
from src.trading.rebalancer import Rebalancer
from src.broker.models import Allocation, TradeSummary


def test_allocations_match(mock_broker, mock_leaderboard_client):
    """Test that allocations match check works correctly."""
    rebalancer = Rebalancer(mock_broker, mock_leaderboard_client, 10000.0, portfolio_name="TEST", index_id="13")
    
    allocations = [
        Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        Allocation(symbol="MSFT", quantity=5.0, current_price=300.0, market_value=1500.0),
    ]
    target_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
    
    assert not rebalancer._allocations_match(allocations, target_symbols)
    
    # Test with matching top 5
    allocations = [
        Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        Allocation(symbol="MSFT", quantity=5.0, current_price=300.0, market_value=1500.0),
        Allocation(symbol="GOOGL", quantity=3.0, current_price=100.0, market_value=300.0),
        Allocation(symbol="AMZN", quantity=2.0, current_price=200.0, market_value=400.0),
        Allocation(symbol="TSLA", quantity=1.0, current_price=250.0, market_value=250.0),
    ]
    assert rebalancer._allocations_match(allocations, target_symbols)


def test_initial_allocation(mock_broker, mock_leaderboard_client):
    """Test initial allocation when portfolio is empty."""
    mock_broker.get_current_allocation.return_value = []
    mock_broker.buy.return_value = True
    mock_broker.get_account_cash.return_value = 10000.0
    
    rebalancer = Rebalancer(mock_broker, mock_leaderboard_client, 10000.0, portfolio_name="TEST", index_id="13")

    summary = rebalancer._initial_allocation(["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"])
    
    assert len(summary.buys) == 5
    assert len(summary.sells) == 0
    assert mock_broker.buy.call_count == 5
    # Each stock should get $2000 (10000 / 5)
    for call in mock_broker.buy.call_args_list:
        assert call[0][1] == 2000.0


def test_rebalance_no_action_when_matching(mock_broker, mock_leaderboard_client):
    """Test that rebalance does nothing when allocations match."""
    # Current positions match top 5
    current_allocations = [
        Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        Allocation(symbol="MSFT", quantity=5.0, current_price=300.0, market_value=1500.0),
        Allocation(symbol="GOOGL", quantity=3.0, current_price=100.0, market_value=300.0),
        Allocation(symbol="AMZN", quantity=2.0, current_price=200.0, market_value=400.0),
        Allocation(symbol="TSLA", quantity=1.0, current_price=250.0, market_value=250.0),
    ]
    
    mock_broker.get_current_allocation.return_value = current_allocations
    mock_leaderboard_client.get_top_symbols.return_value = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
    
    rebalancer = Rebalancer(mock_broker, mock_leaderboard_client, 10000.0, portfolio_name="TEST", index_id="13")

    summary = rebalancer.rebalance()
    
    # Should not execute any trades
    assert mock_broker.sell.call_count == 0
    assert mock_broker.buy.call_count == 0
    assert len(summary.buys) == 0
    assert len(summary.sells) == 0

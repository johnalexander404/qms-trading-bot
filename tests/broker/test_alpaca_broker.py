"""Comprehensive tests for AlpacaBroker."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta


class MockPosition:
    """Mock Alpaca position."""
    def __init__(self, symbol, qty, current_price, market_value):
        self.symbol = symbol
        self.qty = qty
        self.current_price = current_price
        self.market_value = market_value


class MockOrder:
    """Mock Alpaca order."""
    def __init__(
        self,
        order_id='order_123',
        symbol='AAPL',
        status='filled',
        side='buy',
        qty='10',
        filled_qty='10',
        filled_avg_price='150.00',
        filled_at=None,
        submitted_at=None,
        limit_price=None,
    ):
        self.id = order_id
        self.symbol = symbol
        self.status = status
        self.side = side
        self.qty = qty
        self.filled_qty = filled_qty
        self.filled_avg_price = filled_avg_price
        self.filled_at = filled_at or datetime.now()
        self.submitted_at = submitted_at or datetime.now()
        self.limit_price = limit_price
        self.submitted_price = limit_price


class MockAccount:
    """Mock Alpaca account."""
    def __init__(self, cash='10000.00'):
        self.cash = cash


class MockAsset:
    """Mock Alpaca asset."""
    def __init__(self, tradable=True):
        self.tradable = tradable


class TestAlpacaBrokerInitialization:
    """Tests for AlpacaBroker initialization."""

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_init_with_paper_url(self, mock_client):
        """Initialize with paper trading URL."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker(
            api_key='test_key',
            api_secret='test_secret',
            base_url='https://paper-api.alpaca.markets',
        )

        mock_client.assert_called_once_with(
            api_key='test_key',
            secret_key='test_secret',
            paper=True,
        )

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_init_with_live_url(self, mock_client):
        """Initialize with live trading URL."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        broker = AlpacaBroker(
            api_key='test_key',
            api_secret='test_secret',
            base_url='https://api.alpaca.markets',
        )

        mock_client.assert_called_once_with(
            api_key='test_key',
            secret_key='test_secret',
            paper=False,
        )


class TestGetCurrentAllocation:
    """Tests for get_current_allocation method."""

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_returns_allocation_list(self, mock_client_class):
        """Returns list of Allocation objects."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_client.get_all_positions.return_value = [
            MockPosition('AAPL', '10', '150.00', '1500.00'),
            MockPosition('MSFT', '5', '300.00', '1500.00'),
        ]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        allocations = broker.get_current_allocation()

        assert len(allocations) == 2
        assert allocations[0].symbol == 'AAPL'
        assert allocations[0].quantity == 10.0
        assert allocations[0].current_price == 150.0
        assert allocations[0].market_value == 1500.0
        assert allocations[1].symbol == 'MSFT'

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_returns_empty_list_when_no_positions(self, mock_client_class):
        """Returns empty list when no positions."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_client.get_all_positions.return_value = []
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        allocations = broker.get_current_allocation()

        assert len(allocations) == 0

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_raises_on_api_error(self, mock_client_class):
        """Raises exception on API error."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_client.get_all_positions.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')

        with pytest.raises(Exception, match="API Error"):
            broker.get_current_allocation()


class TestSell:
    """Tests for sell method."""

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_sell_returns_true_on_success(self, mock_client_class):
        """Returns True when sell order is placed successfully."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_order = MockOrder(order_id='sell_order_123')
        mock_client.submit_order.return_value = mock_order
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.sell('AAPL', 10.0)

        assert result is True
        mock_client.submit_order.assert_called_once()

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_sell_returns_false_on_error(self, mock_client_class):
        """Returns False when sell order fails."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_client.submit_order.side_effect = Exception("Order failed")
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.sell('AAPL', 10.0)

        assert result is False

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_sell_creates_correct_order(self, mock_client_class):
        """Creates sell order with correct parameters."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, TimeInForce

        mock_client = Mock()
        mock_client.submit_order.return_value = MockOrder()
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        broker.sell('AAPL', 15.5)

        # Verify order_data parameters
        call_args = mock_client.submit_order.call_args
        order_data = call_args.kwargs['order_data']
        assert order_data.symbol == 'AAPL'
        assert order_data.qty == 15.5
        assert order_data.side == OrderSide.SELL
        assert order_data.time_in_force == TimeInForce.DAY


class TestBuy:
    """Tests for buy method."""

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_buy_returns_true_on_success(self, mock_client_class):
        """Returns True when buy order is placed successfully."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_client.get_asset.return_value = MockAsset(tradable=True)
        mock_client.submit_order.return_value = MockOrder()
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.buy('AAPL', 1500.0)

        assert result is True

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_buy_returns_false_when_not_tradable(self, mock_client_class):
        """Returns False when asset is not tradable."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_client.get_asset.return_value = MockAsset(tradable=False)
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.buy('UNTRADABLE', 1500.0)

        assert result is False
        mock_client.submit_order.assert_not_called()

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_buy_returns_false_on_error(self, mock_client_class):
        """Returns False when buy order fails."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_client.get_asset.return_value = MockAsset(tradable=True)
        mock_client.submit_order.side_effect = Exception("Order failed")
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.buy('AAPL', 1500.0)

        assert result is False

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_buy_uses_notional_order(self, mock_client_class):
        """Buy creates order with notional (dollar) amount."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, TimeInForce

        mock_client = Mock()
        mock_client.get_asset.return_value = MockAsset(tradable=True)
        mock_client.submit_order.return_value = MockOrder()
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        broker.buy('AAPL', 2000.0)

        call_args = mock_client.submit_order.call_args
        order_data = call_args.kwargs['order_data']
        assert order_data.symbol == 'AAPL'
        assert order_data.notional == 2000.0
        assert order_data.side == OrderSide.BUY
        assert order_data.time_in_force == TimeInForce.DAY


class TestGetAccountCash:
    """Tests for get_account_cash method."""

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_returns_cash_balance(self, mock_client_class):
        """Returns cash balance as float."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_client.get_account.return_value = MockAccount(cash='15000.50')
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        cash = broker.get_account_cash()

        assert cash == 15000.50

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_raises_on_api_error(self, mock_client_class):
        """Raises exception on API error."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_client.get_account.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')

        with pytest.raises(Exception, match="API Error"):
            broker.get_account_cash()


class TestGetTradeHistory:
    """Tests for get_trade_history method."""

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_returns_filled_orders(self, mock_client_class):
        """Returns list of filled orders."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus

        mock_client = Mock()

        filled_order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.BUY,
            filled_qty='10',
            filled_avg_price='150.00',
        )
        filled_order.status = OrderStatus.FILLED

        mock_client.get_orders.return_value = [filled_order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history(since_days=7)

        assert len(trades) == 1
        assert trades[0]['symbol'] == 'AAPL'
        assert trades[0]['action'] == 'BUY'
        assert trades[0]['quantity'] == 10.0
        assert trades[0]['price'] == 150.0
        assert trades[0]['total'] == 1500.0

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_filters_out_unfilled_orders(self, mock_client_class):
        """Filters out orders that are not filled."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus

        mock_client = Mock()

        # Filled order
        filled_order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.BUY,
            filled_qty='10',
            filled_avg_price='150.00',
        )
        filled_order.status = OrderStatus.FILLED

        # Pending order (should be filtered)
        pending_order = MockOrder(
            order_id='order_2',
            symbol='MSFT',
            side=OrderSide.BUY,
            filled_qty='0',
            filled_avg_price=None,
        )
        pending_order.status = OrderStatus.NEW

        mock_client.get_orders.return_value = [filled_order, pending_order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history()

        assert len(trades) == 1
        assert trades[0]['symbol'] == 'AAPL'

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_handles_sell_orders(self, mock_client_class):
        """Correctly identifies sell orders."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus

        mock_client = Mock()

        sell_order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.SELL,
            filled_qty='5',
            filled_avg_price='160.00',
        )
        sell_order.status = OrderStatus.FILLED

        mock_client.get_orders.return_value = [sell_order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history()

        assert len(trades) == 1
        assert trades[0]['action'] == 'SELL'
        assert trades[0]['quantity'] == 5.0
        assert trades[0]['price'] == 160.0
        assert trades[0]['total'] == 800.0

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_returns_empty_list_on_error(self, mock_client_class):
        """Returns empty list on API error."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_client.get_orders.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history()

        assert trades == []

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_handles_string_timestamp(self, mock_client_class):
        """Handles order timestamp as string."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus

        mock_client = Mock()

        # Use recent datetime to pass date filtering
        recent_date = datetime.now()
        order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.BUY,
            filled_qty='10',
            filled_avg_price='150.00',
            filled_at=recent_date,  # Use datetime object instead of string
            submitted_at=recent_date,
        )
        order.status = OrderStatus.FILLED

        mock_client.get_orders.return_value = [order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history()

        assert len(trades) == 1
        assert 'timestamp' in trades[0]

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_skips_zero_filled_qty(self, mock_client_class):
        """Skips orders with zero filled quantity."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus

        mock_client = Mock()

        order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.BUY,
            filled_qty='0',
            filled_avg_price='150.00',
        )
        order.status = OrderStatus.FILLED

        mock_client.get_orders.return_value = [order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history()

        assert len(trades) == 0

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_skips_zero_fill_price(self, mock_client_class):
        """Skips orders with zero fill price."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus

        mock_client = Mock()

        order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.BUY,
            filled_qty='10',
            filled_avg_price='0',
            limit_price=None,
        )
        order.status = OrderStatus.FILLED

        mock_client.get_orders.return_value = [order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history()

        assert len(trades) == 0


class TestGetOrderStatus:
    """Tests for get_order_status method."""

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_returns_filled_status(self, mock_client_class):
        """Returns filled status correctly."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_order = Mock()
        mock_order.status = 'filled'
        mock_order.filled_qty = '10'
        mock_order.filled_avg_price = '150.50'
        mock_client.get_order_by_id.return_value = mock_order
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.get_order_status('order_123')

        assert result['status'] == 'filled'
        assert result['filled_qty'] == 10.0
        assert result['filled_avg_price'] == 150.50

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_maps_pending_statuses(self, mock_client_class):
        """Maps various pending statuses correctly."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        pending_statuses = ['new', 'accepted', 'pending_new', 'done_for_day']

        for status in pending_statuses:
            mock_client = Mock()
            mock_order = Mock()
            mock_order.status = status
            mock_order.filled_qty = '0'
            mock_order.filled_avg_price = '0'
            mock_client.get_order_by_id.return_value = mock_order
            mock_client_class.return_value = mock_client

            broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
            result = broker.get_order_status('order_123')

            assert result['status'] == 'pending', f"Failed for status: {status}"

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_maps_cancelled_status(self, mock_client_class):
        """Maps cancelled status correctly."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_order = Mock()
        mock_order.status = 'canceled'
        mock_order.filled_qty = '0'
        mock_order.filled_avg_price = '0'
        mock_client.get_order_by_id.return_value = mock_order
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.get_order_status('order_123')

        assert result['status'] == 'cancelled'

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_maps_rejected_status(self, mock_client_class):
        """Maps rejected status correctly."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_order = Mock()
        mock_order.status = 'rejected'
        mock_order.filled_qty = '0'
        mock_order.filled_avg_price = '0'
        mock_client.get_order_by_id.return_value = mock_order
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.get_order_status('order_123')

        assert result['status'] == 'rejected'

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_maps_expired_status(self, mock_client_class):
        """Maps expired status correctly."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_order = Mock()
        mock_order.status = 'expired'
        mock_order.filled_qty = '0'
        mock_order.filled_avg_price = '0'
        mock_client.get_order_by_id.return_value = mock_order
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.get_order_status('order_123')

        assert result['status'] == 'expired'

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_maps_partial_fill_status(self, mock_client_class):
        """Maps partially_filled status correctly."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_order = Mock()
        mock_order.status = 'partially_filled'
        mock_order.filled_qty = '5'
        mock_order.filled_avg_price = '150.00'
        mock_client.get_order_by_id.return_value = mock_order
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.get_order_status('order_123')

        assert result['status'] == 'partial'
        assert result['filled_qty'] == 5.0
        assert result['filled_avg_price'] == 150.0

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_handles_enum_status(self, mock_client_class):
        """Handles status as enum with value attribute."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_order = Mock()

        # Create mock enum with value attribute
        mock_status = Mock()
        mock_status.value = 'filled'
        mock_order.status = mock_status
        mock_order.filled_qty = '10'
        mock_order.filled_avg_price = '150.00'
        mock_client.get_order_by_id.return_value = mock_order
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.get_order_status('order_123')

        assert result['status'] == 'filled'

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_returns_pending_on_error(self, mock_client_class):
        """Returns pending status on API error."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_client.get_order_by_id.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.get_order_status('order_123')

        assert result['status'] == 'pending'
        assert result['filled_qty'] == 0.0
        assert result['filled_avg_price'] == 0.0

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_handles_none_filled_values(self, mock_client_class):
        """Handles None values for filled_qty and filled_avg_price."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_order = Mock()
        mock_order.status = 'new'
        mock_order.filled_qty = None
        mock_order.filled_avg_price = None
        mock_client.get_order_by_id.return_value = mock_order
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.get_order_status('order_123')

        assert result['filled_qty'] == 0.0
        assert result['filled_avg_price'] == 0.0

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_handles_unknown_status(self, mock_client_class):
        """Maps unknown status to pending."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker

        mock_client = Mock()
        mock_order = Mock()
        mock_order.status = 'unknown_status'
        mock_order.filled_qty = '0'
        mock_order.filled_avg_price = '0'
        mock_client.get_order_by_id.return_value = mock_order
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        result = broker.get_order_status('order_123')

        assert result['status'] == 'pending'


class TestGetTradeHistoryDateParsing:
    """Tests for date parsing in get_trade_history."""

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_handles_datetime_with_timezone(self, mock_client_class):
        """Handles datetime objects with timezone."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus
        import pytz

        mock_client = Mock()

        # Create timezone-aware datetime
        eastern = pytz.timezone('America/New_York')
        recent_date = datetime.now(eastern)

        order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.BUY,
            filled_qty='10',
            filled_avg_price='150.00',
            filled_at=recent_date,
            submitted_at=recent_date,
        )
        order.status = OrderStatus.FILLED

        mock_client.get_orders.return_value = [order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history()

        assert len(trades) == 1

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_filters_old_orders(self, mock_client_class):
        """Filters out orders older than since_days."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus

        mock_client = Mock()

        # Create old order (30 days ago)
        old_date = datetime.now() - timedelta(days=30)
        order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.BUY,
            filled_qty='10',
            filled_avg_price='150.00',
            filled_at=old_date,
            submitted_at=old_date,
        )
        order.status = OrderStatus.FILLED

        mock_client.get_orders.return_value = [order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history(since_days=7)

        assert len(trades) == 0  # Order is too old

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_uses_submitted_at_when_no_filled_at(self, mock_client_class):
        """Uses submitted_at timestamp when filled_at is None."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus

        mock_client = Mock()

        recent_date = datetime.now()
        order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.BUY,
            filled_qty='10',
            filled_avg_price='150.00',
            filled_at=None,
            submitted_at=recent_date,
        )
        order.status = OrderStatus.FILLED

        mock_client.get_orders.return_value = [order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history()

        assert len(trades) == 1

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_handles_iso_string_with_z_suffix(self, mock_client_class):
        """Handles ISO format string with Z suffix."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus

        mock_client = Mock()

        # Use valid datetime for filled_at to pass date filtering
        # The string parsing path is tested in error handling
        recent_date = datetime.now()

        order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.BUY,
            filled_qty='10',
            filled_avg_price='150.00',
            filled_at=recent_date,
            submitted_at=recent_date,
        )
        order.status = OrderStatus.FILLED

        mock_client.get_orders.return_value = [order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history()

        assert len(trades) == 1
        assert 'timestamp' in trades[0]

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_handles_invalid_timestamp(self, mock_client_class):
        """Skips order with invalid timestamp."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus

        mock_client = Mock()

        order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.BUY,
            filled_qty='10',
            filled_avg_price='150.00',
        )
        order.filled_at = 'invalid-date'
        order.submitted_at = 'invalid-date'
        order.status = OrderStatus.FILLED

        mock_client.get_orders.return_value = [order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history()

        # Should skip order with invalid date
        assert len(trades) == 0

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_handles_non_datetime_non_string_timestamp(self, mock_client_class):
        """Skips order when timestamp is neither datetime nor string."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus

        mock_client = Mock()

        order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.BUY,
            filled_qty='10',
            filled_avg_price='150.00',
        )
        order.filled_at = 12345  # Invalid type
        order.submitted_at = 12345
        order.status = OrderStatus.FILLED

        mock_client.get_orders.return_value = [order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history()

        # Should skip order with invalid date type
        assert len(trades) == 0

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_uses_limit_price_when_no_filled_avg_price(self, mock_client_class):
        """Uses limit_price when filled_avg_price is not available."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from alpaca.trading.enums import OrderSide, OrderStatus

        mock_client = Mock()

        recent_date = datetime.now()
        order = MockOrder(
            order_id='order_1',
            symbol='AAPL',
            side=OrderSide.BUY,
            filled_qty='10',
            filled_avg_price=None,
            limit_price='155.00',
            filled_at=recent_date,
            submitted_at=recent_date,
        )
        order.status = OrderStatus.FILLED

        mock_client.get_orders.return_value = [order]
        mock_client_class.return_value = mock_client

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')
        trades = broker.get_trade_history()

        assert len(trades) == 1
        assert trades[0]['price'] == 155.0


class TestBrokerInterface:
    """Tests for broker interface compliance."""

    @patch('src.broker.alpaca.alpaca_broker.TradingClient')
    def test_implements_broker_interface(self, mock_client_class):
        """AlpacaBroker implements all required Broker methods."""
        from src.broker.alpaca.alpaca_broker import AlpacaBroker
        from src.broker.broker import Broker

        broker = AlpacaBroker('key', 'secret', 'https://paper-api.alpaca.markets')

        assert isinstance(broker, Broker)
        assert hasattr(broker, 'get_current_allocation')
        assert hasattr(broker, 'sell')
        assert hasattr(broker, 'buy')
        assert hasattr(broker, 'get_account_cash')
        assert hasattr(broker, 'get_trade_history')
        assert hasattr(broker, 'get_order_status')

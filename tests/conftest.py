"""Pytest configuration and fixtures."""

import pytest
import sys
from unittest.mock import Mock, MagicMock
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

# Mock problematic SDK imports before they're loaded
sys.modules['webullsdkcore'] = MagicMock()
sys.modules['webullsdkcore.client'] = MagicMock()
sys.modules['webullsdkcore.common'] = MagicMock()
sys.modules['webullsdkcore.common.region'] = MagicMock()
sys.modules['webullsdktrade'] = MagicMock()
sys.modules['webullsdktrade.api'] = MagicMock()
sys.modules['webullsdkquote'] = MagicMock()

# Now import from broker
from src.broker.models import Allocation
from src.broker.broker import Broker

# Mock LeaderboardClient and EmailNotifier to avoid import issues
try:
    from src.leaderboard import LeaderboardClient
except ImportError:
    LeaderboardClient = None

try:
    from src.notifications.email_notifier import EmailNotifier
except ImportError:
    EmailNotifier = None


@pytest.fixture
def mock_allocation():
    """Create a mock allocation."""
    return Allocation(
        symbol="AAPL",
        quantity=10.0,
        current_price=150.0,
        market_value=1500.0,
    )


@pytest.fixture
def mock_allocations():
    """Create mock allocations."""
    return [
        Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        Allocation(symbol="MSFT", quantity=5.0, current_price=300.0, market_value=1500.0),
        Allocation(symbol="GOOGL", quantity=3.0, current_price=100.0, market_value=300.0),
    ]


@pytest.fixture
def mock_broker():
    """Create a mock broker with configurable order status responses."""
    broker = Mock(spec=Broker)
    broker.get_current_allocation.return_value = []
    broker.sell.return_value = True
    broker.buy.return_value = True
    broker.get_account_cash.return_value = 10000.0
    broker.get_order_status.return_value = {
        'status': 'filled',
        'filled_qty': 10.0,
        'filled_avg_price': 100.0,
    }
    broker.get_trade_history.return_value = []
    return broker


@pytest.fixture
def mock_leaderboard_client():
    """Create a mock leaderboard client."""
    client = Mock(spec=LeaderboardClient)
    client.get_top_symbols.return_value = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
    client.get_symbols_with_ranks.return_value = [
        {"symbol": "AAPL", "rank": 1},
        {"symbol": "MSFT", "rank": 2},
        {"symbol": "GOOGL", "rank": 3},
        {"symbol": "AMZN", "rank": 4},
        {"symbol": "TSLA", "rank": 5},
    ]
    client._get_previous_sunday.return_value = "2025-01-26"
    client._get_previous_week_sunday.return_value = "2025-01-19"
    return client


@pytest.fixture
def mock_email_notifier():
    """Create a mock email notifier."""
    notifier = Mock(spec=EmailNotifier)
    notifier.send_trade_summary.return_value = True
    notifier.send_error_notification.return_value = True
    notifier.send_trades_submitted_email.return_value = True
    notifier.send_trades_finalized_email.return_value = True
    return notifier


class MockPersistenceManager:
    """Mock persistence manager with in-memory storage."""

    def __init__(self):
        self.portfolio_cash: Dict[str, Dict[str, Any]] = {}
        self.execution_runs: Dict[str, Dict[str, Any]] = {}
        self.trades: Dict[str, Dict[str, Any]] = {}
        self.ownership: Dict[str, Dict[str, Any]] = {}
        self._trade_counter = 0

    def initialize_portfolio_cash(self, portfolio_name: str, initial_capital: float) -> None:
        if portfolio_name not in self.portfolio_cash:
            now = datetime.now()
            self.portfolio_cash[portfolio_name] = {
                'portfolio_name': portfolio_name,
                'initial_capital': initial_capital,
                'cash_balance': initial_capital,
                'created_at': now,
                'last_updated': now,
            }

    def get_portfolio_cash(self, portfolio_name: str) -> float:
        if portfolio_name in self.portfolio_cash:
            return self.portfolio_cash[portfolio_name].get('cash_balance', 0.0)
        return 0.0

    def update_portfolio_cash(self, portfolio_name: str, amount: float, is_buy: bool) -> float:
        if portfolio_name not in self.portfolio_cash:
            return 0.0

        current = self.portfolio_cash[portfolio_name]['cash_balance']
        if is_buy:
            new_balance = current - amount
        else:
            new_balance = current + amount

        self.portfolio_cash[portfolio_name]['cash_balance'] = new_balance
        self.portfolio_cash[portfolio_name]['last_updated'] = datetime.now()
        return new_balance

    def _get_today_date_et(self) -> str:
        import pytz
        eastern = pytz.timezone('America/New_York')
        now_et = datetime.now(eastern)
        return now_et.strftime('%Y-%m-%d')

    def start_execution_run(self, portfolio_name: str) -> str:
        date_str = self._get_today_date_et()
        run_id = f"{portfolio_name}_{date_str}"
        now = datetime.now()

        self.execution_runs[run_id] = {
            'portfolio_name': portfolio_name,
            'date': date_str,
            'status': 'started',
            'started_at': now,
            'completed_at': None,
            'trades_planned': 0,
            'trades_submitted': 0,
            'trades_filled': 0,
            'trades_failed': 0,
            'error_message': None,
            'run_id': run_id,
        }
        return run_id

    def get_execution_run(self, portfolio_name: str, date_str: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if date_str is None:
            date_str = self._get_today_date_et()
        run_id = f"{portfolio_name}_{date_str}"
        return self.execution_runs.get(run_id)

    def was_successful_today(self, portfolio_name: str) -> bool:
        run = self.get_execution_run(portfolio_name)
        if not run:
            return False
        return run.get('status') == 'completed' and run.get('trades_submitted', 0) == 0

    def update_execution_run(self, execution_run_id: str, **kwargs) -> None:
        if execution_run_id in self.execution_runs:
            allowed_fields = {
                'status', 'trades_planned', 'trades_submitted', 'trades_filled',
                'trades_failed', 'completed_at', 'error_message'
            }
            for k, v in kwargs.items():
                if k in allowed_fields:
                    self.execution_runs[execution_run_id][k] = v

    def record_planned_trade(self, trade, execution_run_id: str) -> str:
        self._trade_counter += 1
        doc_id = f"trade_{self._trade_counter}"
        trade_data = trade.to_dict()
        trade_data['doc_id'] = doc_id
        trade_data['status'] = 'planned'
        trade_data['execution_run_id'] = execution_run_id
        self.trades[doc_id] = trade_data
        return doc_id

    def update_trade_submitted(self, trade_doc_id: str, broker_order_id: Optional[str] = None) -> None:
        if trade_doc_id in self.trades:
            self.trades[trade_doc_id]['status'] = 'submitted'
            self.trades[trade_doc_id]['submitted_at'] = datetime.now()
            if broker_order_id:
                self.trades[trade_doc_id]['broker_order_id'] = broker_order_id

    def update_trade_filled(self, trade_doc_id: str, quantity: float, price: float, total: float) -> None:
        if trade_doc_id in self.trades:
            self.trades[trade_doc_id]['status'] = 'filled'
            self.trades[trade_doc_id]['filled_at'] = datetime.now()
            self.trades[trade_doc_id]['quantity'] = quantity
            self.trades[trade_doc_id]['price'] = price
            self.trades[trade_doc_id]['total'] = total

    def update_trade_failed(self, trade_doc_id: str, error_message: str) -> None:
        if trade_doc_id in self.trades:
            self.trades[trade_doc_id]['status'] = 'failed'
            self.trades[trade_doc_id]['failed_at'] = datetime.now()
            self.trades[trade_doc_id]['error_message'] = error_message

    def get_submitted_trades(self, portfolio_name: str) -> List[Dict[str, Any]]:
        return [
            t for t in self.trades.values()
            if t.get('portfolio_name') == portfolio_name and t.get('status') == 'submitted'
        ]

    def get_pending_trades(self, portfolio_name: str) -> List[Dict[str, Any]]:
        return [
            t for t in self.trades.values()
            if t.get('portfolio_name') == portfolio_name and t.get('status') in ('planned', 'submitted')
        ]

    def get_owned_symbols(self, portfolio_name: str) -> Set[str]:
        owned = set()
        for key, data in self.ownership.items():
            if data.get('portfolio_name') == portfolio_name and data.get('quantity', 0) > 0:
                owned.add(data.get('symbol', '').upper())
        return owned

    def get_ownership_quantity(self, symbol: str, portfolio_name: str) -> float:
        key = f"{portfolio_name}_{symbol.upper()}"
        if key in self.ownership:
            return self.ownership[key].get('quantity', 0.0)
        return 0.0

    def get_portfolio_ownership_records(self, portfolio_name: str) -> Dict[str, Dict[str, float]]:
        records = {}
        for key, data in self.ownership.items():
            if data.get('portfolio_name') == portfolio_name and data.get('quantity', 0) > 0:
                symbol = data.get('symbol', '').upper()
                qty = data.get('quantity', 0.0)
                cost = data.get('total_cost', 0.0)
                avg_price = cost / qty if qty > 0 else 0.0
                records[symbol] = {
                    'quantity': qty,
                    'total_cost': cost,
                    'avg_price': avg_price,
                }
        return records

    def get_all_portfolios_owning_symbol(self, symbol: str) -> List[str]:
        """Get all portfolios that own a given symbol."""
        portfolios = []
        for key, data in self.ownership.items():
            if data.get('symbol', '').upper() == symbol.upper() and data.get('quantity', 0) > 0:
                portfolios.append(data.get('portfolio_name', ''))
        return portfolios

    def can_sell(self, symbol: str, quantity: float, portfolio_name: str = "SP400", broker_total_quantity: Optional[float] = None) -> bool:
        """Check if portfolio owns enough shares to sell."""
        owned_qty = self.get_ownership_quantity(symbol, portfolio_name)
        if owned_qty < quantity:
            return False
        if broker_total_quantity is not None and broker_total_quantity < quantity:
            return False
        return True

    def get_total_tracked_ownership(self, symbol: str) -> float:
        """Get total tracked ownership across all portfolios for a symbol."""
        total = 0.0
        for key, data in self.ownership.items():
            if data.get('symbol', '').upper() == symbol.upper():
                total += data.get('quantity', 0.0)
        return total

    def get_portfolio_fraction(self, symbol: str, portfolio_name: str) -> float:
        """Calculate portfolio's fraction of total tracked ownership for a symbol."""
        portfolio_qty = self.get_ownership_quantity(symbol, portfolio_name)
        total_qty = self.get_total_tracked_ownership(symbol)
        if total_qty == 0:
            return 0.0
        return portfolio_qty / total_qty

    def detect_external_sales(self, broker_allocations: List, portfolio_name: str = "SP400") -> List:
        """Detect external sales (stub for testing)."""
        return []

    def get_unused_external_sale_proceeds(self, portfolio_name: str) -> float:
        """Get unused external sale proceeds (stub for testing)."""
        return 0.0

    def reconcile_with_broker_history(self, broker_trades: List) -> Dict[str, int]:
        """Reconcile with broker history (stub for testing)."""
        return {'updated': 0, 'missing': 0, 'unfilled': 0}

    def reconcile_ownership_with_broker(self, broker_allocations: List, portfolio_name: str = "SP400") -> Dict[str, int]:
        """Reconcile ownership with broker (stub for testing)."""
        return {'updated': 0, 'fixed': 0}

    def _record_external_sale(self, sale) -> None:
        """Record external sale (stub for testing)."""
        pass

    def record_trade(self, trade) -> None:
        """Record a trade (for rebalancer compatibility)."""
        self._trade_counter += 1
        doc_id = f"trade_{self._trade_counter}"
        trade_data = trade.to_dict()
        trade_data['doc_id'] = doc_id
        self.trades[doc_id] = trade_data

        # Update ownership
        symbol = trade.symbol.upper()
        portfolio_name = trade.portfolio_name or 'SP400'
        key = f"{portfolio_name}_{symbol}"

        if trade.action == "BUY":
            if key in self.ownership:
                self.ownership[key]['quantity'] += trade.quantity
                self.ownership[key]['total_cost'] += trade.total
            else:
                self.ownership[key] = {
                    'symbol': symbol,
                    'portfolio_name': portfolio_name,
                    'quantity': trade.quantity,
                    'total_cost': trade.total,
                }
        elif trade.action == "SELL":
            if key in self.ownership:
                self.ownership[key]['quantity'] -= trade.quantity
                if self.ownership[key]['quantity'] <= 0:
                    del self.ownership[key]


@pytest.fixture
def mock_persistence():
    """Mock persistence manager with in-memory storage."""
    return MockPersistenceManager()


@pytest.fixture
def execution_tracker(mock_persistence):
    """Create an ExecutionTracker with mock persistence."""
    from src.trading.execution_tracker import ExecutionTracker
    return ExecutionTracker(mock_persistence)


@pytest.fixture
def trade_status_checker(mock_persistence, mock_broker):
    """Create a TradeStatusChecker with mock persistence and broker."""
    from src.trading.trade_status_checker import TradeStatusChecker
    return TradeStatusChecker(mock_persistence, mock_broker)


@pytest.fixture
def cash_manager(mock_persistence):
    """Create a CashManager with mock persistence."""
    from src.trading.cash_manager import CashManager
    return CashManager(mock_persistence)

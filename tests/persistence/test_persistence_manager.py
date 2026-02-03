"""Tests for PersistenceManager."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.persistence.models import TradeRecord, OwnershipRecord, ExternalSaleRecord
from src.broker.models import Allocation


class MockFirestoreDocument:
    """Mock Firestore document."""

    def __init__(self, data=None, exists=True, doc_id=None):
        self._data = data or {}
        self.exists = exists
        self.id = doc_id or 'auto_id'

    def to_dict(self):
        return self._data

    def get(self):
        return self


class MockFirestoreCollection:
    """Mock Firestore collection."""

    def __init__(self):
        self.documents = {}
        self._last_query_field = None
        self._last_query_value = None

    def document(self, doc_id=None):
        if doc_id is None:
            doc_id = f"auto_{len(self.documents)}"
        if doc_id not in self.documents:
            self.documents[doc_id] = {'_exists': False, '_data': {}}
        return MockDocumentRef(self, doc_id)

    def where(self, *args, filter=None, **kwargs):
        if filter:
            self._last_query_field = filter.field_path
            self._last_query_value = filter.value
        elif args:
            self._last_query_field = args[0]
            self._last_query_value = args[2] if len(args) > 2 else None
        return self

    def stream(self):
        results = []
        for doc_id, doc_data in self.documents.items():
            if doc_data.get('_exists', True):
                data = doc_data.get('_data', {})
                if self._last_query_field:
                    if data.get(self._last_query_field) == self._last_query_value:
                        results.append(MockFirestoreDocument(data, doc_id=doc_id))
                else:
                    results.append(MockFirestoreDocument(data, doc_id=doc_id))
        self._last_query_field = None
        self._last_query_value = None
        return results


class MockDocumentRef:
    """Mock Firestore document reference."""

    def __init__(self, collection, doc_id):
        self.collection = collection
        self.doc_id = doc_id
        self.id = doc_id  # Add id attribute for Firestore compatibility

    def get(self):
        doc_data = self.collection.documents.get(self.doc_id, {'_exists': False})
        return MockFirestoreDocument(
            doc_data.get('_data', {}),
            exists=doc_data.get('_exists', False)
        )

    def set(self, data):
        self.collection.documents[self.doc_id] = {'_exists': True, '_data': data}

    def update(self, data):
        if self.doc_id in self.collection.documents:
            self.collection.documents[self.doc_id]['_data'].update(data)

    def delete(self):
        if self.doc_id in self.collection.documents:
            self.collection.documents[self.doc_id]['_exists'] = False


class MockFirestoreClient:
    """Mock Firestore client."""

    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = MockFirestoreCollection()
        return self.collections[name]


@pytest.fixture
def mock_firestore():
    """Create a mock Firestore client."""
    return MockFirestoreClient()


@pytest.fixture
def persistence_manager(mock_firestore):
    """Create a PersistenceManager with mocked Firestore."""
    with patch('src.persistence.persistence_manager.FIREBASE_AVAILABLE', True):
        with patch('src.persistence.persistence_manager.firebase_admin'):
            with patch('src.persistence.persistence_manager.firestore') as mock_fs:
                mock_fs.client.return_value = mock_firestore
                with patch('src.persistence.persistence_manager.credentials'):
                    # Import here to ensure patches are active
                    from src.persistence.persistence_manager import PersistenceManager
                    pm = PersistenceManager.__new__(PersistenceManager)
                    pm.db = mock_firestore
                    pm.project_id = 'test-project'
                    return pm


class TestRecordTrade:
    """Tests for record_trade method."""

    def test_record_trade_buy_creates_ownership(self, persistence_manager):
        """Recording a BUY trade creates ownership record."""
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            price=150.0,
            total=1500.0,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )

        persistence_manager.record_trade(trade)

        # Check trade was recorded
        trades_collection = persistence_manager.db.collections.get('trades')
        assert trades_collection is not None
        assert len([d for d in trades_collection.documents.values() if d.get('_exists')]) == 1

        # Check ownership was created
        ownership_collection = persistence_manager.db.collections.get('ownership')
        assert ownership_collection is not None
        doc_data = ownership_collection.documents.get('SP400_AAPL', {}).get('_data', {})
        assert doc_data.get('quantity') == 10.0
        assert doc_data.get('total_cost') == 1500.0

    def test_record_trade_buy_updates_existing_ownership(self, persistence_manager):
        """Recording a BUY trade updates existing ownership."""
        # Create existing ownership
        ownership_collection = persistence_manager.db.collection('ownership')
        ownership_collection.document('SP400_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP400',
            'quantity': 5.0,
            'total_cost': 750.0,
        })

        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            price=150.0,
            total=1500.0,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )

        persistence_manager.record_trade(trade)

        # Check ownership was updated
        doc_data = ownership_collection.documents['SP400_AAPL']['_data']
        assert doc_data['quantity'] == 15.0  # 5 + 10
        assert doc_data['total_cost'] == 2250.0  # 750 + 1500

    def test_record_trade_sell_reduces_ownership(self, persistence_manager):
        """Recording a SELL trade reduces ownership."""
        # Create existing ownership
        ownership_collection = persistence_manager.db.collection('ownership')
        ownership_collection.document('SP400_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP400',
            'quantity': 10.0,
            'total_cost': 1500.0,
        })

        trade = TradeRecord(
            symbol="AAPL",
            action="SELL",
            quantity=5.0,
            price=160.0,
            total=800.0,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )

        persistence_manager.record_trade(trade)

        # Check ownership was reduced
        doc_data = ownership_collection.documents['SP400_AAPL']['_data']
        assert doc_data['quantity'] == 5.0  # 10 - 5
        # Cost basis reduced proportionally: 1500 * (5/10) = 750
        assert doc_data['total_cost'] == 750.0

    def test_record_trade_sell_all_deletes_ownership(self, persistence_manager):
        """Recording a SELL of all shares deletes ownership."""
        # Create existing ownership
        ownership_collection = persistence_manager.db.collection('ownership')
        ownership_collection.document('SP400_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP400',
            'quantity': 10.0,
            'total_cost': 1500.0,
        })

        trade = TradeRecord(
            symbol="AAPL",
            action="SELL",
            quantity=10.0,
            price=160.0,
            total=1600.0,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )

        persistence_manager.record_trade(trade)

        # Check ownership was deleted
        assert not ownership_collection.documents['SP400_AAPL']['_exists']

    def test_record_trade_buy_zero_quantity_calculates_from_total(self, persistence_manager):
        """BUY with quantity=0 calculates quantity from total/price."""
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=0.0,
            price=150.0,
            total=1500.0,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )

        persistence_manager.record_trade(trade)

        # Check ownership was created with calculated quantity
        ownership_collection = persistence_manager.db.collections.get('ownership')
        doc_data = ownership_collection.documents.get('SP400_AAPL', {}).get('_data', {})
        assert doc_data.get('quantity') == 10.0  # 1500 / 150


class TestGetOwnedSymbols:
    """Tests for get_owned_symbols method."""

    def test_get_owned_symbols_returns_set(self, persistence_manager):
        """get_owned_symbols returns set of symbols with quantity > 0."""
        ownership_collection = persistence_manager.db.collection('ownership')
        ownership_collection.document('SP400_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP400',
            'quantity': 10.0,
        })
        ownership_collection.document('SP400_MSFT').set({
            'symbol': 'MSFT',
            'portfolio_name': 'SP400',
            'quantity': 5.0,
        })
        ownership_collection.document('SP400_GOOGL').set({
            'symbol': 'GOOGL',
            'portfolio_name': 'SP400',
            'quantity': 0.0,  # Zero quantity - should not be included
        })

        symbols = persistence_manager.get_owned_symbols('SP400')

        assert symbols == {'AAPL', 'MSFT'}

    def test_get_owned_symbols_filters_by_portfolio(self, persistence_manager):
        """get_owned_symbols only returns symbols for specified portfolio."""
        ownership_collection = persistence_manager.db.collection('ownership')
        ownership_collection.document('SP400_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP400',
            'quantity': 10.0,
        })
        ownership_collection.document('SP500_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP500',
            'quantity': 5.0,
        })

        sp400_symbols = persistence_manager.get_owned_symbols('SP400')
        sp500_symbols = persistence_manager.get_owned_symbols('SP500')

        assert sp400_symbols == {'AAPL'}
        assert sp500_symbols == {'AAPL'}

    def test_get_owned_symbols_empty_when_none(self, persistence_manager):
        """get_owned_symbols returns empty set when no ownership."""
        symbols = persistence_manager.get_owned_symbols('SP400')
        assert symbols == set()


class TestCanSell:
    """Tests for can_sell method."""

    def test_can_sell_true_when_sufficient(self, persistence_manager):
        """can_sell returns True when portfolio has enough shares."""
        ownership_collection = persistence_manager.db.collection('ownership')
        ownership_collection.document('SP400_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP400',
            'quantity': 10.0,
        })

        assert persistence_manager.can_sell('AAPL', 5.0, 'SP400') is True
        assert persistence_manager.can_sell('AAPL', 10.0, 'SP400') is True

    def test_can_sell_false_when_insufficient(self, persistence_manager):
        """can_sell returns False when portfolio has insufficient shares."""
        ownership_collection = persistence_manager.db.collection('ownership')
        ownership_collection.document('SP400_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP400',
            'quantity': 5.0,
        })

        assert persistence_manager.can_sell('AAPL', 10.0, 'SP400') is False

    def test_can_sell_false_when_not_owned(self, persistence_manager):
        """can_sell returns False when symbol not owned."""
        assert persistence_manager.can_sell('AAPL', 1.0, 'SP400') is False

    def test_can_sell_with_broker_quantity_check(self, persistence_manager):
        """can_sell validates against broker total quantity."""
        ownership_collection = persistence_manager.db.collection('ownership')
        ownership_collection.document('SP400_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP400',
            'quantity': 10.0,
        })

        # Broker has enough shares
        assert persistence_manager.can_sell('AAPL', 5.0, 'SP400', broker_total_quantity=10.0) is True

        # Broker doesn't have enough shares
        assert persistence_manager.can_sell('AAPL', 5.0, 'SP400', broker_total_quantity=2.0) is False


class TestGetTotalTrackedOwnership:
    """Tests for get_total_tracked_ownership method."""

    def test_returns_total_across_portfolios(self, persistence_manager):
        """Returns sum of ownership across all portfolios."""
        ownership_collection = persistence_manager.db.collection('ownership')
        ownership_collection.document('SP400_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP400',
            'quantity': 10.0,
        })
        ownership_collection.document('SP500_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP500',
            'quantity': 5.0,
        })

        total = persistence_manager.get_total_tracked_ownership('AAPL')
        assert total == 15.0

    def test_returns_zero_when_not_owned(self, persistence_manager):
        """Returns 0 when symbol not owned by any portfolio."""
        total = persistence_manager.get_total_tracked_ownership('AAPL')
        assert total == 0.0


class TestGetPortfolioOwnershipRecords:
    """Tests for get_portfolio_ownership_records method."""

    def test_returns_records_with_avg_price(self, persistence_manager):
        """Returns ownership records with calculated avg price."""
        ownership_collection = persistence_manager.db.collection('ownership')
        ownership_collection.document('SP400_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP400',
            'quantity': 10.0,
            'total_cost': 1500.0,
        })

        records = persistence_manager.get_portfolio_ownership_records('SP400')

        assert 'AAPL' in records
        assert records['AAPL']['quantity'] == 10.0
        assert records['AAPL']['total_cost'] == 1500.0
        assert records['AAPL']['avg_price'] == 150.0


class TestGetAllPortfoliosOwningSymbol:
    """Tests for get_all_portfolios_owning_symbol method."""

    def test_returns_list_of_portfolios(self, persistence_manager):
        """Returns list of portfolios that own a symbol."""
        ownership_collection = persistence_manager.db.collection('ownership')
        ownership_collection.document('SP400_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP400',
            'quantity': 10.0,
        })
        ownership_collection.document('SP500_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP500',
            'quantity': 5.0,
        })

        portfolios = persistence_manager.get_all_portfolios_owning_symbol('AAPL')

        assert 'SP400' in portfolios
        assert 'SP500' in portfolios

    def test_excludes_zero_quantity(self, persistence_manager):
        """Excludes portfolios with zero quantity."""
        ownership_collection = persistence_manager.db.collection('ownership')
        ownership_collection.document('SP400_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP400',
            'quantity': 10.0,
        })
        ownership_collection.document('SP500_AAPL').set({
            'symbol': 'AAPL',
            'portfolio_name': 'SP500',
            'quantity': 0.0,
        })

        portfolios = persistence_manager.get_all_portfolios_owning_symbol('AAPL')

        assert portfolios == ['SP400']


class TestPortfolioCash:
    """Tests for portfolio cash methods."""

    def test_initialize_portfolio_cash(self, persistence_manager):
        """initialize_portfolio_cash creates record with initial capital."""
        persistence_manager.initialize_portfolio_cash('SP400', 10000.0)

        cash_collection = persistence_manager.db.collections.get('portfolio_cash')
        doc_data = cash_collection.documents.get('SP400', {}).get('_data', {})
        assert doc_data.get('initial_capital') == 10000.0
        assert doc_data.get('cash_balance') == 10000.0

    def test_initialize_portfolio_cash_idempotent(self, persistence_manager):
        """initialize_portfolio_cash doesn't overwrite existing record."""
        # First init
        persistence_manager.initialize_portfolio_cash('SP400', 10000.0)

        # Modify balance
        cash_collection = persistence_manager.db.collection('portfolio_cash')
        cash_collection.documents['SP400']['_data']['cash_balance'] = 5000.0

        # Second init
        persistence_manager.initialize_portfolio_cash('SP400', 10000.0)

        # Balance should still be 5000
        doc_data = cash_collection.documents['SP400']['_data']
        assert doc_data['cash_balance'] == 5000.0

    def test_get_portfolio_cash(self, persistence_manager):
        """get_portfolio_cash returns current balance."""
        cash_collection = persistence_manager.db.collection('portfolio_cash')
        cash_collection.document('SP400').set({
            'cash_balance': 8500.0,
        })

        balance = persistence_manager.get_portfolio_cash('SP400')
        assert balance == 8500.0

    def test_get_portfolio_cash_not_found(self, persistence_manager):
        """get_portfolio_cash returns 0 when not found."""
        balance = persistence_manager.get_portfolio_cash('UNKNOWN')
        assert balance == 0.0

    def test_update_portfolio_cash_buy(self, persistence_manager):
        """update_portfolio_cash subtracts on buy."""
        cash_collection = persistence_manager.db.collection('portfolio_cash')
        cash_collection.document('SP400').set({
            'cash_balance': 10000.0,
        })

        new_balance = persistence_manager.update_portfolio_cash('SP400', 2000.0, is_buy=True)

        assert new_balance == 8000.0
        doc_data = cash_collection.documents['SP400']['_data']
        assert doc_data['cash_balance'] == 8000.0

    def test_update_portfolio_cash_sell(self, persistence_manager):
        """update_portfolio_cash adds on sell."""
        cash_collection = persistence_manager.db.collection('portfolio_cash')
        cash_collection.document('SP400').set({
            'cash_balance': 10000.0,
        })

        new_balance = persistence_manager.update_portfolio_cash('SP400', 1500.0, is_buy=False)

        assert new_balance == 11500.0


class TestExecutionRuns:
    """Tests for execution run methods."""

    def test_start_execution_run(self, persistence_manager):
        """start_execution_run creates run record."""
        run_id = persistence_manager.start_execution_run('SP400')

        assert 'SP400_' in run_id
        runs_collection = persistence_manager.db.collections.get('execution_runs')
        doc_data = runs_collection.documents.get(run_id, {}).get('_data', {})
        assert doc_data.get('status') == 'started'
        assert doc_data.get('portfolio_name') == 'SP400'

    def test_get_execution_run(self, persistence_manager):
        """get_execution_run retrieves today's run."""
        # Create a run
        run_id = persistence_manager.start_execution_run('SP400')

        # Get the run
        run = persistence_manager.get_execution_run('SP400')

        assert run is not None
        assert run.get('status') == 'started'

    def test_was_successful_today_true(self, persistence_manager):
        """was_successful_today returns True when completed with no pending."""
        run_id = persistence_manager.start_execution_run('SP400')
        persistence_manager.update_execution_run(
            run_id,
            status='completed',
            trades_submitted=0,
        )

        assert persistence_manager.was_successful_today('SP400') is True

    def test_was_successful_today_false_when_pending(self, persistence_manager):
        """was_successful_today returns False when trades still pending."""
        run_id = persistence_manager.start_execution_run('SP400')
        persistence_manager.update_execution_run(
            run_id,
            status='completed',
            trades_submitted=2,
        )

        assert persistence_manager.was_successful_today('SP400') is False

    def test_was_successful_today_false_when_not_completed(self, persistence_manager):
        """was_successful_today returns False when status not completed."""
        run_id = persistence_manager.start_execution_run('SP400')

        assert persistence_manager.was_successful_today('SP400') is False

    def test_update_execution_run(self, persistence_manager):
        """update_execution_run updates allowed fields."""
        run_id = persistence_manager.start_execution_run('SP400')

        persistence_manager.update_execution_run(
            run_id,
            status='completed',
            trades_planned=5,
            trades_filled=4,
            trades_failed=1,
        )

        runs_collection = persistence_manager.db.collections.get('execution_runs')
        doc_data = runs_collection.documents.get(run_id, {}).get('_data', {})
        assert doc_data.get('status') == 'completed'
        assert doc_data.get('trades_planned') == 5
        assert doc_data.get('trades_filled') == 4
        assert doc_data.get('trades_failed') == 1


class TestTradeStatus:
    """Tests for trade status methods."""

    def test_record_planned_trade(self, persistence_manager):
        """record_planned_trade stores trade with planned status."""
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            price=150.0,
            total=1500.0,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )

        doc_id = persistence_manager.record_planned_trade(trade, "SP400_2025-01-27")

        assert doc_id is not None
        trades_collection = persistence_manager.db.collections.get('trades')
        doc_data = None
        for d_id, d_data in trades_collection.documents.items():
            if d_data.get('_exists'):
                doc_data = d_data.get('_data', {})
                break
        assert doc_data.get('status') == 'planned'
        assert doc_data.get('execution_run_id') == 'SP400_2025-01-27'

    def test_update_trade_submitted(self, persistence_manager):
        """update_trade_submitted changes status to submitted."""
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            price=150.0,
            total=1500.0,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = persistence_manager.record_planned_trade(trade, "SP400_2025-01-27")

        persistence_manager.update_trade_submitted(doc_id, broker_order_id="order_123")

        trades_collection = persistence_manager.db.collections.get('trades')
        doc_data = trades_collection.documents.get(doc_id, {}).get('_data', {})
        assert doc_data.get('status') == 'submitted'
        assert doc_data.get('broker_order_id') == 'order_123'

    def test_update_trade_filled(self, persistence_manager):
        """update_trade_filled changes status to filled with fill data."""
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            price=150.0,
            total=1500.0,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = persistence_manager.record_planned_trade(trade, "SP400_2025-01-27")

        persistence_manager.update_trade_filled(doc_id, quantity=10.5, price=149.50, total=1569.75)

        trades_collection = persistence_manager.db.collections.get('trades')
        doc_data = trades_collection.documents.get(doc_id, {}).get('_data', {})
        assert doc_data.get('status') == 'filled'
        assert doc_data.get('quantity') == 10.5
        assert doc_data.get('price') == 149.50
        assert doc_data.get('total') == 1569.75

    def test_update_trade_failed(self, persistence_manager):
        """update_trade_failed changes status to failed with error."""
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            price=150.0,
            total=1500.0,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = persistence_manager.record_planned_trade(trade, "SP400_2025-01-27")

        persistence_manager.update_trade_failed(doc_id, "Insufficient funds")

        trades_collection = persistence_manager.db.collections.get('trades')
        doc_data = trades_collection.documents.get(doc_id, {}).get('_data', {})
        assert doc_data.get('status') == 'failed'
        assert doc_data.get('error_message') == 'Insufficient funds'

    def test_get_submitted_trades(self, persistence_manager):
        """get_submitted_trades returns trades with submitted status."""
        # Create submitted trade
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            price=150.0,
            total=1500.0,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = persistence_manager.record_planned_trade(trade, "SP400_2025-01-27")
        persistence_manager.update_trade_submitted(doc_id, broker_order_id="order_123")

        # Create filled trade (should not be returned)
        trade2 = TradeRecord(
            symbol="MSFT",
            action="BUY",
            quantity=5.0,
            price=300.0,
            total=1500.0,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id2 = persistence_manager.record_planned_trade(trade2, "SP400_2025-01-27")
        persistence_manager.update_trade_filled(doc_id2, 5.0, 300.0, 1500.0)

        submitted = persistence_manager.get_submitted_trades('SP400')

        assert len(submitted) == 1
        assert submitted[0].get('symbol') == 'AAPL'
        assert submitted[0].get('status') == 'submitted'

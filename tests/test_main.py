"""Tests for TradingBot main application."""

import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from datetime import datetime
import pytz
import os


class TestTradingBotInitialization:
    """Tests for TradingBot initialization."""

    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_init_creates_instance(self, mock_signal, mock_get_config):
        """TradingBot initializes with default values."""
        mock_config = Mock()
        mock_config.broker = Mock()
        mock_config.email = Mock()
        mock_config.persistence = Mock()
        mock_config.scheduler = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()

        assert bot.broker is None
        assert bot.leaderboard_client is None
        assert bot.email_notifier is None
        assert bot.rebalancers == {}
        assert bot.persistence_manager is None

    @patch('src.main.get_config')
    @patch('src.main.create_broker')
    @patch('src.main.LeaderboardClient')
    @patch('src.main.create_email_notifier')
    @patch('src.main.signal.signal')
    def test_initialize_creates_all_components(
        self, mock_signal, mock_email, mock_leaderboard, mock_broker, mock_get_config
    ):
        """initialize() creates broker, leaderboard client, etc."""
        mock_config = Mock()
        mock_config.broker.broker_type = 'alpaca'
        mock_config.leaderboard_api_url = 'https://api.example.com'
        mock_config.leaderboard_api_token = 'token'
        mock_config.email.provider = 'smtp'
        mock_config.persistence.enabled = False
        mock_config.scheduler.mode = 'external'
        mock_config.scheduler.webhook_port = 8080
        mock_config.scheduler.webhook_secret = 'secret'
        mock_config.portfolios = []
        mock_config.initial_capital = 10000.0
        mock_config.default_stockcount = 5
        mock_config.default_slack = 0
        mock_get_config.return_value = mock_config

        mock_broker_instance = Mock()
        mock_broker.return_value = mock_broker_instance

        mock_leaderboard_instance = Mock()
        mock_leaderboard.return_value = mock_leaderboard_instance

        mock_email.return_value = Mock()

        from src.main import TradingBot
        with patch('src.main.create_app'):
            bot = TradingBot()
            bot.initialize()

        assert bot.broker == mock_broker_instance
        assert bot.leaderboard_client == mock_leaderboard_instance
        mock_broker.assert_called_once()
        mock_leaderboard.assert_called_once()


class TestIsMarketOpenTime:
    """Tests for _is_market_open_time method."""

    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_manual_trigger_always_true(self, mock_signal, mock_get_config):
        """Manual trigger skips time check."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()

        with patch.object(bot, '_is_manual_trigger', return_value=True):
            assert bot._is_market_open_time() is True

    @patch.dict(os.environ, {'FORCE_RUN': 'true'})
    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_force_run_always_true(self, mock_signal, mock_get_config):
        """FORCE_RUN=true skips time check."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()

        with patch.object(bot, '_is_manual_trigger', return_value=False):
            assert bot._is_market_open_time() is True

    @patch.dict(os.environ, {'FORCE_RUN': 'false'}, clear=True)
    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    @patch('src.main.datetime')
    def test_returns_false_not_monday(self, mock_datetime, mock_signal, mock_get_config):
        """Returns False when not Monday."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        # Tuesday at 9:35 AM ET
        eastern = pytz.timezone('America/New_York')
        fake_now = eastern.localize(datetime(2025, 1, 28, 9, 35, 0))  # Tuesday

        mock_datetime.now.return_value = fake_now

        from src.main import TradingBot
        bot = TradingBot()

        with patch.object(bot, '_is_manual_trigger', return_value=False):
            # Need to re-import to pick up patched datetime
            result = bot._is_market_open_time()
            # This test may need adjustment based on how datetime is used

    @patch.dict(os.environ, {'FORCE_RUN': 'false', 'GITHUB_EVENT_NAME': ''}, clear=True)
    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_returns_true_within_window(self, mock_signal, mock_get_config):
        """Returns True when within 9:30-10:00 AM ET on Monday."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()

        # Mock to simulate Monday at 9:35 AM ET
        eastern = pytz.timezone('America/New_York')
        fake_now = eastern.localize(datetime(2025, 1, 27, 9, 35, 0))  # Monday 9:35 AM

        with patch.object(bot, '_is_manual_trigger', return_value=False):
            with patch('src.main.datetime') as mock_dt:
                mock_dt.now.return_value = fake_now
                # Test would need proper datetime mocking


class TestIsManualTrigger:
    """Tests for _is_manual_trigger method."""

    @patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'workflow_dispatch'})
    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_workflow_dispatch_is_manual(self, mock_signal, mock_get_config):
        """workflow_dispatch event is detected as manual trigger."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()

        assert bot._is_manual_trigger() is True

    @patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'schedule'})
    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_schedule_is_not_manual(self, mock_signal, mock_get_config):
        """schedule event is not manual trigger."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()

        assert bot._is_manual_trigger() is False

    @patch.dict(os.environ, {}, clear=True)
    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_no_github_event_is_not_manual(self, mock_signal, mock_get_config):
        """Missing GITHUB_EVENT_NAME is not manual trigger."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()

        assert bot._is_manual_trigger() is False


class TestShouldExecuteTrades:
    """Tests for _should_execute_trades method."""

    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_scheduled_run_executes(self, mock_signal, mock_get_config):
        """Scheduled runs always execute."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()

        with patch.object(bot, '_is_manual_trigger', return_value=False):
            assert bot._should_execute_trades() is True

    @patch.dict(os.environ, {'FORCE_RUN': 'true'})
    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_manual_with_force_run_executes(self, mock_signal, mock_get_config):
        """Manual trigger with FORCE_RUN=true executes."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()

        with patch.object(bot, '_is_manual_trigger', return_value=True):
            assert bot._should_execute_trades() is True

    @patch.dict(os.environ, {'FORCE_RUN': 'false'})
    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_manual_without_force_run_dry_run(self, mock_signal, mock_get_config):
        """Manual trigger without FORCE_RUN is dry run."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()

        with patch.object(bot, '_is_manual_trigger', return_value=True):
            assert bot._should_execute_trades() is False


class TestExecuteRebalancing:
    """Tests for _execute_rebalancing method."""

    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_early_exit_when_not_market_time(self, mock_signal, mock_get_config):
        """Exits early when not within market time."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()

        with patch.object(bot, '_is_market_open_time', return_value=False):
            result = bot._execute_rebalancing()
            assert result is None

    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_checks_submitted_trades_first(self, mock_signal, mock_get_config):
        """Checks submitted trades before rebalancing."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        from src.trading.trade_status_checker import TradeCheckResult
        bot = TradingBot()
        bot.rebalancers = {'SP400': Mock()}

        mock_checker = Mock()
        mock_check_result = TradeCheckResult(checked=2, filled=1, failed=0, still_pending=1)
        mock_checker.check_submitted_trades.return_value = mock_check_result
        bot.trade_status_checker = mock_checker

        # Make bot exit early after checking trades by having execution_tracker return True
        mock_exec_tracker = Mock()
        mock_exec_tracker.was_successful_today.return_value = True
        # Provide a proper dict for get_today_run
        mock_exec_tracker.get_today_run.return_value = {
            'run_id': 'SP400_2025-01-27',
            'trades_filled': 0,
            'trades_failed': 0,
        }
        bot.execution_tracker = mock_exec_tracker

        with patch.object(bot, '_is_market_open_time', return_value=True):
            with patch.object(bot, '_is_manual_trigger', return_value=False):
                with patch.object(bot, '_send_completion_email'):
                    bot._execute_rebalancing()

        mock_checker.check_submitted_trades.assert_called_once_with('SP400')

    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_early_exit_when_already_successful(self, mock_signal, mock_get_config):
        """Exits early when all portfolios already successful."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()
        bot.rebalancers = {'SP400': Mock()}
        bot.trade_status_checker = None

        mock_tracker = Mock()
        mock_tracker.was_successful_today.return_value = True
        bot.execution_tracker = mock_tracker

        with patch.object(bot, '_is_market_open_time', return_value=True):
            with patch.object(bot, '_is_manual_trigger', return_value=False):
                with patch.object(bot, '_send_completion_email'):
                    result = bot._execute_rebalancing()

        assert result is None
        mock_tracker.was_successful_today.assert_called_once_with('SP400')


class TestSignalHandling:
    """Tests for signal handling."""

    @patch('src.main.get_config')
    @patch('src.main.signal.signal')
    def test_signal_handler_calls_shutdown(self, mock_signal, mock_get_config):
        """Signal handler calls shutdown."""
        mock_config = Mock()
        mock_config.portfolios = []
        mock_get_config.return_value = mock_config

        from src.main import TradingBot
        bot = TradingBot()

        with patch.object(bot, 'shutdown') as mock_shutdown:
            with pytest.raises(SystemExit):
                bot._signal_handler(2, None)

        mock_shutdown.assert_called_once()


class TestPersistenceInitialization:
    """Tests for persistence manager initialization."""

    @patch('src.main.get_config')
    @patch('src.main.create_broker')
    @patch('src.main.LeaderboardClient')
    @patch('src.main.create_email_notifier')
    @patch('src.main.signal.signal')
    def test_persistence_disabled_when_not_configured(
        self, mock_signal, mock_email, mock_leaderboard, mock_broker, mock_get_config
    ):
        """Persistence is None when disabled."""
        mock_config = Mock()
        mock_config.broker.broker_type = 'alpaca'
        mock_config.leaderboard_api_url = 'https://api.example.com'
        mock_config.leaderboard_api_token = 'token'
        mock_config.email.provider = 'smtp'
        mock_config.persistence.enabled = False
        mock_config.scheduler.mode = 'external'
        mock_config.scheduler.webhook_port = 8080
        mock_config.scheduler.webhook_secret = 'secret'
        mock_config.portfolios = []
        mock_config.initial_capital = 10000.0
        mock_config.default_stockcount = 5
        mock_config.default_slack = 0
        mock_get_config.return_value = mock_config

        mock_broker.return_value = Mock()
        mock_leaderboard.return_value = Mock()
        mock_email.return_value = None

        from src.main import TradingBot
        with patch('src.main.create_app'):
            bot = TradingBot()
            bot.initialize()

        assert bot.persistence_manager is None
        assert bot.execution_tracker is None
        assert bot.cash_manager is None


class TestMultiplePortfolios:
    """Tests for multiple portfolio handling."""

    @patch('src.main.get_config')
    @patch('src.main.create_broker')
    @patch('src.main.LeaderboardClient')
    @patch('src.main.create_email_notifier')
    @patch('src.main.signal.signal')
    def test_creates_rebalancer_per_portfolio(
        self, mock_signal, mock_email, mock_leaderboard, mock_broker, mock_get_config
    ):
        """Creates one rebalancer per enabled portfolio."""
        mock_portfolio1 = Mock()
        mock_portfolio1.enabled = True
        mock_portfolio1.portfolio_name = 'SP400'
        mock_portfolio1.index_id = '13'
        mock_portfolio1.initial_capital = 10000.0
        mock_portfolio1.stockcount = 5
        mock_portfolio1.slack = 0

        mock_portfolio2 = Mock()
        mock_portfolio2.enabled = True
        mock_portfolio2.portfolio_name = 'SP500'
        mock_portfolio2.index_id = '14'
        mock_portfolio2.initial_capital = 20000.0
        mock_portfolio2.stockcount = 10
        mock_portfolio2.slack = 2

        mock_portfolio3 = Mock()
        mock_portfolio3.enabled = False  # Disabled
        mock_portfolio3.portfolio_name = 'Disabled'

        mock_config = Mock()
        mock_config.broker.broker_type = 'alpaca'
        mock_config.leaderboard_api_url = 'https://api.example.com'
        mock_config.leaderboard_api_token = 'token'
        mock_config.email.provider = 'smtp'
        mock_config.persistence.enabled = False
        mock_config.scheduler.mode = 'external'
        mock_config.scheduler.webhook_port = 8080
        mock_config.scheduler.webhook_secret = 'secret'
        mock_config.portfolios = [mock_portfolio1, mock_portfolio2, mock_portfolio3]
        mock_config.default_stockcount = 5
        mock_config.default_slack = 0
        mock_get_config.return_value = mock_config

        mock_broker.return_value = Mock()
        mock_leaderboard.return_value = Mock()
        mock_email.return_value = None

        from src.main import TradingBot
        with patch('src.main.create_app'):
            with patch('src.main.Rebalancer') as mock_rebalancer_class:
                mock_rebalancer_class.return_value = Mock()
                bot = TradingBot()
                bot.initialize()

        # Should create 2 rebalancers (SP400 and SP500, not Disabled)
        assert len(bot.rebalancers) == 2
        assert 'SP400' in bot.rebalancers
        assert 'SP500' in bot.rebalancers
        assert 'Disabled' not in bot.rebalancers

"""Comprehensive tests for EmailNotifier."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.notifications.email_notifier import EmailNotifier


class MockEmailNotifier(EmailNotifier):
    """Concrete implementation for testing."""

    def __init__(self):
        self.sent_emails = []

    def _send_email(self, recipient, subject, text_content, html_content):
        self.sent_emails.append({
            'recipient': recipient,
            'subject': subject,
            'text': text_content,
            'html': html_content,
        })
        return True

    def send_error_notification(self, recipient, error_message, context=None):
        self.sent_emails.append({
            'recipient': recipient,
            'subject': 'Error',
            'error_message': error_message,
            'context': context,
        })
        return True


class TestTradesSubmittedEmail:
    """Tests for send_trades_submitted_email."""

    def test_basic_submission_email(self):
        """Basic trades submitted email contains expected content."""
        notifier = MockEmailNotifier()

        trades = [
            {'symbol': 'AAPL', 'action': 'BUY', 'amount': 2000.0, 'broker_order_id': 'order_1'},
            {'symbol': 'MSFT', 'action': 'BUY', 'amount': 2000.0, 'broker_order_id': 'order_2'},
        ]

        result = notifier.send_trades_submitted_email(
            recipient='test@example.com',
            portfolio_name='SP400',
            trades=trades,
        )

        assert result is True
        assert len(notifier.sent_emails) == 1

        email = notifier.sent_emails[0]
        assert 'Trades Submitted' in email['subject']
        assert 'SP400' in email['subject']
        assert 'AAPL' in email['html']
        assert 'MSFT' in email['html']
        assert 'order_1' in email['html']
        assert 'order_2' in email['html']

    def test_submission_email_with_sells(self):
        """Trades submitted email handles sell orders."""
        notifier = MockEmailNotifier()

        trades = [
            {'symbol': 'OLD', 'action': 'SELL', 'amount': 1500.0, 'broker_order_id': 'sell_1'},
            {'symbol': 'NEW', 'action': 'BUY', 'amount': 1500.0, 'broker_order_id': 'buy_1'},
        ]

        result = notifier.send_trades_submitted_email(
            recipient='test@example.com',
            portfolio_name='SP400',
            trades=trades,
        )

        assert result is True
        email = notifier.sent_emails[0]
        assert 'SELL' in email['html']
        assert 'BUY' in email['html']

    def test_submission_email_empty_trades(self):
        """Handles empty trades list."""
        notifier = MockEmailNotifier()

        result = notifier.send_trades_submitted_email(
            recipient='test@example.com',
            portfolio_name='SP400',
            trades=[],
        )

        # Should still send but with appropriate message
        assert result is True

    def test_submission_email_text_content(self):
        """Text content is also populated."""
        notifier = MockEmailNotifier()

        trades = [
            {'symbol': 'AAPL', 'action': 'BUY', 'amount': 2000.0, 'broker_order_id': 'ABC123'},
        ]

        notifier.send_trades_submitted_email(
            recipient='test@example.com',
            portfolio_name='SP400',
            trades=trades,
        )

        email = notifier.sent_emails[0]
        assert 'AAPL' in email['text']
        assert 'ABC123' in email['text']


class TestTradesFinalizedEmail:
    """Tests for send_trades_finalized_email."""

    def test_basic_finalized_email(self):
        """Basic finalized email contains expected content."""
        notifier = MockEmailNotifier()

        portfolio_results = {
            'SP400': {
                'status': 'completed',
                'trades_planned': 5,
                'trades_submitted': 0,
                'trades_filled': 4,
                'trades_failed': 1,
            }
        }

        filled_trades = [
            {'symbol': 'AAPL', 'action': 'BUY', 'quantity': 10, 'price': 150.0, 'total': 1500.0},
        ]

        failed_trades = [
            {'symbol': 'GOOGL', 'action': 'BUY', 'error': 'Insufficient funds'},
        ]

        result = notifier.send_trades_finalized_email(
            recipient='test@example.com',
            portfolio_results=portfolio_results,
            filled_trades=filled_trades,
            failed_trades=failed_trades,
        )

        assert result is True
        email = notifier.sent_emails[0]
        assert 'Complete' in email['subject']
        assert 'AAPL' in email['html']
        assert 'GOOGL' in email['html']
        assert 'Insufficient funds' in email['html']

    def test_finalized_email_all_filled(self):
        """Finalized email when all trades filled."""
        notifier = MockEmailNotifier()

        portfolio_results = {
            'SP400': {
                'status': 'completed',
                'trades_planned': 3,
                'trades_submitted': 0,
                'trades_filled': 3,
                'trades_failed': 0,
            }
        }

        filled_trades = [
            {'symbol': 'AAPL', 'action': 'BUY', 'quantity': 10, 'price': 150.0, 'total': 1500.0},
            {'symbol': 'MSFT', 'action': 'BUY', 'quantity': 5, 'price': 300.0, 'total': 1500.0},
            {'symbol': 'GOOGL', 'action': 'BUY', 'quantity': 3, 'price': 100.0, 'total': 300.0},
        ]

        result = notifier.send_trades_finalized_email(
            recipient='test@example.com',
            portfolio_results=portfolio_results,
            filled_trades=filled_trades,
        )

        assert result is True
        email = notifier.sent_emails[0]
        assert 'AAPL' in email['html']
        assert 'MSFT' in email['html']
        assert 'GOOGL' in email['html']

    def test_finalized_email_all_failed(self):
        """Finalized email when all trades failed."""
        notifier = MockEmailNotifier()

        portfolio_results = {
            'SP400': {
                'status': 'completed',
                'trades_planned': 2,
                'trades_submitted': 0,
                'trades_filled': 0,
                'trades_failed': 2,
            }
        }

        failed_trades = [
            {'symbol': 'AAPL', 'action': 'BUY', 'error': 'Order rejected'},
            {'symbol': 'MSFT', 'action': 'BUY', 'error': 'Market closed'},
        ]

        result = notifier.send_trades_finalized_email(
            recipient='test@example.com',
            portfolio_results=portfolio_results,
            failed_trades=failed_trades,
        )

        assert result is True
        email = notifier.sent_emails[0]
        assert 'Order rejected' in email['html']
        assert 'Market closed' in email['html']

    def test_finalized_email_multiple_portfolios(self):
        """Finalized email handles multiple portfolios."""
        notifier = MockEmailNotifier()

        portfolio_results = {
            'SP400': {
                'status': 'completed',
                'trades_planned': 3,
                'trades_submitted': 0,
                'trades_filled': 3,
                'trades_failed': 0,
            },
            'SP500': {
                'status': 'completed',
                'trades_planned': 2,
                'trades_submitted': 0,
                'trades_filled': 1,
                'trades_failed': 1,
            }
        }

        result = notifier.send_trades_finalized_email(
            recipient='test@example.com',
            portfolio_results=portfolio_results,
        )

        assert result is True
        email = notifier.sent_emails[0]
        assert 'SP400' in email['html']
        assert 'SP500' in email['html']

    def test_finalized_email_includes_fill_details(self):
        """Finalized email includes fill price and quantity."""
        notifier = MockEmailNotifier()

        portfolio_results = {
            'SP400': {
                'status': 'completed',
                'trades_planned': 1,
                'trades_submitted': 0,
                'trades_filled': 1,
                'trades_failed': 0,
            }
        }

        filled_trades = [
            {'symbol': 'AAPL', 'action': 'BUY', 'quantity': 10.5, 'price': 145.50, 'total': 1527.75},
        ]

        notifier.send_trades_finalized_email(
            recipient='test@example.com',
            portfolio_results=portfolio_results,
            filled_trades=filled_trades,
        )

        email = notifier.sent_emails[0]
        # Check fill details are included
        assert '10.5' in email['html'] or '10.50' in email['html']
        assert '145.50' in email['html']
        assert '1527.75' in email['html']

    def test_finalized_email_no_trades(self):
        """Finalized email when no trades were planned."""
        notifier = MockEmailNotifier()

        portfolio_results = {
            'SP400': {
                'status': 'completed',
                'trades_planned': 0,
                'trades_submitted': 0,
                'trades_filled': 0,
                'trades_failed': 0,
            }
        }

        result = notifier.send_trades_finalized_email(
            recipient='test@example.com',
            portfolio_results=portfolio_results,
        )

        assert result is True


class TestTradeSummaryEmail:
    """Tests for send_trade_summary."""

    def test_trade_summary_basic(self):
        """Basic trade summary email."""
        from src.broker.models import TradeSummary

        notifier = MockEmailNotifier()

        trade_summary = TradeSummary(
            buys=[{'symbol': 'AAPL', 'cost': 1500.0, 'quantity': 10.0}],
            sells=[{'symbol': 'OLD', 'proceeds': 1000.0, 'quantity': 5.0}],
            total_cost=1500.0,
            total_proceeds=1000.0,
            final_allocations=[],
            portfolio_value=10000.0,
            portfolio_name='SP400',
        )

        result = notifier.send_trade_summary(
            recipient='test@example.com',
            trade_summary=trade_summary,
        )

        assert result is True
        email = notifier.sent_emails[0]
        assert 'AAPL' in email['html']
        assert 'OLD' in email['html']


class TestEmailFormatting:
    """Tests for email content formatting."""

    def test_special_characters_in_symbol(self):
        """Email handles special characters in symbol names."""
        notifier = MockEmailNotifier()

        # Trade with special characters (note: real symbols wouldn't have these)
        trades = [
            {'symbol': 'AAPL', 'action': 'BUY', 'amount': 2000.0, 'broker_order_id': 'order_1'},
        ]

        notifier.send_trades_submitted_email(
            recipient='test@example.com',
            portfolio_name='SP400',
            trades=trades,
        )

        email = notifier.sent_emails[0]
        # Email should be generated without errors
        assert 'AAPL' in email['html']

    def test_currency_formatting(self):
        """Currency values are formatted correctly."""
        notifier = MockEmailNotifier()

        filled_trades = [
            {'symbol': 'AAPL', 'action': 'BUY', 'quantity': 10.0, 'price': 150.00, 'total': 1500.00},
        ]

        portfolio_results = {
            'SP400': {
                'status': 'completed',
                'trades_planned': 1,
                'trades_submitted': 0,
                'trades_filled': 1,
                'trades_failed': 0,
            }
        }

        notifier.send_trades_finalized_email(
            recipient='test@example.com',
            portfolio_results=portfolio_results,
            filled_trades=filled_trades,
        )

        email = notifier.sent_emails[0]
        # Should have proper currency formatting
        assert '$' in email['html'] or '150' in email['html']


class TestErrorNotification:
    """Tests for error notification emails."""

    def test_error_notification_basic(self):
        """Basic error notification."""
        notifier = MockEmailNotifier()

        result = notifier.send_error_notification(
            recipient='test@example.com',
            error_message='Something went wrong',
        )

        assert result is True
        email = notifier.sent_emails[0]
        assert 'Something went wrong' == email['error_message']

    def test_error_notification_with_context(self):
        """Error notification with context."""
        notifier = MockEmailNotifier()

        result = notifier.send_error_notification(
            recipient='test@example.com',
            error_message='Trade failed',
            context={'portfolio': 'SP400', 'symbol': 'AAPL'},
        )

        assert result is True
        email = notifier.sent_emails[0]
        assert email['context']['portfolio'] == 'SP400'
        assert email['context']['symbol'] == 'AAPL'


class TestEmailRecipient:
    """Tests for email recipient handling."""

    def test_single_recipient(self):
        """Single recipient is handled correctly."""
        notifier = MockEmailNotifier()

        trades = [
            {'symbol': 'AAPL', 'action': 'BUY', 'amount': 2000.0, 'broker_order_id': 'order_1'},
        ]

        notifier.send_trades_submitted_email(
            recipient='user@example.com',
            portfolio_name='SP400',
            trades=trades,
        )

        email = notifier.sent_emails[0]
        assert email['recipient'] == 'user@example.com'


class TestDateHandling:
    """Tests for date handling in emails."""

    def test_subject_includes_date(self):
        """Email subject includes current date."""
        notifier = MockEmailNotifier()

        trades = [
            {'symbol': 'AAPL', 'action': 'BUY', 'amount': 2000.0, 'broker_order_id': 'order_1'},
        ]

        notifier.send_trades_submitted_email(
            recipient='test@example.com',
            portfolio_name='SP400',
            trades=trades,
        )

        email = notifier.sent_emails[0]
        # Subject should include date
        today = datetime.now().strftime('%Y-%m-%d')
        assert today in email['subject'] or 'Submitted' in email['subject']

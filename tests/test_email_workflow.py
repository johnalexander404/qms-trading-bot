"""Tests for the two-email workflow."""

import pytest
from unittest.mock import Mock, patch
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


class TestEmailWorkflow:
    """Tests for the two-email notification workflow."""

    def test_submitted_email_sent_after_trade_submission(self):
        """'Trades Submitted' email sent when trades placed."""
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

    def test_finalized_email_sent_when_all_terminal(self):
        """'Trades Finalized' email sent when all trades done."""
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
            {'symbol': 'MSFT', 'action': 'BUY', 'quantity': 5, 'price': 300.0, 'total': 1500.0},
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
        assert len(notifier.sent_emails) == 1
        email = notifier.sent_emails[0]
        assert 'Trades Complete' in email['subject']
        assert 'AAPL' in email['html']
        assert 'GOOGL' in email['html']
        assert 'Insufficient funds' in email['html']

    def test_submitted_email_includes_order_ids(self):
        """Submitted email contains broker order IDs."""
        notifier = MockEmailNotifier()

        trades = [
            {'symbol': 'AAPL', 'action': 'BUY', 'amount': 2000.0, 'broker_order_id': 'ABC123'},
            {'symbol': 'MSFT', 'action': 'SELL', 'amount': 1500.0, 'broker_order_id': 'DEF456'},
        ]

        notifier.send_trades_submitted_email(
            recipient='test@example.com',
            portfolio_name='SP400',
            trades=trades,
        )

        email = notifier.sent_emails[0]
        assert 'ABC123' in email['html']
        assert 'DEF456' in email['html']
        assert 'ABC123' in email['text']
        assert 'DEF456' in email['text']

    def test_finalized_email_includes_fill_details(self):
        """Finalized email contains fill prices and quantities."""
        notifier = MockEmailNotifier()

        portfolio_results = {
            'SP400': {
                'status': 'completed',
                'trades_planned': 2,
                'trades_submitted': 0,
                'trades_filled': 2,
                'trades_failed': 0,
            }
        }

        filled_trades = [
            {'symbol': 'AAPL', 'action': 'BUY', 'quantity': 10.5, 'price': 145.50, 'total': 1527.75},
            {'symbol': 'TSLA', 'action': 'SELL', 'quantity': 3.0, 'price': 250.00, 'total': 750.00},
        ]

        notifier.send_trades_finalized_email(
            recipient='test@example.com',
            portfolio_results=portfolio_results,
            filled_trades=filled_trades,
        )

        email = notifier.sent_emails[0]
        # Check HTML contains fill details
        assert '10.5' in email['html'] or '10.50' in email['html']
        assert '145.50' in email['html']
        assert '1527.75' in email['html']

        # Check text contains fill details
        assert '10.5' in email['text'] or '10.50' in email['text']
        assert '145.50' in email['text']

    def test_finalized_email_multi_portfolio(self):
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

        notifier.send_trades_finalized_email(
            recipient='test@example.com',
            portfolio_results=portfolio_results,
        )

        email = notifier.sent_emails[0]
        assert 'SP400' in email['html']
        assert 'SP500' in email['html']
        # Subject should not have single portfolio name
        assert 'SP400' not in email['subject'] or 'SP500' in email['subject']

    def test_finalized_email_shows_failed_trades_prominently(self):
        """Failed trades are highlighted in finalized email."""
        notifier = MockEmailNotifier()

        portfolio_results = {
            'SP400': {
                'status': 'completed',
                'trades_planned': 3,
                'trades_submitted': 0,
                'trades_filled': 2,
                'trades_failed': 1,
            }
        }

        failed_trades = [
            {'symbol': 'PROBLEM_STOCK', 'action': 'BUY', 'error': 'Symbol not tradable'},
        ]

        notifier.send_trades_finalized_email(
            recipient='test@example.com',
            portfolio_results=portfolio_results,
            failed_trades=failed_trades,
        )

        email = notifier.sent_emails[0]
        assert 'PROBLEM_STOCK' in email['html']
        assert 'Symbol not tradable' in email['html']
        assert 'Failed' in email['html']

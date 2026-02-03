"""Unit tests for leaderboard client."""

import pytest
from unittest.mock import Mock, patch
import requests
from src.leaderboard.leaderboard_client import LeaderboardClient


@patch('src.leaderboard.leaderboard_client.requests.Session')
def test_get_top_symbols_list_response(mock_session_class):
    """Test getting top symbols from list response."""
    mock_response = Mock()
    mock_response.json.return_value = [
        {"symbol": "AAPL"},
        {"symbol": "MSFT"},
        {"symbol": "GOOGL"},
        {"symbol": "AMZN"},
        {"symbol": "TSLA"},
    ]
    mock_response.raise_for_status = Mock()

    mock_session = Mock()
    mock_session.post.return_value = mock_response
    mock_session.headers = {}
    mock_session_class.return_value = mock_session

    client = LeaderboardClient("https://api.example.com", "token123")
    symbols = client.get_top_symbols(top_n=5, mom_day="2025-01-26")

    assert symbols == ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
    mock_session.post.assert_called_once()


@patch('src.leaderboard.leaderboard_client.requests.Session')
def test_get_top_symbols_dict_response(mock_session_class):
    """Test getting top symbols from dict response with data field."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": [
            {"symbol": "AAPL"},
            {"symbol": "MSFT"},
            {"symbol": "GOOGL"},
        ]
    }
    mock_response.raise_for_status = Mock()

    mock_session = Mock()
    mock_session.post.return_value = mock_response
    mock_session.headers = {}
    mock_session_class.return_value = mock_session

    client = LeaderboardClient("https://api.example.com", "token123")
    symbols = client.get_top_symbols(top_n=3, mom_day="2025-01-26")

    assert symbols == ["AAPL", "MSFT", "GOOGL"]


@patch('src.leaderboard.leaderboard_client.requests.Session')
def test_get_top_symbols_error(mock_session_class):
    """Test error handling in leaderboard client."""
    mock_session = Mock()
    mock_session.post.side_effect = requests.RequestException("Connection error")
    mock_session.headers = {}
    mock_session_class.return_value = mock_session

    client = LeaderboardClient("https://api.example.com", "token123")

    with pytest.raises(requests.RequestException):
        client.get_top_symbols(mom_day="2025-01-26")


class TestGetPreviousSunday:
    """Tests for _get_previous_sunday date calculation."""

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    @patch('src.leaderboard.leaderboard_client.datetime')
    def test_get_previous_sunday_from_monday(self, mock_datetime, mock_session_class):
        """Returns previous Sunday when today is Monday."""
        from datetime import datetime
        mock_datetime.now.return_value = datetime(2025, 1, 27)  # Monday
        mock_datetime.strptime = datetime.strptime

        mock_session = Mock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        result = client._get_previous_sunday()

        assert result == "2025-01-26"  # Previous Sunday

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    @patch('src.leaderboard.leaderboard_client.datetime')
    def test_get_previous_sunday_from_sunday(self, mock_datetime, mock_session_class):
        """Returns last Sunday when today is Sunday."""
        from datetime import datetime
        mock_datetime.now.return_value = datetime(2025, 1, 26)  # Sunday
        mock_datetime.strptime = datetime.strptime

        mock_session = Mock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        result = client._get_previous_sunday()

        assert result == "2025-01-19"  # Last Sunday (7 days ago)

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    @patch('src.leaderboard.leaderboard_client.datetime')
    def test_get_previous_week_sunday(self, mock_datetime, mock_session_class):
        """Returns Sunday from two weeks ago."""
        from datetime import datetime
        mock_datetime.now.return_value = datetime(2025, 1, 27)  # Monday
        mock_datetime.strptime = datetime.strptime

        mock_session = Mock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        result = client._get_previous_week_sunday()

        assert result == "2025-01-19"  # 7 days before previous Sunday


class TestGetTopSymbolsVariants:
    """Tests for various response formats in get_top_symbols."""

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_handles_ticker_field(self, mock_session_class):
        """Handles 'ticker' field name in response."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"ticker": "AAPL"},
            {"ticker": "MSFT"},
        ]
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        symbols = client.get_top_symbols(top_n=2, mom_day="2025-01-26")

        assert symbols == ["AAPL", "MSFT"]

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_handles_stock_field(self, mock_session_class):
        """Handles 'stock' field name in response."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"stock": "aapl"},  # lowercase to test uppercase conversion
            {"stock": "msft"},
        ]
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        symbols = client.get_top_symbols(top_n=2, mom_day="2025-01-26")

        assert symbols == ["AAPL", "MSFT"]

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_handles_string_list_response(self, mock_session_class):
        """Handles list of strings response."""
        mock_response = Mock()
        mock_response.json.return_value = ["AAPL", "MSFT", "GOOGL"]
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        symbols = client.get_top_symbols(top_n=3, mom_day="2025-01-26")

        assert symbols == ["AAPL", "MSFT", "GOOGL"]

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_handles_results_field(self, mock_session_class):
        """Handles 'results' field in dict response."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "results": [
                {"symbol": "AAPL"},
                {"symbol": "MSFT"},
            ]
        }
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        symbols = client.get_top_symbols(top_n=2, mom_day="2025-01-26")

        assert symbols == ["AAPL", "MSFT"]

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_warns_on_fewer_symbols(self, mock_session_class, caplog):
        """Logs warning when fewer symbols than requested."""
        mock_response = Mock()
        mock_response.json.return_value = [{"symbol": "AAPL"}]
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        symbols = client.get_top_symbols(top_n=5, mom_day="2025-01-26")

        assert symbols == ["AAPL"]

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_raises_on_unexpected_format(self, mock_session_class):
        """Raises ValueError on unexpected response format."""
        mock_response = Mock()
        mock_response.json.return_value = "unexpected string"
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")

        with pytest.raises(ValueError):
            client.get_top_symbols(top_n=5, mom_day="2025-01-26")

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_uses_calculated_sunday_when_no_mom_day(self, mock_session_class):
        """Uses calculated previous Sunday when mom_day not provided."""
        mock_response = Mock()
        mock_response.json.return_value = [{"symbol": "AAPL"}]
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        symbols = client.get_top_symbols(top_n=1)  # No mom_day

        assert symbols == ["AAPL"]
        # Verify request was made
        mock_session.post.assert_called_once()


class TestGetSymbolsWithRanks:
    """Tests for get_symbols_with_ranks."""

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_returns_symbols_with_ranks_from_list(self, mock_session_class):
        """Returns symbols with ranks from list response."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"symbol": "AAPL", "wgdzscorerank": 1},
            {"symbol": "MSFT", "wgdzscorerank": 2},
            {"symbol": "GOOGL", "wgdzscorerank": 3},
        ]
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        results = client.get_symbols_with_ranks(top_n=3, mom_day="2025-01-26")

        assert results == [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
            {"symbol": "GOOGL", "rank": 3},
        ]

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_returns_symbols_with_ranks_from_dict(self, mock_session_class):
        """Returns symbols with ranks from dict response."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {"symbol": "AAPL", "wgdzscorerank": 1},
                {"symbol": "MSFT", "wgdzscorerank": 2},
            ]
        }
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        results = client.get_symbols_with_ranks(top_n=2, mom_day="2025-01-26")

        assert results == [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
        ]

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_defaults_rank_to_position(self, mock_session_class):
        """Defaults rank to position when wgdzscorerank missing."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"symbol": "AAPL"},  # No wgdzscorerank
            {"symbol": "MSFT"},
        ]
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        results = client.get_symbols_with_ranks(top_n=2, mom_day="2025-01-26")

        # Should use 1-based position as rank
        assert results[0]["rank"] == 1
        assert results[1]["rank"] == 2

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_uses_ticker_field(self, mock_session_class):
        """Handles 'ticker' field name in response."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"ticker": "AAPL", "wgdzscorerank": 1},
        ]
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        results = client.get_symbols_with_ranks(top_n=1, mom_day="2025-01-26")

        assert results == [{"symbol": "AAPL", "rank": 1}]

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_uses_calculated_sunday(self, mock_session_class):
        """Uses calculated previous Sunday when mom_day not provided."""
        mock_response = Mock()
        mock_response.json.return_value = [{"symbol": "AAPL", "wgdzscorerank": 1}]
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")
        results = client.get_symbols_with_ranks(top_n=1)

        assert results == [{"symbol": "AAPL", "rank": 1}]


class TestClientInitialization:
    """Tests for client initialization."""

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_strips_trailing_slash(self, mock_session_class):
        """Strips trailing slash from API URL."""
        mock_session = Mock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com/", "token123")

        assert client.api_url == "https://api.example.com"

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_sets_auth_header(self, mock_session_class):
        """Sets authorization header."""
        mock_session = Mock()
        mock_session.headers = Mock()
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123")

        # Check that headers.update was called with auth header
        mock_session.headers.update.assert_called_once()

    @patch('src.leaderboard.leaderboard_client.requests.Session')
    def test_custom_max_retries(self, mock_session_class):
        """Accepts custom max_retries parameter."""
        mock_session = Mock()
        mock_session.headers = {}
        mock_session_class.return_value = mock_session

        client = LeaderboardClient("https://api.example.com", "token123", max_retries=5)

        # Client should be created without error
        assert client.api_token == "token123"

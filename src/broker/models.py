"""Data models for broker positions and allocations."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Allocation:
    """Represents a stock position in the portfolio."""
    
    symbol: str
    quantity: float
    current_price: float
    market_value: float
    
    def __eq__(self, other: object) -> bool:
        """Compare allocations by symbol."""
        if not isinstance(other, Allocation):
            return False
        return self.symbol.upper() == other.symbol.upper()
    
    def __hash__(self) -> int:
        """Hash by symbol."""
        return hash(self.symbol.upper())


@dataclass
class TradeSummary:
    """Summary of trades executed during rebalancing."""
    
    buys: List[dict]  # List of {"symbol": str, "quantity": float, "cost": float, "status": str, "error": str}
    sells: List[dict]  # List of {"symbol": str, "quantity": float, "proceeds": float, "status": str, "error": str}
    total_cost: float
    total_proceeds: float
    final_allocations: List[Allocation]
    portfolio_value: float  # Market value of current holdings (does not include cash balance)
    portfolio_name: str = "SP400"  # Default for backward compatibility
    initial_capital: float = 0.0  # Track initial capital for performance calculation
    failed_trades: List[dict] = field(default_factory=list)  # List of failed trades with error messages
    cash_balance: float = 0.0  # Portfolio's cash balance (initial_capital + cumulative realized P&L)


@dataclass
class PortfolioPerformance:
    """Performance metrics for a single portfolio."""
    
    portfolio_name: str
    initial_capital: float
    current_value: float
    total_return: float  # Absolute return (current - initial)
    total_return_pct: float  # Percentage return ((current - initial) / initial * 100)
    total_cost: float  # Total cost of all buys
    total_proceeds: float  # Total proceeds from all sells
    net_invested: float  # Net capital invested (cost - proceeds)
    unrealized_pnl: float  # Unrealized profit/loss (current_value - net_invested)
    realized_pnl: float  # Realized profit/loss from sells


@dataclass
class MultiPortfolioSummary:
    """Summary of trades and performance across multiple portfolios."""
    
    portfolios: Dict[str, TradeSummary]  # Key: portfolio_name, Value: TradeSummary
    performances: Dict[str, PortfolioPerformance]  # Key: portfolio_name, Value: PortfolioPerformance
    total_initial_capital: float
    total_current_value: float
    total_net_invested: float  # Total net capital invested (sum of net_invested across portfolios)
    overall_return: float
    overall_return_pct: float

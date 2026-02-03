"""Data models for Firestore persistence."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TradeRecord:
    """Represents a trade record in Firestore."""

    symbol: str
    action: str  # "BUY" or "SELL"
    quantity: float
    price: float  # per share
    total: float  # total cost/proceeds
    timestamp: datetime
    trade_id: Optional[str] = None
    portfolio_name: str = "SP400"  # Default for backward compatibility
    # New fields for trade status tracking
    status: str = "planned"  # "planned", "submitted", "filled", "failed"
    execution_run_id: Optional[str] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    broker_order_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to Firestore-compatible dictionary."""
        result = {
            "symbol": self.symbol.upper(),
            "action": self.action,
            "quantity": self.quantity,
            "price": self.price,
            "total": self.total,
            "timestamp": self.timestamp,
            "trade_id": self.trade_id,
            "portfolio_name": self.portfolio_name,
            "status": self.status,
        }
        # Only include optional fields if they have values
        if self.execution_run_id:
            result["execution_run_id"] = self.execution_run_id
        if self.submitted_at:
            result["submitted_at"] = self.submitted_at
        if self.filled_at:
            result["filled_at"] = self.filled_at
        if self.failed_at:
            result["failed_at"] = self.failed_at
        if self.error_message:
            result["error_message"] = self.error_message
        if self.broker_order_id:
            result["broker_order_id"] = self.broker_order_id
        return result


@dataclass
class OwnershipRecord:
    """Represents ownership record in Firestore."""
    
    symbol: str
    quantity: float
    total_cost: float  # cumulative cost basis
    first_purchase_date: datetime
    last_purchase_date: datetime
    last_updated: datetime
    portfolio_name: str = "SP400"  # Default for backward compatibility
    
    def to_dict(self) -> dict:
        """Convert to Firestore-compatible dictionary."""
        return {
            "symbol": self.symbol.upper(),
            "quantity": self.quantity,
            "total_cost": self.total_cost,
            "first_purchase_date": self.first_purchase_date,
            "last_purchase_date": self.last_purchase_date,
            "last_updated": self.last_updated,
            "portfolio_name": self.portfolio_name,
        }


@dataclass
class ExternalSaleRecord:
    """Represents an external sale detection."""

    symbol: str
    quantity: float
    estimated_proceeds: float
    detected_date: datetime
    used_for_reinvestment: bool = False
    reinvestment_date: Optional[datetime] = None
    portfolio_name: str = "SP400"  # Default for backward compatibility

    def to_dict(self) -> dict:
        """Convert to Firestore-compatible dictionary."""
        return {
            "symbol": self.symbol.upper(),
            "quantity": self.quantity,
            "estimated_proceeds": self.estimated_proceeds,
            "detected_date": self.detected_date,
            "used_for_reinvestment": self.used_for_reinvestment,
            "reinvestment_date": self.reinvestment_date,
            "portfolio_name": self.portfolio_name,
        }


@dataclass
class PortfolioCashRecord:
    """Represents a portfolio's cash balance in Firestore."""

    portfolio_name: str
    initial_capital: float
    cash_balance: float
    created_at: datetime
    last_updated: datetime

    def to_dict(self) -> dict:
        """Convert to Firestore-compatible dictionary."""
        return {
            "portfolio_name": self.portfolio_name,
            "initial_capital": self.initial_capital,
            "cash_balance": self.cash_balance,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
        }


@dataclass
class ExecutionRunRecord:
    """Represents an execution run for a portfolio on a specific date."""

    portfolio_name: str
    date: str  # YYYY-MM-DD in ET
    status: str  # "started", "completed", "failed"
    started_at: datetime
    completed_at: Optional[datetime] = None
    trades_planned: int = 0
    trades_submitted: int = 0
    trades_filled: int = 0
    trades_failed: int = 0
    error_message: Optional[str] = None

    def is_successful(self) -> bool:
        """Check if run is successful: completed AND no trades stuck in submitted state."""
        return self.status == "completed" and self.trades_submitted == 0

    def to_dict(self) -> dict:
        """Convert to Firestore-compatible dictionary."""
        result = {
            "portfolio_name": self.portfolio_name,
            "date": self.date,
            "status": self.status,
            "started_at": self.started_at,
            "trades_planned": self.trades_planned,
            "trades_submitted": self.trades_submitted,
            "trades_filled": self.trades_filled,
            "trades_failed": self.trades_failed,
        }
        if self.completed_at:
            result["completed_at"] = self.completed_at
        if self.error_message:
            result["error_message"] = self.error_message
        return result

"""Abstract base class for email notifiers."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from ..broker.models import Allocation, TradeSummary, MultiPortfolioSummary


class EmailNotifier(ABC):
    """Abstract base class for email notification providers."""
    
    @abstractmethod
    def send_trade_summary(
        self,
        recipient: str,
        trade_summary: Union[TradeSummary, MultiPortfolioSummary],
        leaderboard_symbols: Optional[List[str]] = None,
        portfolio_leaderboards: Optional[Dict[str, List[str]]] = None,
    ) -> bool:
        """
        Send trade summary email.
        
        Args:
            recipient: Email recipient address
            trade_summary: Trade summary data (single or multi-portfolio)
            leaderboard_symbols: List of symbols from leaderboard (for single portfolio)
            portfolio_leaderboards: Dict of portfolio_name -> symbols (for multi-portfolio)
            
        Returns:
            True if email sent successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def send_error_notification(
        self,
        recipient: str,
        error_message: str,
        context: Dict[str, Any] = None,
    ) -> bool:
        """
        Send error notification email.
        
        Args:
            recipient: Email recipient address
            error_message: Error message
            context: Additional context information
            
        Returns:
            True if email sent successfully, False otherwise
        """
        pass
    
    def _format_trade_summary_html(
        self,
        trade_summary: Union[TradeSummary, MultiPortfolioSummary],
        leaderboard_symbols: Optional[List[str]] = None,
        portfolio_leaderboards: Optional[Dict[str, List[str]]] = None,
    ) -> str:
        """Format trade summary as HTML email."""
        # Check if it's multi-portfolio summary
        if isinstance(trade_summary, MultiPortfolioSummary):
            return self._format_multi_portfolio_html(trade_summary, portfolio_leaderboards or {})
        
        # Single portfolio format
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h2 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                .summary {{ background-color: #f2f2f2; padding: 15px; margin: 20px 0; }}
                .positive {{ color: #4CAF50; }}
                .negative {{ color: #f44336; }}
            </style>
        </head>
        <body>
            <h2>Portfolio Rebalancing Summary</h2>
            <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <div class="summary">
                <h3>Leaderboard Top 5</h3>
                <p>{', '.join(leaderboard_symbols or [])}</p>
            </div>
        """
        
        if trade_summary.sells:
            html += """
            <h3>Stocks Sold</h3>
            <table>
                <tr>
                    <th>Symbol</th>
                    <th>Quantity</th>
                    <th>Proceeds</th>
                </tr>
            """
            for sell in trade_summary.sells:
                html += f"""
                <tr>
                    <td>{sell['symbol']}</td>
                    <td>{sell['quantity']:.2f}</td>
                    <td>${sell['proceeds']:.2f}</td>
                </tr>
                """
            html += "</table>"
        
        if trade_summary.buys:
            html += """
            <h3>Stocks Bought</h3>
            <table>
                <tr>
                    <th>Symbol</th>
                    <th>Quantity</th>
                    <th>Cost</th>
                </tr>
            """
            for buy in trade_summary.buys:
                html += f"""
                <tr>
                    <td>{buy['symbol']}</td>
                    <td>{buy['quantity']:.2f}</td>
                    <td>${buy['cost']:.2f}</td>
                </tr>
                """
            html += "</table>"
        
        html += f"""
            <div class="summary">
                <h3>Final Portfolio</h3>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Current Price</th>
                        <th>Market Value</th>
                    </tr>
        """
        
        for allocation in trade_summary.final_allocations:
            html += f"""
                    <tr>
                        <td>{allocation.symbol}</td>
                        <td>{allocation.quantity:.2f}</td>
                        <td>${allocation.current_price:.2f}</td>
                        <td>${allocation.market_value:.2f}</td>
                    </tr>
            """
        
        html += f"""
                </table>
                <p><strong>Total Portfolio Value:</strong> ${trade_summary.portfolio_value:.2f}</p>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _format_multi_portfolio_html(
        self,
        multi_summary: MultiPortfolioSummary,
        portfolio_leaderboards: Dict[str, List[str]],
    ) -> str:
        """Format multi-portfolio summary as HTML email."""
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h2 {{ color: #333; }}
                h3 {{ color: #555; margin-top: 30px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                .summary {{ background-color: #f2f2f2; padding: 15px; margin: 20px 0; }}
                .positive {{ color: #4CAF50; font-weight: bold; }}
                .negative {{ color: #f44336; font-weight: bold; }}
                .portfolio-section {{ margin: 30px 0; padding: 20px; border: 1px solid #ddd; }}
            </style>
        </head>
        <body>
            <h2>Portfolio Rebalancing Summary - Multi-Portfolio</h2>
            <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <div class="summary">
                <h3>Overall Performance</h3>
                <table>
                    <tr>
                        <th>Metric</th>
                        <th>Value</th>
                    </tr>
                    <tr>
                        <td>Total Initial Capital</td>
                        <td>${multi_summary.total_initial_capital:,.2f}</td>
                    </tr>
                    <tr>
                        <td>Total Net Invested</td>
                        <td>${multi_summary.total_net_invested:,.2f}</td>
                    </tr>
                    <tr>
                        <td>Total Current Value</td>
                        <td>${multi_summary.total_current_value:,.2f}</td>
                    </tr>
                    <tr>
                        <td>Overall Return</td>
                        <td class="{'positive' if multi_summary.overall_return >= 0 else 'negative'}">
                            ${multi_summary.overall_return:,.2f} ({multi_summary.overall_return_pct:.2f}%)
                        </td>
                    </tr>
                </table>
            </div>
            
            <h3>Portfolio Performance Summary</h3>
            <table>
                <tr>
                    <th>Portfolio</th>
                    <th>Initial Capital</th>
                    <th>Current Value</th>
                    <th>Return</th>
                    <th>Return %</th>
                    <th>Realized P&L</th>
                    <th>Unrealized P&L</th>
                </tr>
        """
        
        for portfolio_name, performance in multi_summary.performances.items():
            return_class = "positive" if performance.total_return >= 0 else "negative"
            realized_class = "positive" if performance.realized_pnl >= 0 else "negative"
            unrealized_class = "positive" if performance.unrealized_pnl >= 0 else "negative"
            
            html += f"""
                <tr>
                    <td><strong>{portfolio_name}</strong></td>
                    <td>${performance.initial_capital:,.2f}</td>
                    <td>${performance.current_value:,.2f}</td>
                    <td class="{return_class}">${performance.total_return:,.2f}</td>
                    <td class="{return_class}">{performance.total_return_pct:.2f}%</td>
                    <td class="{realized_class}">${performance.realized_pnl:,.2f}</td>
                    <td class="{unrealized_class}">${performance.unrealized_pnl:,.2f}</td>
                </tr>
            """
        
        html += """
            </table>
        """
        
        # Add individual portfolio details
        for portfolio_name, summary in multi_summary.portfolios.items():
            leaderboard_symbols = portfolio_leaderboards.get(portfolio_name, [])
            performance = multi_summary.performances[portfolio_name]
            
            html += f"""
            <div class="portfolio-section">
                <h3>{portfolio_name} Portfolio Details</h3>
                <p><strong>Leaderboard Top 5:</strong> {', '.join(leaderboard_symbols)}</p>
                <p><strong>Performance:</strong> 
                    <span class="{'positive' if performance.total_return >= 0 else 'negative'}">
                        ${performance.total_return:,.2f} ({performance.total_return_pct:.2f}%)
                    </span>
                </p>
            """
            
            if summary.sells:
                html += """
                <h4>Stocks Sold</h4>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Proceeds</th>
                    </tr>
                """
                for sell in summary.sells:
                    html += f"""
                    <tr>
                        <td>{sell['symbol']}</td>
                        <td>{sell['quantity']:.2f}</td>
                        <td>${sell['proceeds']:.2f}</td>
                    </tr>
                    """
                html += "</table>"
            
            if summary.buys:
                html += """
                <h4>Stocks Bought</h4>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Cost</th>
                    </tr>
                """
                for buy in summary.buys:
                    html += f"""
                    <tr>
                        <td>{buy['symbol']}</td>
                        <td>{buy['quantity']:.2f}</td>
                        <td>${buy['cost']:.2f}</td>
                    </tr>
                    """
                html += "</table>"
            
            html += f"""
                <p><strong>Portfolio Value:</strong> ${summary.portfolio_value:,.2f}</p>
            </div>
            """
        
        # Add aggregated Final Holdings section (once for all portfolios)
        # Aggregate allocations across all portfolios
        aggregated_allocations = {}
        for summary in multi_summary.portfolios.values():
            for allocation in summary.final_allocations:
                symbol = allocation.symbol
                if symbol in aggregated_allocations:
                    # Sum quantities and market values for overlapping symbols
                    aggregated_allocations[symbol].quantity += allocation.quantity
                    aggregated_allocations[symbol].market_value += allocation.market_value
                    # Use the latest price (they should be the same anyway)
                    aggregated_allocations[symbol].current_price = allocation.current_price
                else:
                    # Create a copy to avoid modifying the original
                    from ..broker.models import Allocation
                    aggregated_allocations[symbol] = Allocation(
                        symbol=allocation.symbol,
                        quantity=allocation.quantity,
                        current_price=allocation.current_price,
                        market_value=allocation.market_value
                    )
        
        if aggregated_allocations:
            html += """
            <div class="portfolio-section">
                <h3>Final Holdings (All Portfolios)</h3>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Current Price</th>
                        <th>Market Value</th>
                    </tr>
            """
            
            # Sort by symbol for consistent display
            for symbol in sorted(aggregated_allocations.keys()):
                allocation = aggregated_allocations[symbol]
                html += f"""
                    <tr>
                        <td>{allocation.symbol}</td>
                        <td>{allocation.quantity:.2f}</td>
                        <td>${allocation.current_price:.2f}</td>
                        <td>${allocation.market_value:.2f}</td>
                    </tr>
                """
            
            total_portfolio_value = sum(alloc.market_value for alloc in aggregated_allocations.values())
            html += f"""
                </table>
                <p><strong>Total Portfolio Value:</strong> ${total_portfolio_value:,.2f}</p>
            </div>
            """
        
        html += """
        </body>
        </html>
        """
        
        return html
    
    def _format_trade_summary_text(
        self,
        trade_summary: Union[TradeSummary, MultiPortfolioSummary],
        leaderboard_symbols: Optional[List[str]] = None,
        portfolio_leaderboards: Optional[Dict[str, List[str]]] = None,
    ) -> str:
        """Format trade summary as plain text email."""
        # Check if it's multi-portfolio summary
        if isinstance(trade_summary, MultiPortfolioSummary):
            return self._format_multi_portfolio_text(trade_summary, portfolio_leaderboards or {})
        
        # Single portfolio format
        text = f"""
Portfolio Rebalancing Summary
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Leaderboard Top 5: {', '.join(leaderboard_symbols or [])}

"""
        
        if trade_summary.sells:
            text += "Stocks Sold:\n"
            for sell in trade_summary.sells:
                text += f"  - {sell['symbol']}: {sell['quantity']:.2f} shares, ${sell['proceeds']:.2f}\n"
            text += "\n"
        
        if trade_summary.buys:
            text += "Stocks Bought:\n"
            for buy in trade_summary.buys:
                text += f"  - {buy['symbol']}: {buy['quantity']:.2f} shares, ${buy['cost']:.2f}\n"
            text += "\n"
        
        text += "Final Portfolio:\n"
        for allocation in trade_summary.final_allocations:
            text += f"  - {allocation.symbol}: {allocation.quantity:.2f} shares @ ${allocation.current_price:.2f} = ${allocation.market_value:.2f}\n"
        
        text += f"\nTotal Portfolio Value: ${trade_summary.portfolio_value:.2f}\n"
        
        return text
    
    def _format_multi_portfolio_text(
        self,
        multi_summary: MultiPortfolioSummary,
        portfolio_leaderboards: Dict[str, List[str]],
    ) -> str:
        """Format multi-portfolio summary as plain text email."""
        text = f"""
Portfolio Rebalancing Summary - Multi-Portfolio
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

=== Overall Performance ===
Total Initial Capital: ${multi_summary.total_initial_capital:,.2f}
Total Net Invested: ${multi_summary.total_net_invested:,.2f}
Total Current Value: ${multi_summary.total_current_value:,.2f}
Overall Return: ${multi_summary.overall_return:,.2f} ({multi_summary.overall_return_pct:.2f}%)

=== Portfolio Performance Summary ===
"""
        
        for portfolio_name, performance in multi_summary.performances.items():
            text += f"""
{portfolio_name}:
  Initial Capital: ${performance.initial_capital:,.2f}
  Current Value: ${performance.current_value:,.2f}
  Return: ${performance.total_return:,.2f} ({performance.total_return_pct:.2f}%)
  Realized P&L: ${performance.realized_pnl:,.2f}
  Unrealized P&L: ${performance.unrealized_pnl:,.2f}
"""
        
        # Add individual portfolio details
        for portfolio_name, summary in multi_summary.portfolios.items():
            leaderboard_symbols = portfolio_leaderboards.get(portfolio_name, [])
            performance = multi_summary.performances[portfolio_name]
            
            text += f"""
=== {portfolio_name} Portfolio Details ===
Leaderboard Top 5: {', '.join(leaderboard_symbols)}
Performance: ${performance.total_return:,.2f} ({performance.total_return_pct:.2f}%)

"""
            
            if summary.sells:
                text += "Stocks Sold:\n"
                for sell in summary.sells:
                    text += f"  - {sell['symbol']}: {sell['quantity']:.2f} shares, ${sell['proceeds']:.2f}\n"
                text += "\n"
            
            if summary.buys:
                text += "Stocks Bought:\n"
                for buy in summary.buys:
                    text += f"  - {buy['symbol']}: {buy['quantity']:.2f} shares, ${buy['cost']:.2f}\n"
                text += "\n"
            
            text += f"Portfolio Value: ${summary.portfolio_value:,.2f}\n"
        
        # Add aggregated Final Holdings section (once for all portfolios)
        # Aggregate allocations across all portfolios
        aggregated_allocations = {}
        for summary in multi_summary.portfolios.values():
            for allocation in summary.final_allocations:
                symbol = allocation.symbol
                if symbol in aggregated_allocations:
                    # Sum quantities and market values for overlapping symbols
                    aggregated_allocations[symbol].quantity += allocation.quantity
                    aggregated_allocations[symbol].market_value += allocation.market_value
                    # Use the latest price (they should be the same anyway)
                    aggregated_allocations[symbol].current_price = allocation.current_price
                else:
                    # Create a copy to avoid modifying the original
                    from ..broker.models import Allocation
                    aggregated_allocations[symbol] = Allocation(
                        symbol=allocation.symbol,
                        quantity=allocation.quantity,
                        current_price=allocation.current_price,
                        market_value=allocation.market_value
                    )
        
        if aggregated_allocations:
            text += "\n=== Final Holdings (All Portfolios) ===\n"
            # Sort by symbol for consistent display
            for symbol in sorted(aggregated_allocations.keys()):
                allocation = aggregated_allocations[symbol]
                text += f"  - {allocation.symbol}: {allocation.quantity:.2f} shares @ ${allocation.current_price:.2f} = ${allocation.market_value:.2f}\n"
            
            total_portfolio_value = sum(alloc.market_value for alloc in aggregated_allocations.values())
            text += f"\nTotal Portfolio Value: ${total_portfolio_value:,.2f}\n"
        
        return text

from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import List
from pydantic import BaseModel
from agents.common import BaseMCPAgent

# --- New Imports ---
# This library fetches real data from Nord Pool
# Install it with: pip install nordpool
from nordpool import prices

# --- Pydantic Models (Unchanged) ---

class PriceRequest(BaseModel):
    """
    Request model for the 'get_electricity_price_forecast' tool.
    Specifies how many hours ahead to forecast.
    """
    lookahead_hours: int


class PricePoint(BaseModel):
    """
    Response model for a single price data point.
    """
    timestamp: datetime
    eur_mwh: float

# --- Electricity Price Agent (Updated) ---

class ElectricityPriceAgent(BaseMCPAgent):
    """
    This agent provides real-time and forecasted electricity prices by
    fetching data from the Nord Pool spot market.
    """
    
    def __init__(self) -> None:
        super().__init__(name="electricity-price-agent")
        # Initialize the Nord Pool client, specifying EUR currency
        self.spot_prices = prices.Prices(currency="EUR")

    def configure(self) -> None:
        """
        Registers the 'get_electricity_price_forecast' tool with the MCP server.
        """
        self.register_tool("get_electricity_price_forecast", self.get_forecast)

    def get_forecast(self, request: PriceRequest) -> List[PricePoint]:
        """
        Implementation of the 'get_electricity_price_forecast' tool.
        
        Fetches spot prices for today and tomorrow, then filters them
        to match the requested 'lookahead_hours'.
        """
        print(f"Received forecast request for {request.lookahead_hours} hours.")
        
        now = datetime.now()
        end_date_needed = now + timedelta(hours=request.lookahead_hours)
        
        all_prices_data = []

        # 1. Fetch today's prices
        try:
            # We fetch for the 'FI' (Finland) bidding area
            today_data = self.spot_prices.hourly(areas=['FI'])
            all_prices_data.extend(today_data['areas']['FI']['values'])
        except Exception as e:
            # This can happen if prices for today aren't published yet (e.g., late night)
            print(f"Warning: Could not fetch today's prices: {e}")

        # 2. Fetch tomorrow's prices
        # Note: These are typically published by Nord Pool around 14:00 EET
        try:
            tomorrow_date = now.date() + timedelta(days=1)
            tomorrow_data = self.spot_prices.hourly(end_date=tomorrow_date, areas=['FI'])
            all_prices_data.extend(tomorrow_data['areas']['FI']['values'])
        except Exception as e:
            # This is normal if it's before the ~14:00 publish time
            print(f"Info: Could not fetch tomorrow's prices (may not be published yet): {e}")

        # 3. Filter the combined data to match the request
        forecast_points = []
        for price_data in all_prices_data:
            # 'value' is the price in EUR/MWh
            # 'start_time' is a datetime object
            price_timestamp = price_data['start_time']
            price_value = price_data['value']
            
            # Ensure the data is within our requested time window
            if price_timestamp >= now and price_timestamp <= end_date_needed:
                forecast_points.append(
                    PricePoint(timestamp=price_timestamp, eur_mwh=price_value)
                )

        print(f"Found {len(forecast_points)} price points for the requested period.")
        return forecast_points


def serve() -> None:
    """
    Starts the agent server.
    """
    ElectricityPriceAgent().serve()


if __name__ == "__main__":
    serve()
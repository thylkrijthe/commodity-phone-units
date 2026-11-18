"""Commodity reference units and historical data."""

from dataclasses import dataclass
from datetime import date, datetime
import json
from urllib.request import urlopen
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

from silver_data import TROY_OUNCES_PER_KG

START = date(1999, 1, 4)


@dataclass(frozen=True)
class Market:
    ticker: str
    unit: str
    factor: float
    units: dict
    etf: str


MARKETS = {
    "Silver": Market("SI=F", "kg", TROY_OUNCES_PER_KG, {"troy oz": 1 / TROY_OUNCES_PER_KG, "kg": 1}, "SLV"),
    "Gold": Market("GC=F", "kg", TROY_OUNCES_PER_KG, {"troy oz": 1 / TROY_OUNCES_PER_KG, "kg": 1}, "GLD"),
    "Platinum": Market("PL=F", "kg", TROY_OUNCES_PER_KG, {"troy oz": 1 / TROY_OUNCES_PER_KG, "kg": 1}, "PPLT"),
    "Copper": Market("HG=F", "kg", 1 / 0.45359237, {"lb": 0.45359237, "kg": 1, "tonnes": 1000}, "CPER"),
    "WTI crude oil": Market("CL=F", "barrel", 1, {"barrels": 1, "kg": None}, "USO"),
    "Natural gas": Market("NG=F", "MMBtu", 1, {"MMBtu": 1, "kg": None}, "UNG"),
    "Corn": Market("ZC=F", "tonne", 1000 / 25.40117272 / 100, {"bushels": 25.40117272 / 1000, "kg": .001, "tonnes": 1}, "CORN"),
    "Wheat": Market("ZW=F", "tonne", 1000 / 27.2155422 / 100, {"bushels": 27.2155422 / 1000, "kg": .001, "tonnes": 1}, "WEAT"),
}


def daily_market(name, etf=False):
    market = MARKETS[name]
    today = datetime.now(ZoneInfo("America/New_York")).date()
    prices = yf.download((market.etf if etf else market.ticker), start=START.isoformat(), end=today.isoformat(),
                         auto_adjust=False, actions=etf, multi_level_index=False, progress=False,
                         threads=False, timeout=15)
    if prices is None or prices.empty:
        raise ValueError(f"No historical prices returned for {name}. Please retry.")
    with urlopen("https://api.frankfurter.dev/v1/1998-12-20..?base=EUR&symbols=USD", timeout=15) as response:
        rates = json.load(response)["rates"]
    fx = pd.Series({day: row["USD"] for day, row in rates.items()}, dtype=float)
    fx.index = pd.to_datetime(fx.index)
    splits = prices.get("Stock Splits", pd.Series(0., index=prices.index)).fillna(0).replace(0, 1).sort_index()
    prices = prices[["Open", "Close"]].sort_index()
    if etf:
        future_splits = splits.iloc[::-1].cumprod().iloc[::-1] / splits
        prices = prices.mul(future_splits, axis=0)
    prices.index = pd.DatetimeIndex(prices.index).tz_localize(None)
    prices.index.name = "date"
    if not prices.index.is_unique:
        raise ValueError(f"Invalid historical bars returned for {name}.")
    # Keep signed oil prices and match daily reference rates by availability.
    open_fx = fx.reindex(prices.index - pd.Timedelta(days=1), method="ffill").to_numpy()
    close_fx = fx.reindex(prices.index, method="ffill").to_numpy()
    converted = prices.div(pd.DataFrame({"Open": open_fx, "Close": close_fx}, index=prices.index)) * (1 if etf else market.factor)
    converted = converted.loc[np.isfinite(converted).all(axis=1)]
    if converted.empty:
        raise ValueError("No complete price bars with matching euro exchange rates were returned.")
    if (pd.Timestamp(today) - converted.index[-1]).days > 7:
        raise ValueError("The downloaded price series is out of date.")
    if etf:
        splits.index = pd.DatetimeIndex(splits.index).tz_localize(None)
        converted["share_multiplier"] = splits.cumprod().reindex(converted.index)
    return converted


@dataclass(frozen=True)
class CommodityHolding:
    quantity: float
    unit: str
    start_date: date
    market: str
    basis: str = "Commodity quantity"
    kg_conversion: float | None = None

    def __post_init__(self):
        if not np.isfinite(self.quantity) or self.quantity <= 0:
            raise ValueError("Enter a positive quantity or euro amount.")
        if self.basis not in ("Commodity quantity", "Euro amount", "ETF shares"):
            raise ValueError("Choose a supported holding type.")
        if self.basis == "Commodity quantity" and self.unit not in MARKETS[self.market].units:
            raise ValueError("Choose a supported commodity unit.")
        if self.basis == "Commodity quantity" and MARKETS[self.market].units[self.unit] is None:
            if self.kg_conversion is None or not np.isfinite(self.kg_conversion) or self.kg_conversion <= 0:
                raise ValueError("Enter the density or energy content needed to convert kilograms.")

    @property
    def amount(self):
        if self.basis == "ETF shares":
            return self.quantity
        if self.basis == "Euro amount":
            raise ValueError("Euro amounts require the starting reference price.")
        factor = MARKETS[self.market].units[self.unit]
        if factor is None:
            if self.market == "WTI crude oil":
                factor = 1 / (158.987294928 * self.kg_conversion)
            else:
                factor = self.kg_conversion
        return self.quantity * factor


def holding_history(bars, holding):
    prices = bars.loc[bars.index >= pd.Timestamp(holding.start_date), "Close"]
    if prices.empty:
        raise ValueError("Choose a starting date on or before the latest available close.")
    if holding.basis == "Euro amount" and prices.iloc[0] <= 0:
        raise ValueError("Choose a starting date with a positive reference price for a euro investment.")
    amount = None if holding.basis == "Euro amount" else holding.amount
    if holding.basis == "Euro amount":
        amount = holding.quantity / prices.iloc[0]
    if holding.basis == "ETF shares":
        multipliers = bars.loc[prices.index, "share_multiplier"]
        amount = holding.quantity * multipliers / multipliers.iloc[0]
    return pd.DataFrame({"reference_price_eur": prices, "quantity_in_reference_unit": amount,
                         "holding_value_eur": prices * amount})

"""Mobile interface for the silver holdings and research tools."""

from dataclasses import replace
from datetime import date
from io import BytesIO

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics import chart, summary
import matplotlib.pyplot as plt
from backtest import Account
from intraday import download_intraday
from research import fixed_run, walk_forward
from markets import START, MARKETS, CommodityHolding, daily_market, holding_history
from strategies import Parameters, STRATEGIES

TEAL = "#176c62"
COPPER = "#ae6d31"
CHART_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


@st.cache_data(ttl=900, show_spinner=False)
def daily_prices(name, etf=False):
    return daily_market(name, etf)


@st.cache_data(ttl=50, show_spinner=False)
def intraday_prices(name, etf=False):
    return download_intraday(name, etf)


def euro(value):
    return f"€{value:,.2f}"


def show_chart(series, unit, key, intraday=False):
    figure = go.Figure()
    for (name, values), color in zip(series.items(), (TEAL, COPPER, "#5967a3", "#826157")):
        time_label = "%{x|%d %b %H:%M} UTC" if intraday else "%{x|%d %b %Y}"
        figure.add_scatter(
            x=values.index, y=values, name=name, mode="lines", line={"color": color, "width": 2},
            hovertemplate=f"{time_label}<br>%{{y:,.2f}} {unit}<extra>%{{fullData.name}}</extra>",
        )
    buttons = (
        [dict(count=1, label="1 day", step="day", stepmode="backward")]
        if intraday else
        [dict(count=n, label=label, step="month", stepmode="backward")
         for n, label in [(1, "1M"), (6, "6M"), (12, "1Y")]]
    )
    figure.update_layout(
        height=385, margin={"l": 5, "r": 12, "t": 48, "b": 12},
        dragmode="zoom", uirevision=key, paper_bgcolor="#fbfaf7", plot_bgcolor="#fbfaf7",
        xaxis={"type": "date", "rangeselector": {"buttons": [*buttons, {"step": "all", "label": "All"}]}},
        yaxis={"title": unit, "tickformat": ",.0f", "fixedrange": False},
        legend={"orientation": "h", "x": 0, "y": -.18},
        showlegend=len(series) > 1,
    )
    st.plotly_chart(figure, width="stretch", config=CHART_CONFIG, key=key)


def holdings_page():
    st.header("My holdings")
    existing = st.session_state.get(f"holding-{selected_market}")
    bases = ("Commodity quantity", "Euro amount", "ETF shares")
    basis = st.radio("Enter holding as", bases,
                     index=bases.index(existing.basis) if existing else 0,
                     key=f"holding-basis-{selected_market}")
    unit = "EUR" if basis == "Euro amount" else "shares"
    conversion = None
    if basis == "Commodity quantity":
        unit = st.selectbox("Commodity unit", options=list(market.units),
                            key=f"commodity-unit-{selected_market}",
                            format_func=lambda value: {"kg": "Kilograms (kg)", "troy oz": "Troy ounces", "lb": "Pounds (lb)", "MMBtu": "Million BTU (MMBtu)"}.get(value, value.capitalize()))
        if market.units[unit] is None:
            if selected_market == "WTI crude oil":
                conversion = st.number_input("Oil density (kg per litre)", min_value=0.,
                                              value=0., format="%.5f", key="oil-density")
                st.caption("Enter the density of your oil. One barrel is 158.987294928 litres.")
            else:
                conversion = st.number_input("Gas energy content (MMBtu per kg)", min_value=0.,
                                              value=0., format="%.6f", key="gas-energy")
                st.caption("Enter the energy content for your gas composition.")
    elif basis == "ETF shares":
        st.caption(f"Fund used for {selected_market}: {market.etf}. Share counts follow splits. Cash dividends are excluded.")
    else:
        st.caption("Your euro amount buys a fixed quantity at the first available reference close on or after your date.")
    with st.form(f"holding-inputs-{selected_market}"):
        label = "Starting amount (€)" if basis == "Euro amount" else "Number of shares" if basis == "ETF shares" else "Quantity"
        quantity = st.number_input(label, min_value=0., max_value=1e12, step=1.,
                                   value=float(existing.quantity) if existing and existing.basis == basis else 0.,
                                   key=f"quantity-{selected_market}-{basis}")
        start = st.date_input("Starting date", value=existing.start_date if existing else START,
                              min_value=START, max_value=date.today(), key=f"holding-start-{selected_market}")
        submitted = st.form_submit_button("Calculate value", type="primary", width="stretch")
    holding = existing
    if existing is not None and existing.basis != basis:
        holding = None
    try:
        if submitted:
            holding = CommodityHolding(quantity, unit, start, selected_market, basis, conversion)
        if holding is None:
            return
        with st.spinner("Loading historical prices…"):
            bars = daily_prices(selected_market, holding.basis == "ETF shares")
            history = holding_history(bars, holding)
        st.session_state[f"holding-{selected_market}"] = holding
    except (OSError, ValueError) as error:
        st.error(str(error))
        return
    values = history["holding_value_eur"]
    amount = history["quantity_in_reference_unit"].iloc[-1]
    delta = f"{values.iloc[-1] / values.iloc[0] - 1:+.1%} since {values.index[0]:%d %b %Y}" if values.iloc[0] > 0 else None
    st.metric("Latest estimate", euro(values.iloc[-1]), delta)
    reference_unit = f"{market.etf} shares" if holding.basis == "ETF shares" else market.unit
    st.caption(f"{amount:,.4f} {reference_unit} · Close on {values.index[-1]:%d %b %Y} · "
               f"Starting reference value {euro(values.iloc[0])}")
    st.caption(f"Available history begins {bars.index[0]:%d %b %Y}.")
    st.session_state[f"holding-amount-{selected_market}"] = amount
    show_chart({"Holding value": values}, "€", f"holding-history-{selected_market}-{basis}")
    history["input_type"] = holding.basis
    history["input_quantity"] = holding.quantity
    history["input_unit"] = holding.unit
    history["source_symbol"] = market.etf if holding.basis == "ETF shares" else market.ticker
    history["kg_conversion"] = holding.kg_conversion
    st.download_button("Download holding history", history.to_csv(index_label="date"),
                       "commodity-holding-history.csv", "text/csv")


def intraday_panel():
    live = st.toggle("Refresh every minute", value=True)
    holding = st.session_state.get(f"holding-{selected_market}")
    show_holding = st.checkbox("Show my holding value", value=False) if holding else False

    @st.fragment(run_every="60s" if live else None)
    def quote():
        st.button("Check now")
        try:
            bars = intraday_prices(selected_market, bool(show_holding and holding.basis == "ETF shares"))
            st.session_state[f"intraday-{selected_market}-{bool(show_holding and holding.basis == 'ETF shares')}"] = bars
        except (ValueError, OSError) as error:
            st.warning(f"Could not refresh. {error}")
            bars = st.session_state.get(f"intraday-{selected_market}-{bool(show_holding and holding.basis == 'ETF shares')}")
            if bars is None:
                return
        values = bars["silver_eur_per_kg"]
        if show_holding:
            values = values * st.session_state[f"holding-amount-{selected_market}"]
        st.metric("Estimated holding value" if show_holding else "Latest reference price",
                  euro(values.iloc[-1]) if show_holding else f"{euro(values.iloc[-1])}/{market.unit}")
        st.caption(f"Commodity bar {values.index[-1]:%d %b, %H:%M UTC} · "
                   f"FX bar {bars.fx_time.iloc[-1]:%d %b, %H:%M UTC} · Feed may be delayed")
        show_chart({selected_market: values}, "€" if show_holding else f"€/{market.unit}",
                   f"intraday-{show_holding}", intraday=True)

    quote()


def prices_page():
    st.header("Price history")
    view = st.radio("View", ["Daily history", "Intraday"], horizontal=True)
    if view == "Intraday":
        intraday_panel()
        return
    try:
        with st.spinner("Loading daily commodity prices…"):
            bars = daily_prices(selected_market)
    except (OSError, ValueError) as error:
        st.error(str(error))
        return
    st.metric("Latest daily close", f'{euro(bars["Close"].iloc[-1])}/{market.unit}')
    st.caption(f"Available {bars.index[0]:%d %b %Y} to {bars.index[-1]:%d %b %Y}")
    history_start = st.date_input("Show history from", value=bars.index[0].date(),
                                  min_value=START, max_value=bars.index[-1].date(), key=f"history-start-{selected_market}")
    bars = bars.loc[bars.index >= pd.Timestamp(history_start)]
    show_chart({selected_market: bars["Close"]}, f"€/{market.unit}", "silver-daily")
    st.download_button("Download daily prices", bars.rename(
        columns={"Open": "open_eur_per_kg", "Close": "close_eur_per_kg"}
    ).to_csv(index_label="date"), "commodity-prices.csv", "text/csv")


def run_strategy(mode, params, account, train, test):
    bars = daily_prices(selected_market)
    bars = bars.loc[bars.index >= pd.Timestamp(strategy_start)]
    if (bars <= 0).any().any():
        raise ValueError("This period includes zero or negative futures prices. Choose a later start date for the long-only allocation backtest.")
    if mode == "Walk-forward":
        ledger, folds = walk_forward(bars, params, account, train, test)
        return {params.strategy: ledger}, folds
    if mode == "Compare strategies":
        return {name: fixed_run(bars, replace(params, strategy=name), account)
                for name in STRATEGIES}, None
    return {params.strategy: fixed_run(bars, params, account)}, None


def strategy_results(ledgers, folds):
    first = next(iter(ledgers.values()))
    equity = {name: run["strategy_equity"] for name, run in ledgers.items()}
    equity["Buy and hold"] = first["benchmark_equity"]
    show_chart(equity, "€", "strategy-equity")
    table = {name: summary(run, currency="€").loc["Strategy"] for name, run in ledgers.items()}
    table["Buy and hold"] = summary(first, currency="€").loc["Buy and hold"]
    st.dataframe(pd.DataFrame(table).T.round(2), width="stretch")
    if folds is not None:
        with st.expander("Walk-forward test periods"):
            st.dataframe(folds, width="stretch", hide_index=True)
            st.download_button("Download test periods", folds.to_csv(index=False),
                               "silver-walk-forward.csv", "text/csv")

    name = st.selectbox("Strategy detail", options=list(ledgers))
    run = ledgers[name]
    with st.expander("Price, trade markers and drawdown"):
        figure = chart(run, f"{selected_market} · {name}", currency="€",
                       price_label=f"Price (€/{market.unit})", close_label="Daily close")
        try:
            image = BytesIO()
            figure.savefig(image, dpi=145, format="png")
            st.image(image.getvalue(), width="stretch")
            st.download_button("Download chart", image.getvalue(), "silver-strategy.png", "image/png")
        finally:
            plt.close(figure)
    st.download_button("Download daily strategy results", run.to_csv(index_label="date"),
                       "silver-strategy.csv", "text/csv")


def strategy_page():
    st.header("Strategy lab")
    mode = st.selectbox("Mode", ["Single strategy", "Compare strategies", "Walk-forward"])
    name = st.selectbox("Strategy", STRATEGIES) if mode != "Compare strategies" else STRATEGIES[0]
    global strategy_start
    strategy_start = st.date_input("Backtest starting date", value=date(2018, 1, 1),
                                   min_value=START, max_value=date.today(), key=f"strategy-start-{selected_market}")
    with st.form("strategy"):
        window = st.number_input("Lookback (sessions)", min_value=5, max_value=250, value=20)
        with st.expander("Adjust allocation, fees and strategy settings"):
            capital = st.number_input("Starting capital (€)", min_value=1., max_value=1e9, value=10_000.)
            allocation = st.slider("Allocation (%)", 1, 100, 25)
            fee = st.number_input("Fee per trade (basis points)", min_value=0., max_value=9999., value=10.)
            if mode == "Compare strategies" or name == STRATEGIES[0]:
                entry = st.number_input("Buy below average (%)", min_value=0., max_value=99., value=2.)
                exit_threshold = st.number_input("Sell above average (%)", min_value=0., max_value=100., value=2.)
            else:
                entry = exit_threshold = 2.
            fast = st.number_input("Fast moving average (sessions)", 1, 249, 10) if (
                mode == "Compare strategies" or name == STRATEGIES[2]
            ) else 10
        train, test = 504, 126
        if mode == "Walk-forward":
            train = st.number_input("Training sessions", min_value=3, max_value=5000, value=train)
            test = st.number_input("Test sessions", min_value=1, max_value=2000, value=test)
        submitted = st.form_submit_button("Run backtest", type="primary", width="stretch")
    if submitted:
        try:
            if (mode == "Compare strategies" or name == STRATEGIES[2]) and fast >= window:
                raise ValueError("The fast moving average must be shorter than the lookback.")
            params = Parameters(name, window, fast, entry / 100, exit_threshold / 100)
            account = Account(capital, allocation / 100, fee)
            with st.spinner("Running the backtest…"):
                st.session_state.strategy_result = (selected_market, mode, name, *run_strategy(mode, params, account, train, test))
        except (OSError, ValueError) as error:
            st.error(str(error))
            return
    result = st.session_state.get("strategy_result")
    if result is not None and result[:3] == (selected_market, mode, name):
        strategy_results(*result[3:])


st.set_page_config(page_title="Commodity tracker", page_icon="◈", layout="centered")
st.title("Commodity tracker")
selected_market = st.selectbox("Commodity", options=list(MARKETS))
market = MARKETS[selected_market]
page = st.radio("Section", ["My holdings", "Price history", "Strategy lab"],
                horizontal=True, label_visibility="collapsed")
{"My holdings": holdings_page, "Price history": prices_page, "Strategy lab": strategy_page}[page]()
st.caption("Futures reference prices converted to euros. Physical purchase and resale prices may differ. History begins at the first available quote from 1999 onward.")

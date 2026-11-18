# Silver tracker for phones

The app has three sections. **My silver** values a weight in kilograms or troy ounces. **Price history** shows zoomable daily prices and a recent intraday view with an optional one-minute refresh. **Strategy lab** runs single-strategy, comparison and walk-forward backtests and exports the results. Prices use silver futures as a reference, converted into euros. The latest quote time is shown.

## Put it online and share privately

1. Extract the ZIP. Create a **private** GitHub repository and add the files inside the `silver-phone` folder to its root, including `.streamlit/config.toml` if using the supplied theme. The entry file is `app.py`.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) and connect GitHub. Under **Linked accounts → Source control**, authorize access to private repositories if needed.
3. Select **Create app → Yup, I have an app**. Choose the repository and branch, set the main file path to `app.py`, and choose Python **3.14** under **Advanced settings**. Click **Deploy**.
4. Once it loads, open **Share**, verify only specific people can view it, and invite your father using his email. He can open the link in Safari or Chrome and sign in with Google or an emailed one-time link. He needs no GitHub account and your Mac can be off.

Keep your notebook’s `silver_holding.json` and results out of the repository. This app keeps the entered quantity in the visitor’s current session. A fresh session can require entering it again. The intraday view refreshes while it is open, and Yahoo Finance prices may be delayed. Neither the app nor the backtest places trades.

## Try it on your Mac first

From the project folder:

```bash
~/python-envs/mude/bin/python -m pip install -r requirements.txt
~/python-envs/mude/bin/python -m streamlit run app.py
```

Open the URL shown in your terminal. To test private sharing, use a different browser or a private window after deployment.

[Streamlit deployment instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) · [Private app sharing](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)

## Expanded commodity version

Choose Silver, Gold, Platinum, Copper, WTI crude oil, Natural gas, Corn or Wheat at the top. Each market has its own holding quantity and unit in the current session. This is one holding per market. The app values each separately.

Daily history requests data from January 1999, the beginning of the euro reference-rate period used here. The first available futures bar varies by market and is displayed on the Price history screen. Incomplete bars and dates without a matching exchange rate are omitted. Choosing a holding date before the first available bar starts valuation at that first bar. Backtests have their own starting-date control.

Gold, silver and platinum use €/kg with kilograms or troy ounces for holdings. Copper uses €/kg with kilograms, pounds or tonnes. Oil uses €/barrel and gas €/MMBtu. Corn and wheat use €/tonne with kilograms or tonnes. Grain quotes are converted from US cents per bushel using the commodity-specific bushel weight. Futures history and FX rates can be revised by their providers.

The WTI series includes negative prices in 2020. Price charts retain those observations. The allocation backtest requires strictly positive prices, so select a later starting date to run it on oil when that period would otherwise be included.

## Update an existing deployment

Replace the corresponding files in your existing GitHub repository with the files in this folder. Add the new `markets.py` file too. Keep `app.py` at the repository root. Commit and push the changes. Streamlit will rebuild the existing app from the updated branch. The entry point remains `app.py`.

[Yahoo Finance commodity symbols](https://finance.yahoo.com/markets/commodities/) · [Exchange-rate API](https://frankfurter.dev/)

## Quantity, starting euros, or ETF shares

Under My holdings, choose Commodity quantity, Euro amount or ETF shares.

- Commodity quantity uses the selected market's usual unit or kilograms. Precious metals offer troy ounces, copper pounds, grains bushels, oil barrels and gas MMBtu. Tonnes remain available for copper and grains.
- Oil kilograms require your oil density in kg/litre. Gas kilograms require your gas energy content in MMBtu/kg. Enter the specification for your material.
- Euro amount represents a hypothetical fixed quantity purchased at the first available commodity reference close on or after your starting date. It excludes trading and storage costs.
- ETF shares use SLV for silver, GLD for gold, PPLT for platinum, CPER for copper, USO for oil, UNG for gas, CORN for corn and WEAT for wheat. Enter the number of shares held at the chosen starting date. The tracker adjusts the number of shares for subsequent splits and values them in euros. Cash dividends are excluded. Fund history starts when the fund's quotes become available.

CSV exports include the entered quantity, unit, input type, price symbol and any oil/gas conversion setting. Each market keeps its latest calculated holding during the session.

Unit references include the [CME metal converter](https://www.cmegroup.com/tools-information/calc_metal.html), [CME grain conversion guide](https://www.cmegroup.com/trading/agricultural/files/AC-225_MetricGuide.pdf) and [EIA energy units](https://www.eia.gov/energyexplained/units-and-calculators/).

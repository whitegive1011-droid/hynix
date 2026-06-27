# AIOS Manual-Only User Guide

AIOS now uses manual market data only. It does not call yfinance, Stooq,
Alpha Vantage, Finnhub, Binance, OKX, or any other market API during normal
operation or GitHub Actions.

Manual uploaded data is the single source of truth. All uploaded rows are
treated as official manual market data and normalized to `manual_upload`.
By user convention, all prices should be entered in USD/USDT-equivalent terms.

## 1. Mobile Daily Update Via GitHub Issues

Use this workflow when you are away from your computer.

1. Open `https://github.com/whitegive1011-droid/hynix` on your phone.
2. Tap `Issues`.
3. Tap `New issue`.
4. Choose `Manual Daily Prices`.
5. Keep the title format as `Manual Prices YYYY-MM-DD`.
6. Enter the trading date.
7. Paste the CSV rows.
8. Submit the issue.

GitHub Actions will parse the issue, import all rows into
`data/cache/market_cache.csv`, regenerate reports from CSV only, run tests,
deploy GitHub Pages, comment on the issue, and close it if successful.

## 2. Required CSV Format

Use this header:

```csv
date,ticker,close,change_pct,market_cap,source,note
```

Only `date`, `ticker`, and `close` are required. `change_pct`, `market_cap`,
`source`, and `note` may be blank. Any non-empty `source` is accepted, including
`binance_proxy`, `okx_proxy`, `futu_official`, `manual_official`, `futu`,
`binance`, and `okx`. AIOS stores the normalized source as `manual_upload`.

Example:

```csv
date,ticker,close,change_pct,market_cap,source,note
2026-06-27,NVDA,192.530,-1.64,,futu_official,"Manual price from screenshot"
2026-06-27,AAPL,281.57,1.65,,binance,"AAPLUSDT manual price"
2026-06-27,MSFT,375.61,5.00,,futu,"Manual price"
2026-06-27,MU,1143.47,0.48,,binance_proxy,"Accepted as manual upload"
2026-06-27,000660.KS,2673000,-8.36,,okx,"SK Hynix manual price"
```

Rows are upserted by `date,ticker`. Submitting the same ticker/date again
replaces the older row.

## 3. Required Tickers And Optional Tickers

Core basket tickers:

```text
MSFT
GOOGL
AMZN
META
AAPL
TSLA
000660.KS
MU
005930.KS
```

Recommended tickers:

```text
NVDA
QQQ
SOXX
7709.HK
7747.HK
```

If required tickers are missing, AIOS keeps unavailable metrics as `N/A` and
the recommendation should be `Uncertain`.

## 4. How To Check GitHub Actions Status

1. Open the repository on GitHub.
2. Tap or click `Actions`.
3. For mobile updates, open `Manual Price Issue Import`.
4. Confirm the run is green.

If the run fails, open the failed step. The issue should also receive an error
comment and stay open.

## 5. How To Open The Dashboard

Open:

```text
https://whitegive1011-droid.github.io/hynix/dashboard.html
```

The dashboard shows:

- Today's recommendation
- Confidence
- Risk level
- Market mode
- Data Source: `Manual Upload Only`
- Manual upload date
- Manual tickers used
- Cache coverage
- Missing required tickers
- History depth per ticker
- 5D readiness
- 20D readiness

## 6. Local Desktop CSV Import Workflow

Use this workflow to backfill many historical rows.

```bash
cd /Users/jihaotian/Documents/Codex/2026-06-26/prompt-decision-review-engine-trade-journal/work/hynix-publish
```

Generate a template:

```bash
../../.venv/bin/python main.py cache-template \
  --output data/cache/manual_prices_template.csv
```

Fill at least:

```csv
date,ticker,close
```

Import:

```bash
../../.venv/bin/python main.py import-cache \
  --input data/cache/manual_prices_template.csv \
  --output data/cache/market_cache.csv
```

Regenerate reports:

```bash
../../.venv/bin/python main.py --provider csv --output-dir reports --no-input
```

Run tests:

```bash
../../.venv/bin/python -m pytest
```

## 7. When To Use Mobile Vs Desktop Workflow

Use mobile GitHub Issues for daily updates with a small number of rows.

Use desktop CSV import when you need to backfill 6 or 21 trading days for many
tickers, or when you want to inspect the cache locally before committing.

## 8. Why Indicators May Still Show N/A

`N/A` usually means the cache does not contain enough manual history.

Common causes:

- A required core basket ticker is missing.
- Only today's prices are available.
- 5D history has fewer than 6 trading days.
- 20D history has fewer than 21 trading days.
- The product ticker exists but AI/HBM basket tickers are incomplete.

AIOS must not invent missing prices. Missing data should remain `N/A`.

## 9. Data History Requirements

- `5D` requires at least 6 trading days.
- `20D` requires at least 21 trading days.
- Risk Score depends on 5D basket returns, so it remains `N/A` until 5D is
  ready for the required basket.

For best results, keep at least 21 trading days for every core basket ticker.

## 10. Safety Notes

- Do not use fake prices.
- Keep all manual prices in the USD/USDT-equivalent convention.
- Missing data should remain `N/A`.
- `Uncertain` is expected when basket data or history is incomplete.
- Every recommendation should remain explainable and traceable to manual data
  in `data/cache/market_cache.csv`.

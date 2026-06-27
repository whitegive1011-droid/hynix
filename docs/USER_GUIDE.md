# AIOS User Guide

This guide explains how to update AIOS market data from a phone or desktop, how
to verify that the update ran successfully, and why some indicators may still
show `N/A`.

## 1. Mobile Daily Update Via GitHub Issues

Use the mobile workflow for daily price updates when you are away from your
computer.

1. Open the GitHub repository on your phone:
   `https://github.com/whitegive1011-droid/hynix`
2. Tap `Issues`.
3. Tap `New issue`.
4. Choose the `Manual Daily Prices` issue form.
5. Keep the title format as:

```text
Manual Prices YYYY-MM-DD
```

6. Enter the trading date in `YYYY-MM-DD` format.
7. Paste the price CSV into the `Price CSV` field.
8. Submit the issue.

After submission, GitHub Actions will:

- Parse the issue body
- Validate the CSV
- Update `data/manual/daily_manual_prices.csv`
- Upsert prices into `data/cache/market_cache.csv`
- Regenerate `latest_signal.json`, `investment_dashboard.xlsx`, and
  `dashboard.html`
- Deploy the dashboard to GitHub Pages
- Comment on the issue with the result
- Close the issue if the import succeeds

If the import fails, the workflow comments on the issue and leaves it open so
the data can be corrected.

## 2. Required CSV Format

The mobile issue form expects this header:

```csv
date,ticker,close,change_pct,market_cap,source,note
```

Example:

```csv
date,ticker,close,change_pct,market_cap,source,note
2026-06-27,7709.HK,154.00,-14.20,,futu,"HK intraday"
2026-06-27,000660.KS,2724000,-8.50,,naver,"SK Hynix"
2026-06-27,005930.KS,343500,-4.00,,naver,"Samsung"
2026-06-27,MU,115.50,-4.80,,futu,"overnight"
```

Column notes:

- `date`: Required. Must be `YYYY-MM-DD`.
- `ticker`: Required. Must match the ticker symbols used by AIOS.
- `close`: Required. Must be a real positive market price.
- `change_pct`: Optional. Daily percentage change, if available.
- `market_cap`: Optional. Market capitalization, if available.
- `source`: Optional but recommended. Example: `futu`, `naver`, `yahoo`.
- `note`: Optional. Short context about the price.

Rows are upserted by `date,ticker`. If the same ticker and date are submitted
again, the newest submission replaces the older row.

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

Optional but recommended tickers:

```text
NVDA
QQQ
SOXX
7709.HK
7747.HK
```

AIOS does not fail hard if some tickers are missing. It records warnings, keeps
unavailable metrics as `N/A`, and reduces recommendation confidence.

## 4. How To Check GitHub Actions Status

After submitting a manual price issue:

1. Open the repository on GitHub.
2. Tap or click `Actions`.
3. Look for the latest workflow run.
4. For mobile issue updates, check `Manual Price Issue Import`.
5. For regular scheduled or pushed updates, check `AIOS CI/CD`.

Status meanings:

- `Queued`: GitHub has accepted the job but has not started yet.
- `In progress`: The workflow is running.
- `Success`: Data import, tests, report generation, and deployment completed.
- `Failure`: Open the workflow run and read the failed step. The issue should
  also receive an error comment if the mobile import failed.

## 5. How To Open The Dashboard

Open the deployed dashboard here:

```text
https://whitegive1011-droid.github.io/hynix/dashboard.html
```

The dashboard should show:

- Today's recommendation
- Confidence
- Risk level
- Market mode
- Data source
- Last update
- Data quality
- Manual mobile input status
- Latest manual input date
- Manual tickers used
- Missing ticker warnings
- Key indicators

## 6. Local Desktop CSV Import Workflow

Use the desktop workflow when you want to import many historical rows at once,
especially when filling 21 or more trading days.

From the publish repository:

```bash
cd /Users/jihaotian/Documents/Codex/2026-06-26/prompt-decision-review-engine-trade-journal/work/hynix-publish
```

Generate a manual template:

```bash
../../.venv/bin/python main.py cache-template \
  --output data/cache/manual_prices_template.csv
```

Open and fill the template:

```bash
open data/cache/manual_prices_template.csv
```

The minimum desktop CSV format is:

```csv
date,ticker,close
```

Optional desktop columns:

```text
open,high,low,adj_close,volume
```

Import the filled CSV:

```bash
../../.venv/bin/python main.py import-cache \
  --input data/cache/manual_prices_template.csv \
  --output data/cache/market_cache.csv
```

Regenerate reports from the CSV cache:

```bash
../../.venv/bin/python main.py \
  --provider csv \
  --output-dir reports \
  --no-input
```

Run tests:

```bash
../../.venv/bin/python -m pytest
```

If tests pass, commit and push with GitHub Desktop:

1. Review changed files.
2. Use a commit message such as:

```text
data: update manual market cache
```

3. Click `Commit to main`.
4. Click `Push origin`.
5. Wait for GitHub Actions to finish.

## 7. When To Use Mobile Vs Desktop Workflow

Use the mobile GitHub Issues workflow when:

- You only need to add today's prices
- You are away from your computer
- You want GitHub Actions to handle import, testing, report generation, and
  deployment automatically

Use the desktop CSV workflow when:

- You need to backfill historical prices
- You need to update many rows at once
- You want to inspect the cache file locally before committing
- You are trying to eliminate `N/A` values caused by insufficient history

## 8. Why Indicators May Still Show N/A

`N/A` usually means AIOS does not have enough reliable source data to calculate
the metric.

Common causes:

- Required basket tickers are missing
- Only one or two trading days are available
- The cache has the product ticker but not the AI/HBM basket tickers
- Live providers failed and the CSV cache is incomplete
- Historical rows do not cover enough days for 5D or 20D calculations

This is expected behavior. AIOS should not invent missing market data.

## 9. Data History Requirements

Return and indicator calculations need enough historical rows.

- `5D` requires at least 6 trading days.
- `20D` requires at least 21 trading days.

For best results, keep at least 21 trading days for every core basket ticker:

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

If only today's prices are imported, the cache freshness improves, but 5D and
20D metrics may still remain `N/A`.

## 10. Safety Notes

- Do not use fake prices.
- Do not fill missing prices with guessed values.
- Missing data should remain `N/A`.
- `Uncertain` is expected when basket data is incomplete.
- A lower-confidence recommendation is safer than a confident recommendation
  based on incomplete market context.
- Every recommendation should remain explainable and traceable to objective
  data.


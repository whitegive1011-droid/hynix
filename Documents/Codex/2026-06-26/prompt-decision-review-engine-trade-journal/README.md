# AI Investment Operating System (AIOS)

AIOS is a lightweight personal investment decision-support system for AI infrastructure and HBM positions.

Version: `v0.1`

## What It Does

- Fetches market data through a multi-source provider
- Tries `yfinance`, Stooq, optional API providers, and CSV cache fallback
- Retries failed market data downloads where configured
- Falls back to a committed CSV cache when live providers are unavailable
- Calculates indicators and AI/HBM basket metrics
- Generates an explainable rule-based recommendation
- Produces `latest_signal.json`, `investment_dashboard.xlsx`, `dashboard.html`, `history.csv`, `execution.log`, and `deployment_summary.txt`

AIOS does not place trades. No API keys are required for the default setup.
Optional Alpha Vantage and Finnhub keys can be provided through environment
variables and must not be committed.

## User Guide

For mobile and desktop data update steps, see
[docs/USER_GUIDE.md](docs/USER_GUIDE.md).

## Local Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

## Run Tests

```bash
.venv/bin/python -m pytest
```

## Run Locally

Default run:

```bash
.venv/bin/python main.py --no-input
```

Offline CSV run:

```bash
.venv/bin/python main.py \
  --config work/smoke_config.yaml \
  --portfolio work/smoke_portfolio.yaml \
  --provider csv \
  --output-dir reports \
  --no-input
```

Seed the local market cache:

```bash
.venv/bin/python main.py seed-cache \
  --provider stooq \
  --output data/cache/market_cache.csv
```

For Yahoo seeding:

```bash
.venv/bin/python main.py seed-cache \
  --provider yfinance \
  --output data/cache/market_cache.csv
```

Manual cache import:

```bash
.venv/bin/python main.py cache-template \
  --output data/cache/manual_prices_template.csv
```

Fill the template with real market prices. The minimum required columns are:

```text
date,ticker,close
```

Optional columns are:

```text
open,high,low,adj_close,volume
```

Import the filled CSV:

```bash
.venv/bin/python main.py import-cache \
  --input data/cache/manual_prices_template.csv \
  --output data/cache/market_cache.csv
```

The importer upserts rows by `date,ticker`, so running it multiple times will not create duplicate cache rows.

Mobile manual price input through GitHub Issues:

1. Open a new issue with the `Manual Daily Prices` form
2. Keep the title as `Manual Prices YYYY-MM-DD`
3. Paste CSV rows in this format:

```text
date,ticker,close,change_pct,market_cap,source,note
2026-06-27,7709.HK,154.00,-14.20,,futu,"HK intraday"
2026-06-27,000660.KS,2724000,-8.50,,naver,"SK Hynix"
2026-06-27,005930.KS,343500,-4.00,,naver,"Samsung"
2026-06-27,MU,1155.00,-4.80,,futu,"overnight"
```

The GitHub Actions workflow imports the issue, updates
`data/manual/daily_manual_prices.csv`, upserts `data/cache/market_cache.csv`,
regenerates reports, deploys GitHub Pages, comments on the issue, and closes it
after success. If required basket tickers are missing, AIOS keeps unavailable
metrics as `N/A` and the recommendation remains `Uncertain`.

Dry run:

```bash
.venv/bin/python main.py --dry-run --no-input
```

## Configuration

Main configuration:

```text
config.yaml
```

Portfolio configuration:

```text
portfolio.yaml
```

If `portfolio.yaml` is missing, AIOS uses safe defaults with zero positions.

## Data Fallback

The default provider is `multi`.

Provider priority:

1. `yfinance`
2. `stooq` for supported US tickers
3. `alphavantage` when `ALPHAVANTAGE_API_KEY` exists
4. `finnhub` when `FINNHUB_API_KEY` exists
5. CSV cache

If live providers fail or return partial data, AIOS falls back to:

```text
data/cache/market_cache.csv
```

The dashboard displays:

- Data Source
- Last Update
- Data Quality
- Data Quality Score
- Cache Coverage
- Missing Tickers
- Stale Tickers
- Provider Attribution

## Output Files

Generated files are written under:

```text
reports/
```

Local `reports/` output is ignored by Git. The GitHub Actions workflow force-adds the generated release artifacts only after tests and report generation succeed.

## GitHub Actions Deployment

Workflow:

```text
.github/workflows/aios-ci-cd.yml
.github/workflows/manual-price-issue.yml
```

The workflow:

1. Installs Python dependencies
2. Runs `pytest`
3. Stops if tests fail
4. Generates reports
5. Validates required report files
6. Commits generated reports
7. Deploys `dashboard.html` to GitHub Pages

No repository secrets are required.

## Required GitHub Setup

In the GitHub repository:

1. Go to `Settings -> Pages`
2. Set Source to `GitHub Actions`
3. Go to `Settings -> Actions -> General`
4. Allow workflows to read and write repository contents
5. Ensure the branch contains `.github/workflows/aios-ci-cd.yml`

## Release Check

Before release:

```bash
.venv/bin/python -m pytest
.venv/bin/python main.py --no-input
```

Confirm:

- `reports/latest_signal.json` is valid JSON
- `reports/investment_dashboard.xlsx` opens successfully
- `reports/dashboard.html` renders locally
- `reports/history.csv` has no duplicate `date,ticker` rows
- `reports/deployment_summary.txt` records execution status

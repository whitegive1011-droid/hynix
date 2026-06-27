# AI Investment Operating System (AIOS)

AIOS is a lightweight personal investment decision-support system for AI
infrastructure and HBM positions.

Version: `v0.1`

## What It Does

- Uses manual uploaded market data as the single source of truth
- Reads market data only from `data/cache/market_cache.csv`
- Imports mobile updates through GitHub Issues
- Calculates indicators and AI/HBM basket metrics from the manual cache
- Generates explainable rule-based recommendations
- Produces `latest_signal.json`, `investment_dashboard.xlsx`,
  `dashboard.html`, `history.csv`, `execution.log`, and
  `deployment_summary.txt`

AIOS does not place trades and does not call external market APIs during normal
operation or GitHub Actions. No repository secrets or API keys are required.

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

```bash
.venv/bin/python main.py --provider csv --output-dir reports --no-input
```

The default runtime is manual-only. The optional alias is:

```bash
.venv/bin/python main.py --manual-only --output-dir reports --no-input
```

## Manual Cache Import

Generate a template:

```bash
.venv/bin/python main.py cache-template \
  --output data/cache/manual_prices_template.csv
```

Fill at least:

```text
date,ticker,close
```

Import the filled CSV:

```bash
.venv/bin/python main.py import-cache \
  --input data/cache/manual_prices_template.csv \
  --output data/cache/market_cache.csv
```

The importer upserts rows by `date,ticker`, so running it multiple times will
not create duplicate cache rows.

## Mobile Manual Price Input

Open a new issue with the `Manual Daily Prices` form and paste rows in this
format:

```text
date,ticker,close,change_pct,market_cap,source,note
2026-06-27,AAPL,281.57,1.65,,binance,"AAPLUSDT manual price"
2026-06-27,MSFT,375.61,5.00,,futu,"Manual price"
2026-06-27,MU,1143.47,0.48,,binance_proxy,"Accepted as manual upload"
```

All uploaded rows are normalized to `manual_upload` and imported into
`data/cache/market_cache.csv`.

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

## Data Mode

AIOS is manual-only:

1. GitHub Issue CSV upload
2. `data/cache/market_cache.csv`
3. Report generation from CSV

No yfinance, Stooq, Alpha Vantage, Finnhub, Binance, or OKX market API is used
by the runtime or GitHub Actions.

The dashboard displays:

- Data Source: `Manual Upload Only`
- Last Update
- Data Quality
- Data Quality Score
- Cache Coverage
- Missing Tickers
- History Depth
- 5D Readiness
- 20D Readiness

## Output Files

Generated files are written under:

```text
reports/
```

Local `reports/` output is ignored by Git. GitHub Actions force-adds generated
release artifacts only after tests and report generation succeed.

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
4. Generates reports from CSV only
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
.venv/bin/python main.py --provider csv --output-dir reports --no-input
```

Confirm:

- `reports/latest_signal.json` is valid JSON
- `reports/investment_dashboard.xlsx` opens successfully
- `reports/dashboard.html` renders locally
- `reports/history.csv` has no duplicate `date,ticker` rows
- `reports/deployment_summary.txt` records execution status

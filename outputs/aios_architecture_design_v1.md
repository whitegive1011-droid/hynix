# AIOS Architecture Design V1

Source prompt:

`outputs/aios_prompt_v2_decision_review_engine.md`

Status:

Architecture milestone draft for review. No business code should be implemented until this architecture is approved.

========================================================
1. PROJECT ARCHITECTURE
========================================================

AIOS will be a lightweight, file-based Python application that runs from:

```bash
python main.py
```

The architecture is organized around four first-class engines:

1. Data Quality Engine
2. Market Engine
3. Decision Engine
4. Review Engine

The user-facing behavior layer is:

5. Investment Coach

The output layer is:

6. Report Generation

The persistence layer is:

7. File Storage

High-level architecture:

```text
config.yaml / portfolio.yaml
        |
        v
Configuration Loader
        |
        v
Market Data Providers
        |
        v
Data Quality Engine
        |
        v
Market Engine
        |
        v
Decision Engine
        |
        +--------------------+
        |                    |
        v                    v
Latest Signal          Investment Coach
        |                    |
        v                    v
Review Engine <---- Investor Action Input
        |
        v
Report Generators
        |
        v
Excel / HTML / CSV / JSON / Logs
```

Design principles:

- Rule-based first.
- Explainable by default.
- No database in V1.
- No web framework in V1.
- CSV and JSON are the lightweight data store.
- Engines exchange typed Python objects, not raw dictionaries.
- Export modules convert typed objects into CSV, JSON, Excel, and HTML.
- All important thresholds live in `config.yaml`.
- Missing first-run files are created automatically.

========================================================
2. DIRECTORY STRUCTURE
========================================================

Recommended structure:

```text
aios/
  main.py
  config.yaml
  portfolio.yaml
  requirements.txt
  README.md
  .gitignore

  aios/
    __init__.py

    app/
      __init__.py
      runner.py
      context.py

    config/
      __init__.py
      loader.py
      models.py

    data/
      __init__.py
      providers.py
      quality.py
      models.py

    market/
      __init__.py
      indicators.py
      baskets.py
      classifier.py
      scoring.py
      engine.py
      models.py

    decision/
      __init__.py
      rules.py
      engine.py
      models.py

    review/
      __init__.py
      engine.py
      evaluator.py
      statistics.py
      behavior.py
      models.py

    coach/
      __init__.py
      prompts.py
      recorder.py
      models.py

    reports/
      __init__.py
      excel.py
      html.py
      json_exporter.py
      monthly.py
      templates/
        dashboard.html.j2
        monthly_review.html.j2

    storage/
      __init__.py
      paths.py
      csv_store.py
      json_store.py
      schemas.py

    utils/
      __init__.py
      dates.py
      logging.py
      math.py

  data/
    raw/
    processed/

  outputs/
    investment_dashboard.xlsx
    dashboard.html
    latest_signal.json
    history.csv
    data_quality_report.json
    decision_review.csv
    investor_actions.csv
    monthly_review.xlsx
    monthly_review.html
    execution.log

  tests/
    test_config_loader.py
    test_data_quality.py
    test_indicators.py
    test_market_classifier.py
    test_decision_engine.py
    test_review_engine.py
    test_behavior_analysis.py
    test_storage.py
    fixtures/
      market_prices_sample.csv
      history_sample.csv
      decision_review_sample.csv
```

Notes:

- `main.py` should stay thin.
- Business logic belongs inside `aios/`.
- `outputs/` contains generated user-facing files.
- `data/raw/` and `data/processed/` are optional caches, not a database.
- The repository should be small enough to run comfortably on a MacBook Air M1.

========================================================
3. MODULE RESPONSIBILITIES
========================================================

`main.py`

- Entry point.
- Calls `AiosRunner`.
- Handles top-level exceptions and exit code.

`aios/app/runner.py`

- Orchestrates one full run.
- Loads config and portfolio.
- Fetches market data.
- Runs data quality checks.
- Runs market analysis.
- Runs decision generation.
- Records review entries.
- Generates all output files.

`aios/config/loader.py`

- Loads `config.yaml` and `portfolio.yaml`.
- Applies defaults.
- Validates required fields.

`aios/config/models.py`

- Defines typed config dataclasses.
- Keeps runtime config explicit and testable.

`aios/data/providers.py`

- Provides a provider interface.
- V1 primary provider: `yfinance`.
- V1 fallback provider: configurable, initially another yfinance query mode or local cached data.
- Future providers can be added without changing engine logic.

`aios/data/quality.py`

- Implements Data Quality Engine.
- Validates freshness, missing tickers, stale data, abnormal prices, and fallback usage.
- Produces `DataQualityReport`.
- Returns confidence penalty for downstream decisions.

`aios/market/indicators.py`

- Calculates MA, EMA, MACD, RSI14, ADX14, ATR14, Bollinger Bands, volume changes, gaps, support, and resistance.

`aios/market/baskets.py`

- Calculates AI Basket and HBM Basket returns.
- Calculates relative ratio.
- Calculates Samsung / SK Hynix market cap ratio when available.

`aios/market/classifier.py`

- Classifies market mode:
  - Uptrend
  - Range
  - Downtrend
  - Mixed

`aios/market/scoring.py`

- Calculates:
  - Risk Score
  - Trend Score
  - Momentum Score
  - Range Score
  - Volatility Score

`aios/market/engine.py`

- Combines indicators, baskets, classification, and scoring.
- Produces `MarketState`.
- Does not generate buy/sell decisions.

`aios/decision/rules.py`

- Contains transparent rule definitions.
- Maps market state into recommendation candidates.
- Keeps rule reasons traceable.

`aios/decision/engine.py`

- Produces the daily recommendation.
- Applies data quality confidence penalty.
- Produces reasons, warning indicators, confidence, risk level, current position, and suggested position.

`aios/review/engine.py`

- Coordinates the Decision Review Engine.
- Appends daily review records.
- Updates records when forward returns become available.

`aios/review/evaluator.py`

- Evaluates recommendation result:
  - Successful
  - Failed
  - Missed Opportunity
  - Avoided Loss
  - Pending

`aios/review/statistics.py`

- Calculates:
  - Recommendation Accuracy
  - Risk Management Accuracy
  - Trend Classification Accuracy
  - Range Classification Accuracy
  - Position Adjustment Accuracy
  - Win Rate
  - Average Gain
  - Average Loss
  - Consecutive correct / error streaks

`aios/review/behavior.py`

- Calculates investor behavior metrics:
  - Recommendation Follow Rate
  - Return if Following Engine
  - Actual Return
  - Behavior Difference
  - Missed Gain
  - Loss Avoided

`aios/coach/prompts.py`

- Builds the daily Investment Coach question.
- V1 should support local command-line input.

`aios/coach/recorder.py`

- Records whether the user executed the recommendation.
- Appends to `investor_actions.csv`.

`aios/reports/excel.py`

- Generates `investment_dashboard.xlsx`.
- Includes Dashboard, Portfolio, Technical, Data Quality, AI_HBM_History, Trade Journal, Decision Review, Investor Behavior, Performance, and Monthly Review sheets.

`aios/reports/html.py`

- Generates `dashboard.html`.
- Uses Jinja2 templates.
- Optimized for desktop, phone, and dark mode.

`aios/reports/monthly.py`

- Generates `monthly_review.xlsx` and `monthly_review.html`.
- Runs when month-end or manually requested.

`aios/storage/csv_store.py`

- Reads, writes, and upserts CSV files safely.
- Prevents duplicate records for the same date and run time.

`aios/storage/json_store.py`

- Writes `latest_signal.json` and `data_quality_report.json`.

`aios/storage/schemas.py`

- Documents CSV and JSON schemas in code.
- Validates required columns.

`aios/utils/logging.py`

- Configures console and file logging.
- Writes to `outputs/execution.log`.

========================================================
4. DATA FLOW
========================================================

One daily run:

```text
1. Load config.yaml
2. Load portfolio.yaml
3. Resolve ticker universe
4. Fetch market data from primary provider
5. Run Data Quality Engine
6. If needed, fetch fallback data
7. Re-run or update data quality report
8. Run Market Engine
9. Run Decision Engine
10. Generate latest_signal.json
11. Ask Investment Coach execution question if interactive mode is enabled
12. Append or update investor_actions.csv
13. Append or update decision_review.csv
14. Update forward returns for older review records
15. Generate investment_dashboard.xlsx
16. Generate dashboard.html
17. Generate monthly review if required
18. Write execution.log
```

Data contracts:

```text
MarketDataFrame
  -> DataQualityReport
  -> ValidatedMarketData
  -> MarketState
  -> Recommendation
  -> CoachInput / InvestorAction
  -> DecisionReviewRecord
  -> Reports
```

Core rule:

No downstream engine should ignore data quality warnings.

========================================================
5. EXECUTION FLOW
========================================================

Default local execution:

```bash
python main.py
```

Expected behavior:

- Non-interactive market analysis runs automatically.
- If `coach.interactive_input` is true, CLI asks whether the recommendation was executed.
- If running in GitHub Actions, interactive input is disabled.
- All outputs are generated under `outputs/`.

Recommended CLI options for future milestones:

```bash
python main.py --mode daily
python main.py --mode monthly
python main.py --no-input
python main.py --date 2026-06-26
```

V1 can start with no CLI options and add these only when needed.

Application-level pseudocode:

```text
def run():
    config = load_config()
    portfolio = load_portfolio()
    prices = provider.fetch(config.tickers)
    quality = data_quality_engine.evaluate(prices)

    if quality.requires_fallback:
        fallback_prices = fallback_provider.fetch(quality.problem_tickers)
        prices = merge_prices(prices, fallback_prices)
        quality = data_quality_engine.evaluate(prices, fallback_used=True)

    market_state = market_engine.analyze(prices, quality)
    recommendation = decision_engine.recommend(market_state, portfolio, quality)
    investor_action = coach.ask_or_skip(recommendation)
    review_engine.record(recommendation, market_state, investor_action)
    review_engine.update_forward_returns(prices)
    reports.generate_all()
```

========================================================
6. CONFIGURATION DESIGN
========================================================

`config.yaml` should contain:

```yaml
app:
  timezone: Asia/Shanghai
  output_dir: outputs
  log_level: INFO
  run_mode: daily

data:
  primary_provider: yfinance
  fallback_provider: cache
  lookback_days: 260
  required_tickers:
    - 7709.HK
    - 7747.HK
    - 000660.KS
    - 005930.KS
    - MU
    - NVDA
    - MSFT
    - GOOGL
    - AMZN
    - META
    - AAPL
    - TSLA
    - QQQ
    - SOXX

data_quality:
  max_data_age_hours: 36
  max_missing_data_ratio: 0.05
  stale_price_days: 3
  abnormal_daily_move_pct: 20
  confidence_penalty:
    warning: 10
    degraded: 25
    failed: 50

baskets:
  ai:
    MSFT: 0.1667
    GOOGL: 0.1667
    AMZN: 0.1667
    META: 0.1667
    AAPL: 0.1667
    TSLA: 0.1667
  hbm:
    000660.KS: 0.50
    MU: 0.25
    005930.KS: 0.25

indicators:
  rsi_period: 14
  adx_period: 14
  atr_period: 14
  bollinger_period: 20
  bollinger_std: 2
  moving_averages: [20, 50, 100, 200]

classification:
  uptrend_min_trend_score: 70
  downtrend_max_trend_score: 35
  range_min_range_score: 65
  mixed_conflict_threshold: 2

decision:
  max_single_adjustment_shares: 100
  min_confidence_to_add: 65
  min_confidence_to_reduce: 55
  high_risk_score: 75
  uncertain_confidence_below: 45

review:
  forward_return_days: [1, 5, 20]
  reduce_success_threshold_pct: -2
  reduce_missed_opportunity_threshold_pct: 3
  hold_failure_threshold_pct: -5
  add_success_threshold_pct: 3

coach:
  interactive_input: true
  ask_reason_when_not_followed: true

reports:
  generate_excel: true
  generate_html: true
  generate_monthly: auto
```

`portfolio.yaml` should contain:

```yaml
base_currency: HKD
positions:
  7709.HK:
    shares: 300
    average_cost: 0
  7747.HK:
    shares: 0
    average_cost: 0
cash:
  HKD: 0
```

Configuration rules:

- All thresholds must have defaults.
- Unknown config keys should produce warnings, not crashes.
- Missing critical config should fail early with a clear message.

========================================================
7. FILE SCHEMA DESIGN
========================================================

`history.csv`

```text
run_id
run_timestamp
date
ticker
open
high
low
close
adj_close
volume
return_1d
return_5d
return_20d
source
data_quality_status
```

`data_quality_report.json`

```json
{
  "run_id": "2026-06-26T15:20:00+08:00",
  "status": "ok | warning | degraded | failed",
  "confidence_penalty": 0,
  "fallback_used": false,
  "missing_tickers": [],
  "stale_tickers": [],
  "abnormal_price_warnings": [],
  "messages": []
}
```

`latest_signal.json`

```json
{
  "run_id": "2026-06-26T15:20:00+08:00",
  "date": "2026-06-26",
  "market_mode": "Uptrend",
  "recommendation": "Hold",
  "confidence": 72,
  "risk_level": "Medium",
  "current_position": 300,
  "suggested_position": 300,
  "reasons": [],
  "warning_indicators": [],
  "data_quality_status": "ok",
  "data_quality_warnings": []
}
```

`decision_review.csv`

```text
run_id
date
market_mode
ai_basket_return_1d
ai_basket_return_5d
ai_basket_return_20d
hbm_basket_return_1d
hbm_basket_return_5d
hbm_basket_return_20d
risk_score
relative_ratio
samsung_sk_hynix_market_cap_ratio
trend_score
range_score
recommendation
confidence
reasons
suggested_position
current_position
executed
end_of_day_return
forward_return_1d
forward_return_5d
forward_return_20d
evaluation_1d
evaluation_5d
evaluation_20d
data_quality_status
confidence_penalty
```

`investor_actions.csv`

```text
run_id
date
recommendation
suggested_position
current_position
executed
actual_action
actual_position
reason
recorded_at
```

`execution.log`

```text
timestamp level module message
```

Duplicate prevention:

- Use `run_id` for each run.
- Use `date + scheduled_slot` or `run_id` for intraday runs.
- Daily review records should upsert by `date` for daily mode.
- Intraday history can append by `run_id`.

========================================================
8. DATA QUALITY ENGINE DESIGN
========================================================

Purpose:

Protect the Decision Engine from bad market data.

Input:

- Raw market prices.
- Required ticker list.
- Configured thresholds.
- Provider metadata.

Output:

- `DataQualityReport`
- `ValidatedMarketData`
- confidence penalty

Recommended model:

```text
DataQualityStatus:
  OK
  WARNING
  DEGRADED
  FAILED
```

Checks:

1. Freshness check

- Detect latest available date per ticker.
- Compare with expected market date and max data age.
- Mark stale when data is older than threshold.

2. Missing ticker check

- Verify all required tickers exist.
- Track optional vs required tickers separately in future versions.

3. Missing row ratio check

- For each ticker, calculate missing rows in lookback window.
- Warn or degrade based on configured ratio.

4. Abnormal price check

- Detect zero or negative prices.
- Detect abnormal daily moves above configured threshold.
- Warn rather than discard unless clearly invalid.

5. Stale price check

- Detect repeated close prices over configured number of days.
- Especially useful for holidays, suspended tickers, or failed provider data.

6. Fallback handling

- If required tickers are missing or stale, request fallback.
- Record whether fallback was used.
- Do not hide fallback usage from the user.

Confidence penalty:

```text
OK: 0
WARNING: configurable small penalty
DEGRADED: configurable medium penalty
FAILED: configurable large penalty, prefer Uncertain
```

Decision behavior:

- `OK`: normal recommendation.
- `WARNING`: recommendation allowed, but explain warning.
- `DEGRADED`: reduce confidence and prefer smaller position changes.
- `FAILED`: output Watch or Uncertain unless there is enough valid data to make a conservative risk-reduction recommendation.

Test cases:

- All tickers fresh.
- One optional ticker missing.
- One required ticker missing.
- Stale close prices.
- Abnormal price spike.
- Fallback used successfully.
- Fallback unavailable.

========================================================
9. DECISION REVIEW ENGINE DESIGN
========================================================

Purpose:

Measure decision quality over time, not only portfolio return.

Input:

- `Recommendation`
- `MarketState`
- `DataQualityReport`
- `InvestorAction`
- Historical forward returns

Output:

- `decision_review.csv`
- monthly review files
- review statistics for dashboard

Lifecycle:

1. On recommendation date, create a review record.
2. Same day, fill end-of-day return if available.
3. After 1 trading day, fill 1-day forward return and evaluation.
4. After 5 trading days, fill 5-day forward return and evaluation.
5. After 20 trading days, fill 20-day forward return and evaluation.
6. Monthly, aggregate review records into performance statistics.

Evaluation statuses:

- Pending
- Successful
- Failed
- Missed Opportunity
- Avoided Loss
- Neutral

Example rule direction:

- `Reduce`: successful if forward return is negative beyond threshold.
- `Reduce`: missed opportunity if forward return is strongly positive.
- `Hold`: successful if trend continues or drawdown remains controlled.
- `Hold`: failed if large correction follows.
- `Add Back`: successful if forward return is positive beyond threshold.
- `Add Back`: failed if large decline follows.
- `Watch` or `Uncertain`: successful if conflicting or poor-quality data justified caution.

Statistics:

- Recommendation Accuracy
- Risk Management Accuracy
- Trend Classification Accuracy
- Range Classification Accuracy
- Position Adjustment Accuracy
- Average Forward Return by recommendation type
- Win Rate
- Average Gain
- Average Loss
- Maximum Consecutive Errors
- Maximum Consecutive Correct Decisions

Design rule:

The Review Engine should not know how Excel or HTML works. It produces records and statistics only.

========================================================
10. INVESTMENT COACH WORKFLOW
========================================================

Purpose:

Record the gap between engine recommendation and investor action.

V1 local CLI workflow:

```text
Today's Recommendation:
Reduce 100 Shares

Did you execute it? [y/N/skip]
```

If yes:

```text
executed = true
actual_action = recommendation
actual_position = suggested_position
reason = ""
```

If no:

```text
What did you actually do?
What is your actual position?
Reason? optional
```

If skipped:

```text
executed = blank
actual_action = blank
actual_position = blank
reason = "not recorded"
```

GitHub Actions workflow:

- Interactive input disabled.
- Recommendation is generated.
- Investor action remains blank until manually recorded later.

Behavior analysis:

- Compare recommendation vs action.
- Calculate follow rate.
- Calculate actual return.
- Estimate return if following engine.
- Calculate behavior difference.
- Identify repeated behavior patterns.

Tone:

- The coach should be factual and non-punitive.
- It should help discipline, not shame the investor.

========================================================
11. GITHUB ACTIONS WORKFLOW
========================================================

GitHub Actions cron is UTC.

Asia/Shanghai and Hong Kong time are UTC+8.

Target local run times:

- 09:30 -> 01:30 UTC
- 11:30 -> 03:30 UTC
- 13:30 -> 05:30 UTC
- 15:20 -> 07:20 UTC

Workflow responsibilities:

```text
1. Checkout repository
2. Set up Python
3. Install requirements
4. Run python main.py --no-input
5. Validate output files exist
6. Upload artifacts or commit generated files
7. Publish dashboard.html to GitHub Pages
```

Recommended workflow file:

```text
.github/workflows/daily-aios.yml
```

Schedule:

```yaml
on:
  schedule:
    - cron: "30 1 * * 1-5"
    - cron: "30 3 * * 1-5"
    - cron: "30 5 * * 1-5"
    - cron: "20 7 * * 1-5"
  workflow_dispatch:
```

Notes:

- V1 should not over-engineer market holiday detection.
- If market data is stale because of a holiday, Data Quality Engine should warn and lower confidence.
- Later versions can add exchange calendar support.

========================================================
12. FUTURE EXPANSION PLAN
========================================================

Near-term:

- Add more robust provider fallback.
- Add local cache reuse when provider fails.
- Add manual investor action update command.
- Add monthly review charts.

Medium-term:

- Add exchange calendar support.
- Add better portfolio return calculation.
- Add multi-account portfolio tracking.
- Add rule effectiveness ranking.
- Add indicator usefulness scoring.

Long-term:

- Add AI-assisted monthly narrative analysis.
- Add lightweight hosted action input.
- Add automatic GitHub Pages update workflow.
- Add optional broker export import.
- Add richer investment coach behavior pattern detection.

Non-goals for V1:

- No real broker trading.
- No automatic order execution.
- No database.
- No web server.
- No machine learning model.
- No high-frequency trading.

========================================================
13. DEVELOPMENT MILESTONES
========================================================

Milestone 0: Architecture Approval

Goal:

- Approve this architecture before coding.

Deliverables:

- `outputs/aios_architecture_design_v1.md`

Gate:

- Architecture covers all 13 requested sections.
- User approves the architecture.

Milestone 1: Project Skeleton and Configuration

Goal:

- Create runnable project skeleton.
- Load `config.yaml` and `portfolio.yaml`.
- Set up logging and output paths.

Deliverables:

- `main.py`
- package structure
- `config.yaml`
- `portfolio.yaml`
- `requirements.txt`
- basic tests

Run gate:

```bash
python main.py
pytest
```

Expected generated files:

- `outputs/execution.log`

Milestone 2: Market Data Fetching and Storage

Goal:

- Download or load market data.
- Normalize ticker data.
- Write `history.csv`.

Deliverables:

- provider interface
- yfinance provider
- CSV storage
- sample fixture tests

Run gate:

```bash
python main.py
pytest
```

Expected generated files:

- `outputs/history.csv`
- `outputs/execution.log`

Milestone 3: Data Quality Engine

Goal:

- Validate data freshness, missing tickers, stale data, and abnormal prices.
- Generate confidence penalty.

Deliverables:

- `DataQualityReport`
- quality checks
- fallback hook
- tests for bad data cases

Run gate:

```bash
python main.py
pytest
```

Expected generated files:

- `outputs/data_quality_report.json`
- `outputs/history.csv`
- `outputs/execution.log`

Milestone 4: Market Engine

Goal:

- Calculate indicators, baskets, scores, and market mode.

Deliverables:

- indicators
- basket returns
- scoring
- market classifier
- tests using fixtures

Run gate:

```bash
python main.py
pytest
```

Expected generated files:

- updated `outputs/history.csv`
- `outputs/data_quality_report.json`

Milestone 5: Decision Engine

Goal:

- Generate explainable daily recommendation.
- Apply data quality confidence penalty.

Deliverables:

- recommendation model
- rule engine
- `latest_signal.json`
- tests for Uptrend, Range, Downtrend, Mixed, and poor data quality

Run gate:

```bash
python main.py
pytest
```

Expected generated files:

- `outputs/latest_signal.json`
- `outputs/data_quality_report.json`
- `outputs/history.csv`

Milestone 6: Investment Coach

Goal:

- Ask whether recommendation was executed.
- Record investor action locally.

Deliverables:

- CLI prompt
- non-interactive skip mode
- `investor_actions.csv`
- tests for yes/no/skip paths

Run gate:

```bash
python main.py
python main.py --no-input
pytest
```

Expected generated files:

- `outputs/investor_actions.csv`
- `outputs/latest_signal.json`

Milestone 7: Decision Review Engine

Goal:

- Record daily recommendation context.
- Update forward returns and evaluations.

Deliverables:

- `decision_review.csv`
- evaluation rules
- review statistics
- tests for successful, failed, missed opportunity, pending

Run gate:

```bash
python main.py --no-input
pytest
```

Expected generated files:

- `outputs/decision_review.csv`
- `outputs/investor_actions.csv`

Milestone 8: Excel Dashboard

Goal:

- Generate daily working Excel workbook.

Deliverables:

- `investment_dashboard.xlsx`
- sheets:
  - Dashboard
  - Portfolio
  - Technical
  - Data Quality
  - AI_HBM_History
  - Trade Journal
  - Decision Review
  - Investor Behavior
  - Performance
  - Monthly Review

Run gate:

```bash
python main.py --no-input
pytest
```

Expected generated files:

- `outputs/investment_dashboard.xlsx`

Manual verification:

- Open workbook.
- Confirm sheets exist.
- Confirm formatting and filters are readable.

Milestone 9: HTML Dashboard

Goal:

- Generate responsive HTML dashboard.

Deliverables:

- `dashboard.html`
- Jinja2 template
- mobile and desktop layout
- dark mode

Run gate:

```bash
python main.py --no-input
pytest
```

Expected generated files:

- `outputs/dashboard.html`

Manual verification:

- Open dashboard locally.
- Confirm recommendation, data quality warnings, and review stats render.

Milestone 10: Monthly Review

Goal:

- Generate monthly review Excel and HTML.

Deliverables:

- `monthly_review.xlsx`
- `monthly_review.html`
- best/worst recommendations
- accuracy trends
- behavior difference analysis

Run gate:

```bash
python main.py --mode monthly --no-input
pytest
```

Expected generated files:

- `outputs/monthly_review.xlsx`
- `outputs/monthly_review.html`

Milestone 11: GitHub Actions

Goal:

- Run automatically at scheduled times.
- Publish dashboard output.

Deliverables:

- `.github/workflows/daily-aios.yml`
- output validation step

Run gate:

```bash
python main.py --no-input
pytest
```

Additional verification:

- Manual `workflow_dispatch` succeeds.
- Output artifacts are visible.

Milestone 12: Stabilization and Documentation

Goal:

- Make the system maintainable for long-term use.

Deliverables:

- README usage guide
- file schema documentation
- troubleshooting guide
- final test pass

Run gate:

```bash
python main.py --no-input
pytest
```

Completion criteria:

- All required outputs generated.
- All tests pass.
- Memory and runtime remain within target.
- Recommendation remains explainable.
- Data quality warnings are visible.
- Review Engine and Investment Coach outputs are traceable.

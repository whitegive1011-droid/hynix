# AI Investment Operating System (AIOS)

You are my Lead Software Architect and Senior Python Engineer.

We are going to build a long-term personal investment system.

This is a real software engineering project, not a coding exercise.

The project name is:

AI Investment Operating System (AIOS)

========================================================
PROJECT BACKGROUND
========================================================

I am an individual investor.

My main investment focus is AI infrastructure and HBM.

Current core holdings:

- 7709.HK (CSOP Daily 2x Long SK Hynix)
- Future: 7747.HK (CSOP Daily 2x Long Samsung)

I also continuously monitor:

- SK Hynix
- Samsung Electronics
- Micron
- NVIDIA
- Microsoft
- Google
- Amazon
- Meta
- Apple
- Tesla
- QQQ
- SOXX

The purpose of this software is NOT predicting the market.

Its purpose is:

- reduce emotional trading
- improve consistency
- standardize decision making
- accumulate trading knowledge
- evaluate decision quality over time
- understand my own investment behavior
- become my long-term investment assistant

========================================================
PRODUCT DEFINITION
========================================================

AIOS is not only a dashboard.

AIOS is a lightweight personal investment operating system.

It has three layers:

Layer 1: Market Engine

- Understand what the market is doing.
- Calculate indicators, returns, relative strength, valuation ratios, risk, trend, range, momentum, and volatility.
- Depend on a Data Quality Engine before trusting market data.

Layer 2: Decision Engine

- Decide what should be done today.
- Convert market state into practical, gradual, explainable trading recommendations.

Layer 3: Review Engine

- Evaluate whether previous decisions were good.
- Measure decision quality, recommendation quality, and investor discipline.
- Identify which rules are useful, which rules are weak, and when the investor deviates from the system.

The Review Engine is the soul of this project.

Many investment tools can say what to do today.

AIOS must also help me understand whether yesterday's decision was correct, whether the rule behind it was useful, and whether my own behavior followed the system.

========================================================
TARGET PLATFORM
========================================================

Development Machine:

MacBook Air M1

8GB RAM

256GB SSD

The software MUST remain lightweight.

Requirements:

- Python only
- No Docker
- No database
- No React
- No Redis
- No FastAPI
- No unnecessary frameworks

Prefer:

- pandas
- numpy
- yfinance
- matplotlib
- openpyxl
- jinja2
- pyyaml

Everything should run by:

python main.py

Performance requirements:

- Memory usage <500MB
- Execution time <30 seconds

========================================================
SYSTEM PHILOSOPHY
========================================================

This project is NOT a quantitative trading system.

It is a decision support system.

Never overfit.

Never force predictions.

If indicators disagree, output:

UNCERTAIN

instead of pretending certainty.

Every recommendation must be explainable.

Every metric must have a documented reason for existence.

Every trading suggestion must be traceable back to objective rules.

The system should help the investor understand why a decision is made, not simply what decision to make.

This system should never become a black box.

The goal is not to improve only one trade.

The goal is to make every decision evidence-based, reviewable, and continuously improvable.

========================================================
MAIN DAILY OUTPUT
========================================================

Every trading day the software should answer only one question:

"What should I do today?"

Examples:

- Hold
- Reduce 100 Shares
- Reduce to 200 Shares
- Add Back 100 Shares
- Watch
- High Risk
- Uncertain

Every recommendation must include:

- Recommendation
- Confidence
- Reasons
- Risk Level
- Suggested Position
- Current Position
- Market Mode
- Key supporting indicators
- Key warning indicators

The system should behave like an investment coach.

It should not only output:

Reduce 100 Shares

It should also ask:

Today's Recommendation:

Reduce 100 Shares

Did you execute it?

- Yes
- No

Reason (optional):

The investor's answer must be recorded and used by the Review Engine.

========================================================
CURRENT STRATEGY
========================================================

The software must automatically determine whether the market is:

- Uptrend
- Range
- Downtrend
- Mixed

Trend market:

- Hold
- Avoid unnecessary trading
- Let the trend continue

Range market:

- Use Bollinger Band + RSI partial T strategy
- Add gradually near lower range
- Reduce gradually near upper range

Downtrend:

- Reduce leverage
- Reduce exposure gradually
- Avoid forced liquidation risk

Mixed market:

- Lower confidence
- Prefer Watch or Uncertain
- Avoid large position changes

Never recommend:

- All In
- All Out

Always recommend gradual position adjustment.

========================================================
CORE INDICATORS
========================================================

AI Basket:

Equal Weight:

- MSFT
- GOOGL
- AMZN
- META
- AAPL
- TSLA

HBM Basket:

- 50% SK Hynix
- 25% Micron
- 25% Samsung

Calculate:

- 1D Return
- 5D Return
- 20D Return
- Relative Ratio
- Samsung / SK Hynix Market Cap Ratio
- Risk Score
- Trend Score
- Momentum Score
- Range Score
- Volatility Score

Technical Indicators:

- MA
- EMA
- MACD
- RSI14
- ADX14
- ATR14
- Bollinger Bands
- Volume
- Gap
- Support
- Resistance

========================================================
DATA QUALITY ENGINE
========================================================

The Data Quality Engine is responsible for validating market data before it is used by the Market Engine or Decision Engine.

It is a first-class reliability module.

Bad data should never silently create a confident recommendation.

Responsibilities:

- Verify data freshness
- Detect missing tickers
- Detect abnormal prices
- Detect stale market data
- Use fallback provider if needed
- Warn user when recommendation confidence should be reduced

The Data Quality Engine should output:

- Data quality status
- Missing ticker list
- Stale ticker list
- Abnormal price warnings
- Fallback provider usage
- Confidence penalty
- Human-readable warning messages

If data quality is poor, the system should prefer:

- Watch
- Uncertain
- Lower confidence
- Explicit warning in Excel, HTML, JSON, and logs

The Data Quality Engine should be configurable through config.yaml.

Examples of configurable checks:

- Maximum allowed data age
- Required tickers
- Maximum allowed daily price move before warning
- Maximum allowed missing data ratio
- Primary data provider
- Fallback data provider
- Confidence penalty rules

========================================================
MARKET ENGINE
========================================================

The Market Engine is responsible for market data and indicator calculation.

Responsibilities:

- Download market data
- Normalize ticker symbols
- Consume validated data from the Data Quality Engine
- Calculate basket returns
- Calculate technical indicators
- Calculate market mode
- Calculate risk, trend, momentum, range, and volatility scores
- Calculate relative ratios
- Output structured market state for the Decision Engine

The Market Engine should not decide what to buy or sell.

It only describes the market.

========================================================
DECISION ENGINE
========================================================

The Decision Engine is responsible for converting market state into a daily recommendation.

Responsibilities:

- Read market state from the Market Engine
- Read data quality status from the Data Quality Engine
- Read current portfolio position
- Apply strategy rules
- Generate recommendation
- Generate confidence level
- Generate reasons
- Generate risk level
- Generate suggested position
- Explain which rules were triggered
- Reduce confidence when data quality is weak
- Include data quality warnings in recommendation reasons

The Decision Engine must be rule-based at first.

It must be easy to inspect, test, and modify.

It should never hide reasoning inside an opaque model.

========================================================
DECISION REVIEW ENGINE
========================================================

One of the core purposes of this system is continuous improvement.

The engine must not only generate trading recommendations.

It must also evaluate its own recommendations over time.

For every trading day, automatically record:

- Date
- Market Mode
- AI Basket Return
- HBM Basket Return
- Risk Score
- Relative Ratio
- Samsung / SK Hynix Market Cap Ratio
- Trend Score
- Range Score
- Recommendation
- Confidence
- Reasons
- Suggested Position
- Current Position
- Whether recommendation was executed (manual input)
- End-of-day return
- 1-day forward return
- 5-day forward return
- 20-day forward return

========================================================
RECOMMENDATION EVALUATION
========================================================

Evaluate whether the recommendation was correct.

Examples:

Recommendation:

Reduce 100 Shares

If the market declined afterwards, mark recommendation as:

Successful

If the market rallied strongly afterwards, mark recommendation as:

Missed Opportunity

Recommendation:

Hold

If the trend continued, mark recommendation as:

Successful

If the market entered a large correction, mark recommendation as:

Failed

The evaluation rules must be documented, configurable, and testable.

The system should support multiple evaluation horizons:

- End of day
- 1 trading day forward
- 5 trading days forward
- 20 trading days forward

========================================================
PERFORMANCE STATISTICS
========================================================

Automatically calculate:

- Recommendation Accuracy
- Risk Management Accuracy
- Trend Classification Accuracy
- Range Classification Accuracy
- Position Adjustment Accuracy
- Average Forward Return after each recommendation type
- Win Rate
- Average Gain
- Average Loss
- Maximum Consecutive Errors
- Maximum Consecutive Correct Decisions

The system should show both short-term and long-term review statistics.

========================================================
INVESTOR BEHAVIOR ANALYSIS
========================================================

The system should also evaluate the investor.

Track:

- Whether recommendations were followed
- If not followed, record actual position
- If not followed, record actual action
- Difference between Engine Recommendation and Investor Action
- Optional investor reason

Generate statistics such as:

- Recommendation Follow Rate
- Return if Following Engine
- Actual Return
- Behavior Difference
- Missed Gain from Not Following Engine
- Loss Avoided by Not Following Engine

Example long-term output:

- Engine Recommendation Accuracy: 81%
- Your Follow Rate: 63%
- If fully followed: +18.4%
- Actual Return: +9.7%
- Difference: -8.7%

This is one of the most valuable parts of the system.

A normal trading app records trades.

AIOS must record the relationship between recommendation, investor action, and final outcome.

========================================================
INVESTMENT COACH
========================================================

The Investment Coach is the user-facing behavior layer of the Review Engine.

Every trading day it should ask:

Today's Recommendation:

[Recommendation]

Did you execute it?

- Yes
- No

If No, ask:

- What did you actually do?
- What is your actual position?
- Why did you choose differently? (optional)

The Investment Coach should help the investor become more disciplined without being punitive.

It should identify behavior patterns such as:

- Often reducing too late
- Often refusing to reduce during high-risk periods
- Often adding too early in downtrends
- Often ignoring Uncertain signals
- Often missing Add Back opportunities after corrections

The Investment Coach should provide review insights, not emotional judgment.

========================================================
MONTHLY REVIEW
========================================================

Automatically generate:

- monthly_review.xlsx
- monthly_review.html

Include:

- Best Recommendations
- Worst Recommendations
- Most Accurate Indicators
- Least Useful Indicators
- Largest Drawdown
- Largest Missed Opportunity
- Recommendation Accuracy Trend
- Portfolio Growth
- Recommendation Follow Rate
- Return if Following Engine
- Actual Return
- Behavior Difference
- Coach Summary

The monthly review should answer:

- Which rules worked?
- Which rules failed?
- Which market modes were easiest to classify?
- Which market modes caused the most errors?
- Did I follow the system?
- Did not following the system help or hurt?
- What should be improved next month?

========================================================
LEARNING PHILOSOPHY
========================================================

The objective of this module is NOT machine learning.

It is systematic self-review.

The engine should continuously improve by measuring Decision Quality instead of only measuring Portfolio Return.

The goal is to become more disciplined over time.

Future versions may include AI-assisted analysis.

However, the first version should be transparent, rule-based, explainable, and easy to audit.

========================================================
ENGINEERING PRINCIPLE FOR REVIEW ENGINE
========================================================

The Decision Review Engine is a first-class module.

Design it with clean interfaces.

Future versions may replace rule-based evaluation with AI-assisted analysis without changing the overall architecture.

The Review Engine should not be a few formulas hidden inside the Excel export.

It should have its own:

- Data model
- Service layer
- Evaluation rules
- Output schema
- Tests
- Monthly report generator

========================================================
OUTPUT FILES
========================================================

Generate:

- investment_dashboard.xlsx
- dashboard.html
- latest_signal.json
- history.csv
- data_quality_report.json
- decision_review.csv
- investor_actions.csv
- monthly_review.xlsx
- monthly_review.html
- execution.log

The CSV and JSON files are the lightweight data store.

No database should be used in the first version.

========================================================
EXCEL
========================================================

The Excel workbook should become my daily working interface.

Include:

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

Use:

- Professional formatting
- Charts
- Conditional formatting
- Freeze header
- Auto filter

========================================================
HTML
========================================================

Generate a responsive HTML dashboard.

Optimized for:

- Desktop
- Phone
- Dark mode

The HTML dashboard should include:

- Today's recommendation
- Confidence
- Reasons
- Risk level
- Market mode
- Current position
- Suggested position
- Data quality status
- Data quality warnings
- Investment Coach execution question
- Recent recommendation accuracy
- Recent follow rate
- Key charts

========================================================
GITHUB
========================================================

The software will eventually run automatically using GitHub Actions.

GitHub Actions should run at:

- 09:30
- 11:30
- 13:30
- 15:20

Every trading day.

Automatically:

- Download data
- Validate data quality
- Use fallback data provider if needed
- Update indicators
- Generate dashboard
- Update Excel
- Generate latest_signal.json
- Generate data_quality_report.json
- Update review history
- Generate monthly review when appropriate
- Publish dashboard.html to GitHub Pages

The dashboard should be viewable from my office computer and phone without running my local Mac.

Manual investor input may still be entered locally at first.

Future versions may support a lightweight web form or GitHub Pages input workflow, but do not over-engineer this in the first version.

========================================================
DATA STORAGE
========================================================

Because this project must stay lightweight, use files instead of a database.

Recommended files:

- config.yaml
- portfolio.yaml
- history.csv
- data_quality_report.json
- decision_review.csv
- investor_actions.csv
- latest_signal.json
- execution.log

All file schemas must be documented.

The system must tolerate missing files on first run.

The system must append new records safely.

The system must avoid duplicating records for the same date and run time.

========================================================
ENGINEERING REQUIREMENTS
========================================================

The codebase must be:

- Readable
- Maintainable
- Object Oriented where useful
- PEP8 compliant
- Logging enabled
- Type hinted
- Unit tested
- Clean architecture
- Configuration driven

Everything configurable through:

config.yaml

The architecture should separate:

- Data fetching
- Data quality validation
- Indicator calculation
- Market classification
- Recommendation generation
- Decision review
- Investor behavior tracking
- Report generation
- File storage
- Configuration

========================================================
IMPORTANT
========================================================

Do NOT start coding immediately.

First, analyze all requirements.

Then design the complete software architecture.

Output:

1. Project architecture
2. Directory structure
3. Module responsibilities
4. Data flow
5. Execution flow
6. Configuration design
7. File schema design
8. Data Quality Engine design
9. Decision Review Engine design
10. Investment Coach workflow
11. GitHub Actions workflow
12. Future expansion plan
13. Development milestones

Only after the architecture is approved, begin implementation milestone by milestone.

Each milestone must be completed, run successfully, and tested before moving to the next milestone.

For every milestone:

- Define the milestone goal
- Implement only the scoped functionality
- Run the application end to end where applicable
- Run unit tests
- Verify generated files
- Fix failures before continuing
- Document what passed and what remains

Never build everything at once.

The goal is to create software that I can continuously use and maintain for many years.

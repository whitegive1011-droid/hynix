from pathlib import Path

from aios.app.runner import AiosRunner


def test_runner_creates_execution_log(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    portfolio_path = tmp_path / "portfolio.yaml"
    output_dir = tmp_path / "outputs"

    config_path.write_text(
        f"""
app:
  output_dir: {output_dir}
  log_level: INFO
data:
  primary_provider: csv
  lookback_days: 5
  required_tickers:
    - 7709.HK
  csv_path: tests/fixtures/market_prices_sample.csv
coach:
  interactive_input: false
""",
        encoding="utf-8",
    )
    portfolio_path.write_text(
        """
base_currency: HKD
positions:
  7709.HK:
    shares: 10
    average_cost: 1
cash:
  HKD: 100
""",
        encoding="utf-8",
    )

    runner = AiosRunner(
        config_path=config_path,
        portfolio_path=portfolio_path,
        no_input=True,
    )

    assert runner.run() == 0
    log_path = output_dir / "execution.log"
    history_path = output_dir / "history.csv"
    assert log_path.exists()
    assert history_path.exists()
    assert "Market history written" in log_path.read_text(encoding="utf-8")

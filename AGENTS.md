# Repository Guidelines

## Project Structure & Module Organization
`bot.py` is the entry point and wires Telegram handlers, schedulers, and strategy classes. Supporting modules (`handlers.py`, `investor_manager.py`, `data_loader.py`, `utils.py`) live at the repo root and should remain focused and reusable. Strategies reside in `strategies/` (paper tiers plus `live.py`), persistent assets and logs live in `data/`, and automated tests live in `tests/` with parity naming (`test_handlers.py`, `test_strategy.py`) plus the top-level `test_rebalance_paper_low.py`.

## Build, Test & Development Commands
Use `python -m venv .venv && source .venv/bin/activate` to create the environment, then `python -m pip install -r requirements.txt` to pull dependencies. Run the bot locally with `python bot.py` once a `.env` file supplies the required keys. Execute `python -m pytest` for the full suite or `python -m pytest -m "not integration"` for the fast path; add `-k <pattern>` for targeted debugging.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation, type hints, and concise docstrings as shown in `bot.py` and `strategies/paper_low.py`. Keep strategy classes mostly stateless, inject Alpaca clients, and expose consistent method names (`get_signals`, `rebalance`) so they can be hot-swapped. Favor descriptive snake_case for functions and constants (`REBALANCE_INTERVAL_DAYS`) and always log via the configured `logging` handlers instead of printing.

## Testing Guidelines
Pytest is the single harness. Mark live-credential scenarios with `@pytest.mark.integration` (see `pytest.ini`) and default CI/local runs to `-m "not integration"`. Name tests after the behavior under test and co-locate fixtures in `tests/conftest.py` to share Alpaca client stubs. When adding a strategy, cover signal math with unit tests and guard one integration scenario behind the marker.

## Commit & Pull Request Guidelines
Commits follow short, imperative subjects (`fix strategy config`, `add more strategy`); include extra context or issue links in the body when needed. Every PR should state the problem, outline the solution, and list the commands executed (at minimum `python -m pytest -m "not integration"`). Attach screenshots or log excerpts whenever Telegram commands, schedulers, or investor exports change, and call out any new configuration keys.

## Security & Configuration Tips
Populate `.env` using the keys enumerated in `config.py` (Telegram token, Alpaca API/secret pairs per account tier, `ENVIRONMENT`). Never commit credentials or generated artifacts from `data/`; if you add required keys, document them in a tracked `.env.example` so others can provision safely. Rotate `ADMIN_IDS` when operator access changes, and keep paper/live keys segregated by strategy constant.

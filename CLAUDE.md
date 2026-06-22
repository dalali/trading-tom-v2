# CLAUDE.md

## Project
trading-tom-v2 — Multi-user paper-trading platform — admin manages users/funds, shared day/swing trading engine, per-trade history, admin-run simulations

## Tech Stack
Python BE + React FE + Docker Compose

## Local Setup
```bash
cp .env.example .env   # edit as needed
./run.sh start
```

## Key Commands
- `./run.sh start` — start the app
- `./run.sh test`  — run tests
- `./run.sh logs`  — tail logs
- `./run.sh shell` — container shell

## Rules
- Keep changes minimal and focused
- Run tests before committing

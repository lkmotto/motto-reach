# AGENTS.md for motto-reach

## Overview
Consolidated repository for Motto reach operations: distribution and outreach. Handles outbound communication and content distribution across channels.

## Development

### Setup
```bash
uv sync
```

### Run
```bash
uv run python -m distribution
uv run python -m outreach
```

### Test
```bash
uv run pytest
```

### Lint
```bash
uv run ruff check .
```

### Type Check
```bash
uv run mypy .
```

## Deployment
Deployed via Docker to Northflank. Uses Motto fleet infrastructure for channel management and content distribution.

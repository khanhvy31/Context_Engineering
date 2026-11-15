# Brightcart Analytics: project context

## What this project is
SQLite analytics warehouse for Brightcart (online store). Database: `data/brightcart.db`.

## Where things are (read only what you need)
- Table schemas: @docs/data_dictionary.md
- Metric definitions (source of truth): @docs/metrics/metric_definitions.md
- 2026 targets: `docs/reports/q3_2026_business_review.md` (long; use the `report-reader` subagent)
- Do NOT read: `data/raw_exports/`, `docs/archive/` (irrelevant to metrics questions)
- Do NOT use: `docs/metrics/metrics_glossary.md` (outdated, revenue-based)

## Business rules (always apply)
- Refund rate = refunded orders / completed orders, grouped by ORDER date
- Exclude test accounts: `users.is_test = 1`
- Exclude cancelled orders (`orders.status = 'cancelled'`)

## How to answer
- Run queries with `sqlite3 data/brightcart.db` (or Python's sqlite3)
- Answer in short bullet points, then the SQL in a code block,
  then one line: "Definition used: metric_definitions.md (order-based, test accounts excluded)"

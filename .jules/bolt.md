## 2024-06-14 - Missing SQLite Index for Time-Series Data
**Learning:** The dashboard uses multiple queries with `ORDER BY timestamp DESC LIMIT 1` over an SQLite database that stores a large amount of message payloads. Without an index on `timestamp`, this leads to full table scans or sorting in a temporary B-TREE for every single latest metric shown on the dashboard.
**Action:** Add `CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC)` in `catcher/catcher.py` to make time-based lookups instant.

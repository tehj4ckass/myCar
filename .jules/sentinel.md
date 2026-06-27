## 2024-06-27 - SQL Injection via Environment Variable in SQLite Queries
**Vulnerability:** SQL Injection in SQLite queries using f-strings with environment variables (VIN) inside string literals in dashboard/pages/laden.py and dashboard/pages/trips.py.
**Learning:** Even inputs sourced from the environment (like VIN) can be manipulated or contain characters that break SQL syntax or lead to SQL injection. Environment variables should be treated as untrusted input.
**Prevention:** Strictly use parameterized queries with `?` placeholders and SQLite string concatenation (like `||`) instead of Python string formatting/f-strings for all user or environment inputs.

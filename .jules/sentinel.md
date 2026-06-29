
## 2024-05-24 - Parameterize Queries for Environment Variables
**Vulnerability:** SQL injection risk due to f-strings interpolating `VIN` directly into SQLite queries.
**Learning:** Even inputs sourced from environment variables must be parameterized, as environment variables can be manipulated.
**Prevention:** Ensure all database queries strictly use parameterized queries (e.g., using `?` placeholders and SQLite string concatenation like `||`) to prevent SQL injection risks.

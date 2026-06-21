## 2024-05-18 - Parameterized Queries for Environment Variables in SQLite
**Vulnerability:** The `VIN` environment variable was directly interpolated into SQL query strings using python f-strings (e.g. `f"SELECT ... LIKE '%{VIN}/...' "`) leading to a SQL injection vulnerability.
**Learning:** Environment variables can still act as attack vectors. Directly inserting them via string interpolation into SQL queries creates SQL injection vulnerabilities even if they are not direct user input.
**Prevention:** Always use parameterized queries for all inputs, including environment variables. In SQLite, use string concatenation `||` with placeholders (`?`) for pattern matching (e.g., `"SELECT ... LIKE '%' || ? || '/...' "`, `(VIN,)`) instead of string interpolation.

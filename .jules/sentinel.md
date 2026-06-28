## 2024-06-28 - Parameterized Queries in SQLite
**Vulnerability:** SQL Injection via f-strings in LIKE queries. The code was using string interpolation with environmental variables (like VIN) to build queries such as conn.execute(f"SELECT ... WHERE topic LIKE '%{VIN}/charging/power'").
**Learning:** SQLite parameterization using ? placeholders does not work natively inside string literals for LIKE clauses if written as LIKE '%?%'. Parameterized string interpolation (f-strings) introduces SQL injection risks.
**Prevention:** To safely parameterize LIKE queries, use string concatenation in SQL, e.g., LIKE '%' || ? || '/charging/power' and pass the user input as a parameter (VIN,) to the execute call.

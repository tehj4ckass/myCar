## 2024-05-18 - Environment Variables in SQL Queries
**Vulnerability:** SQL Injection via Environment Variables
**Learning:** Even variables that appear 'safe' or are read from environment configurations (like `VIN`) can introduce SQL injection vulnerabilities when interpolated directly into SQL query strings (e.g., using Python f-strings) rather than being passed as parameterized inputs.
**Prevention:** Always use SQLite query parameters (like `?`) combined with string concatenation functions (like `||`) when inserting variables into SQL commands, irrespective of their origin.

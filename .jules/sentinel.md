## 2024-06-23 - Prevent SQL Injection from Environment Variables
**Vulnerability:** SQL Injection via f-strings containing environment variables (e.g., `VIN = os.environ.get("VIN")`) being used to construct SQLite queries.
**Learning:** Even though environment variables like `VIN` might seem benign, they are user-controllable input if they come from configuration or the environment. Constructing SQL queries via string formatting with these variables creates a significant SQL injection vulnerability.
**Prevention:** Always use parameterized SQL queries (e.g., using `?` placeholders) and use SQLite string concatenation (`||`) when dynamic parameters are part of a `LIKE` pattern or complex topic string.

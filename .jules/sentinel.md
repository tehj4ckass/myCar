## 2023-10-27 - SQL Injection via Environment Variable
**Vulnerability:** SQL Injection in SQLite queries where `VIN` environment variable is directly formatted into SQL strings.
**Learning:** Even internal-seeming inputs like environment variables can be injection vectors if they are directly substituted into SQL strings, especially since an attacker may control the environment.
**Prevention:** Always use parameterized queries `?` with execute calls and SQLite string concatenation (like `'%' || ? || '/topic'`) to format query components, avoiding standard string interpolation.

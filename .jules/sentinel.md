## 2026-06-15 - [Fix SQL Injection in Streamlit Dashboard]
**Vulnerability:** Found SQL injection vulnerabilities in `dashboard/pages/laden.py` and `dashboard/pages/trips.py`. Unsafe direct f-string interpolations were used to pass environment variables into `conn.execute()` queries.
**Learning:** It is common for internal tools and dashboards to implicitly trust variables coming from `.env` files or environment variables. This creates a security risk if the environment is ever tampered with or populated with malicious input.
**Prevention:** Use query parameterization (e.g. `?` placeholders) for all variable interpolations in SQLite queries, including variables sourced from the environment.

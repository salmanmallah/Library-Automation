# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 3.0.x   | :white_check_mark: |
| 2.x     | :x:                |
| < 2.0   | :x:                |

---

## Security Architecture & Defenses

1. **Password Storage:**
   All user and administrator credentials are encrypted using **Argon2id** (`argon2-cffi`), resisting GPU/ASIC brute-force and side-channel attacks. Plaintext passwords are never logged or stored.

2. **Session & Token Security:**
   Stateless authentication uses signed **JWT tokens** (HS256) with expiration enforcement and HTTP-only cookie support to prevent client-side credential extraction.

3. **Role-Based Access Control (RBAC):**
   Backend middleware enforces role checks across four standard institutional levels:
   - `super_admin`: Full system configuration, user provisioning, and audit oversight.
   - `library_admin`: Policy configuration, shelf management, and financial reconciliation.
   - `librarian`: Daily circulation desks (issue, return, renewal, and cataloging).
   - `member`: Read-only catalog search, self-service loan reviews, and hold reservations.

4. **Cross-Site Scripting (XSS) Prevention:**
   All dynamically rendered strings in the browser interface pass through an entity escape sanitization routine (`escapeHtml`), preventing DOM-based script injection attacks.

5. **SQL Injection Protection:**
   All database communication executes through **SQLAlchemy 2.0 ORM** with parameterized queries and strict type validation.

6. **Audit Trail:**
   Every sensitive authentication, catalog, inventory, and circulation transaction is logged to an immutable `audit_logs` relational table with timestamp, user ID, and source IP address.

---

## Reporting a Vulnerability

If you discover a security vulnerability in this project:

1. **Do not create a public GitHub issue.**
2. Email details to: `salmanmallah@gmail.com` with subject `[SECURITY VULNERABILITY] Library Automation`.
3. Provide a clear description, reproduction steps, and potential impact.
4. Maintainers will acknowledge receipt within 48 hours and work on a coordinated security patch.

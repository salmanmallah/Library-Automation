# Contributing to Library Automation Platform

Thank you for your interest in contributing to the **Institutional Library Management & Automated Inventory Platform**!

---

## Code of Conduct
We are committed to providing a welcoming and inspiring community for all. Please treat maintainers and fellow contributors with respect.

## Getting Started

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/salmanmallah/Library-Automation.git
   cd Library-Automation
   ```

2. **Set up virtual environment:**
   ```bash
   python -m venv .env
   # On Windows:
   .\.env\Scripts\activate
   # On Linux/macOS:
   source .env/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the test suite:**
   ```bash
   pytest
   ```

## Development Guidelines

- **Separation of Concerns:** Keep core services, ORM models, API routes, and presentation layers decoupled.
- **Data Integrity:** Physical book copies must always remain separated from book title metadata.
- **Safety & XSS:** Any client-side template string interpolation MUST be escaped with `escapeHtml()`.
- **Typing & Linting:** Use Python type annotations (`typing`) across all functions.
- **Tests Required:** Any new feature, router, or bug fix must include corresponding unit and integration tests.

## Pull Request Process

1. Create a feature branch (`git checkout -b feat/your-feature-name`).
2. Commit with meaningful conventional commit messages (`feat: add shelf transfer workflow`).
3. Ensure all automated tests pass (`pytest`).
4. Submit a Pull Request targeting the `main` branch with detailed release notes.

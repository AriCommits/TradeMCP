# Security Audit & Architecture Review

## 1. Security Vulnerabilities

### 1.1 Hardcoded Django SECRET_KEY
* **Severity:** **CRITICAL**
* **Location:** `django_mcp_toolkit/django_mcp_toolkit/settings.py`
* **Description:** The `SECRET_KEY` is hardcoded as `'django-insecure-test-key-for-mcp-toolkit'`. If this code is deployed to production, attackers can use this key to forge session cookies, reset passwords, and potentially achieve remote code execution (RCE) via deserialization attacks.
* **Remediation:** Load the `SECRET_KEY` from an environment variable.
  ```python
  import os
  from django.core.exceptions import ImproperlyConfigured

  SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
  if not SECRET_KEY:
      raise ImproperlyConfigured("The DJANGO_SECRET_KEY environment variable must be set.")
  ```

### 1.2 Debug Mode Enabled by Default
* **Severity:** **HIGH**
* **Location:** `django_mcp_toolkit/django_mcp_toolkit/settings.py`
* **Description:** `DEBUG = True` is hardcoded. In production, this will expose detailed stack traces, local variables, and potentially sensitive environment variables to any user who encounters an error page.
* **Remediation:** Toggle `DEBUG` based on an environment variable, defaulting to `False`.
  ```python
  DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() in ('true', '1', 't')
  ```

### 1.3 Overly Permissive ALLOWED_HOSTS
* **Severity:** **HIGH**
* **Location:** `django_mcp_toolkit/django_mcp_toolkit/settings.py`
* **Description:** `ALLOWED_HOSTS = ['*']` allows the Django application to serve requests for any Host header. This makes the application vulnerable to HTTP Host header attacks, which can lead to cache poisoning and password reset poisoning.
* **Remediation:** Restrict `ALLOWED_HOSTS` to the specific domains or IP addresses where the application is hosted, configurable via the environment.
  ```python
  ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
  ```

### 1.4 Unsafe Subprocess Execution Path
* **Severity:** **MEDIUM / HIGH**
* **Location:** `src/trading/execution_client.py` (`apply_execution_filter` function)
* **Description:** The `backend_bin` path is read directly from the configuration (`config["execution"]["backend_bin"]`) and passed to `subprocess.run()`. If an attacker can modify the YAML configuration files, they can execute arbitrary system commands with the privileges of the Python process.
* **Remediation:** Validate that the `backend_bin` path points to an expected, secure directory within the repository and restrict its execution. Alternatively, ensure strict file permissions on the YAML configuration files.

### 1.5 Missing CSRF and CORS Protections (Contextual)
* **Severity:** **MEDIUM**
* **Location:** `django_mcp_toolkit`
* **Description:** While `CsrfViewMiddleware` is enabled, if the MCP tools or views are accessed via cross-origin requests (e.g., from a separate frontend), standard CSRF protections might block legitimate requests or be bypassed if improperly configured. Furthermore, CORS headers are not configured.
* **Remediation:** If the toolkit is meant to be accessed headlessly or via external APIs, configure `django-cors-headers` appropriately and ensure API endpoints use token-based authentication or explicitly handle CSRF for API requests.

---

## 2. Repository Structure Evaluation (Moving directories to `src/`)

You asked if `@backend` and `@django_mcp_toolkit` can be moved into the `@src/` directory to clean up the repository.

### Moving `backend` (Rust Exec Engine)
**Recommendation: DO NOT move to `src/`**
* **Why:** The `backend` directory contains a Rust project (`Cargo.toml`, `src/main.rs`). Standard Python project structures (like PEP 621 / `pyproject.toml` `src` layouts) expect the `src/` directory to contain purely Python packages. Mixing a Rust crate inside the Python `src/` folder can confuse Python packaging tools (like `setuptools` or `build`), make IDE indexing messier, and violate community conventions for polyglot repositories.
* **Alternative:** Keep it as a top-level `backend/` or `rust_backend/` directory.

### Moving `django_mcp_toolkit`
**Recommendation: Move `greeks_viz` to `src/`, drop the host project**
* **Why:** The `django_mcp_toolkit` folder actually contains two things:
  1. `greeks_viz`: A reusable Django app.
  2. `django_mcp_toolkit`: A host Django project used just to run/test the app.
* **How to clean it up:**
  1. Move the `greeks_viz` directory directly into `src/` (so it becomes `src/greeks_viz`). This makes it a proper, importable Python package alongside `src/trading`.
  2. The host project (`django_mcp_toolkit` with `manage.py` and `settings.py`) shouldn't be distributed as part of the core library. You can move it to a `tests/test_project/` directory or a `dev_server/` directory at the root level if you only use it for local development and testing.

**Resulting Clean Architecture:**
```text
.
├── backend/                  # Rust code (stays outside src)
│   └── rust_exec_engine/
├── src/                      # Python source root
│   ├── trading/              # Existing trading logic
│   └── greeks_viz/           # Reusable Django app (Moved)
├── tests/                    # Unit tests
│   └── django_project/       # Host project for testing greeks_viz
├── pyproject.toml
└── README.md
```
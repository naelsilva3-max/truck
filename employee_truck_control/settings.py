"""
Django settings for employee_truck_control project.

Default database: SQLite (development).
PostgreSQL-ready: set DATABASE_URL or override the DATABASES dict via environment.
"""

from pathlib import Path
import os
try:
    from dotenv import load_dotenv
    # Explicitly find the .env file relative to BASE_DIR
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / '.env')
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Base directory
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-dev-only-change-me"
    else:
        raise RuntimeError(
            "DJANGO_SECRET_KEY environment variable is not set. "
            "Set it before starting the server in production."
        )

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1 localhost naelsilva.pythonanywhere.com",
).split()

# ---------------------------------------------------------------------------
# Security Headers & SSL
# These settings are forced OFF when DEBUG=True for local development,
# and forced ON when DEBUG=False for production.
# ---------------------------------------------------------------------------
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
X_FRAME_OPTIONS = "DENY"

# Avoid leaking the referrer header to external sites
SECURE_REFERRER_POLICY = "same-origin"

# Prevent browsers from MIME-sniffing a response away from the declared Content-Type
SECURE_CONTENT_TYPE_NOSNIFF = True

# Ensure session and CSRF cookies are always HttpOnly
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Limit session age to 8 hours of inactivity
SESSION_COOKIE_AGE = 28800
SESSION_SAVE_EVERY_REQUEST = True

# Prevent session fixation
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django built-ins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Project apps
    "optimized_image",
    "core",
    "employees",
    "trucks",
    "attendance",
    "biometric",
    "accounts",
    "visitors",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "employee_truck_control.rate_limit.LoginRateLimitMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # LGPD: blocks BiometricTemplate objects from being passed to templates
    "employee_truck_control.middleware.BiometricTemplateProtectionMiddleware",
]

ROOT_URLCONF = "employee_truck_control.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.user_role",
            ],
        },
    },
]

WSGI_APPLICATION = "employee_truck_control.wsgi.application"

# ---------------------------------------------------------------------------
# Database — PostgreSQL by default, SQLite fallback for local dev
# Set DB_ENGINE=sqlite to use SQLite locally.
#
# Connection pooling:
#   - CONN_MAX_AGE=600 keeps persistent connections for 10 minutes.
#   - For production with high concurrency, use PgBouncer (transaction mode)
#     or set DB_POOL_ENABLED=True to use django-db-connection-pool.
#     Install: pip install django-db-connection-pool
# ---------------------------------------------------------------------------
_db_engine = os.environ.get("DB_ENGINE", "postgresql")

# Persistent database connections (10 minutes) — reduces connection overhead
CONN_MAX_AGE = int(os.environ.get("CONN_MAX_AGE", "600"))

# Connection pooling via django-db-connection-pool (optional)
_db_pool_enabled = os.environ.get("DB_POOL_ENABLED", "False") == "True"

if _db_engine == "postgresql":
    _db_ssl_mode = os.environ.get("DB_SSL_MODE", "require")
    _db_ssl_options = {}
    if _db_ssl_mode and _db_ssl_mode != "disable":
        _db_ssl_options = {
            "sslmode": _db_ssl_mode,
            "sslcert": os.environ.get("DB_SSL_CERT", ""),
            "sslkey": os.environ.get("DB_SSL_KEY", ""),
            "sslrootcert": os.environ.get("DB_SSL_ROOT_CERT", ""),
        }
        # Remove empty values so psycopg2 doesn't complain
        _db_ssl_options = {k: v for k, v in _db_ssl_options.items() if v}

    _db_engine_path = (
        "db_connection_pool.django.backends.postgresql_connection_pool"
        if _db_pool_enabled
        else "django.db.backends.postgresql"
    )

    DATABASES = {
        "default": {
            "ENGINE": _db_engine_path,
            "NAME": os.environ.get("DB_NAME", "employee_truck_control"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            "CONN_MAX_AGE": CONN_MAX_AGE,
            "OPTIONS": _db_ssl_options,
        }
    }

    # Pool-specific settings (only used when DB_POOL_ENABLED=True)
    if _db_pool_enabled:
        DATABASES["default"]["POOL_SETTINGS"] = {
            "max_size": int(os.environ.get("DB_POOL_MAX_SIZE", "10")),
            "min_size": int(os.environ.get("DB_POOL_MIN_SIZE", "2")),
            "max_overflow": int(os.environ.get("DB_POOL_MAX_OVERFLOW", "5")),
            "timeout": int(os.environ.get("DB_POOL_TIMEOUT", "30")),
            "recycle": int(os.environ.get("DB_POOL_RECYCLE", "600")),
        }
elif _db_engine == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ.get("DB_NAME", "employee_truck_control"),
            "USER": os.environ.get("DB_USER", "root"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "3306"),
            "CONN_MAX_AGE": CONN_MAX_AGE,
            "OPTIONS": {
                "charset": "utf8mb4",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "CONN_MAX_AGE": 0,  # SQLite doesn't benefit from persistent connections
        }
    }

# ---------------------------------------------------------------------------
# Email (password recovery, account verification)
# In DEBUG, defaults to printing emails to the console instead of sending
# them for real. Set EMAIL_HOST_USER/EMAIL_HOST_PASSWORD in .env for SMTP.
# ---------------------------------------------------------------------------
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "no-reply@example.com")

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ---------------------------------------------------------------------------
# Media files (employee and truck photos)
# ---------------------------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Authentication redirects
# ---------------------------------------------------------------------------
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "biometric": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Silence django.security to avoid leaking sensitive request data in logs
        "django.security": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # Never log SQL queries in production (may contain sensitive data)
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING" if not DEBUG else "DEBUG",
            "propagate": False,
        },
    },
}
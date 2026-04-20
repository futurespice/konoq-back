"""
konoq/settings.py
"""
from pathlib import Path
from datetime import timedelta
import os
from dotenv import load_dotenv

# Загружаем .env из корня проекта
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent


def env(key, default=None, cast=None):
    """Маленький хелпер — читает переменную окружения с кастингом."""
    value = os.environ.get(key, default)
    if cast is not None and value is not None:
        if cast is bool:
            return str(value).lower() in ("1", "true", "yes")
        if cast is list:
            return [v.strip() for v in str(value).split(",") if v.strip()]
        return cast(value)
    return value


SECRET_KEY    = env("SECRET_KEY", "django-insecure-konoq-dev-key-change-in-production")
DEBUG         = env("DEBUG", "False", cast=bool)
ALLOWED_HOSTS = env("ALLOWED_HOSTS", "", cast=list)

# ── Applications ──────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    # Our apps
    "apps.users",
    "apps.bookings",
    "apps.rooms",
    "apps.tours",
    "apps.finance",
    "apps.tg_bot",
    "apps.wa_bot",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "konoq.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "konoq.wsgi.application"
# Webhook принимается через ASGI (async view), но Gunicorn у нас WSGI.
# Django 4.1+ умеет обрабатывать async views в WSGI через ThreadPoolExecutor — всё работает.

# ── Database ──────────────────────────────────────────────────────────────────
# В продакшне (Docker) используется PostgreSQL, в разработке — SQLite
if env("DB_ENGINE") == "django.db.backends.postgresql":
    DATABASES = {
        "default": {
            "ENGINE":   "django.db.backends.postgresql",
            "NAME":     env("DB_NAME",     "konoq"),
            "USER":     env("DB_USER",     "konoq"),
            "PASSWORD": env("DB_PASSWORD", "konoq"),
            "HOST":     env("DB_HOST",     "db"),
            "PORT":     env("DB_PORT",     "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME":   BASE_DIR / "db.sqlite3",
        }
    }

# ── Auth ──────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Localisation ──────────────────────────────────────────────────────────────
LANGUAGE_CODE = "ru-ru"
TIME_ZONE     = "Asia/Bishkek"
USE_I18N      = True
USE_TZ        = True

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL  = "/django-static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ── Media files ───────────────────────────────────────────────────────────────
MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── DRF ───────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# ── JWT ───────────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":    timedelta(minutes=env("ACCESS_TOKEN_LIFETIME_MINUTES", 30, cast=int)),
    "REFRESH_TOKEN_LIFETIME":   timedelta(days=env("REFRESH_TOKEN_LIFETIME_DAYS",  30, cast=int)),
    "ROTATE_REFRESH_TOKENS":    True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES":        ("Bearer",),
}

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = DEBUG  # В режиме DEBUG разрешаем всё для удобства фронта
CORS_ALLOWED_ORIGINS = env(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
    cast=list,
)
CORS_ALLOW_CREDENTIALS = True

# ── CSRF ──────────────────────────────────────────────────────────────────────
CSRF_TRUSTED_ORIGINS = env(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:3000",
    cast=list,
)

# Говорим Django что он за доверенным прокси
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ── Telegram Bot ──────────────────────────────────────────────────────────────
# TG_BOT_TOKEN      — токен от @BotFather
# TG_OWNER_ID       — Telegram user_id владельца (Эрнис)
# TG_WEBHOOK_SECRET — случайная строка, часть URL webhook
# SITE_URL          — https://konoq-hostel.com (без слэша в конце)
TG_BOT_TOKEN      = env("TG_BOT_TOKEN",      "")
TG_OWNER_ID       = env("TG_OWNER_ID",       "0")
TG_WEBHOOK_SECRET = env("TG_WEBHOOK_SECRET", "")
SITE_URL          = env("SITE_URL",          "")

# ── Swagger / drf-spectacular ─────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE":       "KonoQ API",
    "DESCRIPTION": "API системы управления хостелом KonoQ · Ош, Кыргызстан",
    "VERSION":     "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
    },
    "COMPONENT_SPLIT_REQUEST": True,
    "TAGS": [
        {"name": "auth",     "description": "Авторизация и управление пользователями"},
        {"name": "bookings", "description": "Бронирования гостей"},
        {"name": "rooms",    "description": "Физические номера хостела"},
        {"name": "tours",    "description": "Туры и экскурсии"},
        {"name": "finance",  "description": "Финансы и выручка (только admin)"},
    ],
}

# SendPulse WhatsApp
SENDPULSE_CLIENT_ID = os.getenv("SENDPULSE_CLIENT_ID", "")
SENDPULSE_CLIENT_SECRET = os.getenv("SENDPULSE_CLIENT_SECRET", "")
SENDPULSE_PHONE = os.getenv("SENDPULSE_PHONE", "")

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

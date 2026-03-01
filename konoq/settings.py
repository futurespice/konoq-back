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
DEBUG         = env("DEBUG", "True", cast=bool)
ALLOWED_HOSTS = env("ALLOWED_HOSTS", "*", cast=list)

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
    "ACCESS_TOKEN_LIFETIME":    timedelta(hours=env("ACCESS_TOKEN_LIFETIME_HOURS", 8, cast=int)),
    "REFRESH_TOKEN_LIFETIME":   timedelta(days=env("REFRESH_TOKEN_LIFETIME_DAYS",  30, cast=int)),
    "ROTATE_REFRESH_TOKENS":    True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES":        ("Bearer",),
}

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
    cast=list,
)
CORS_ALLOW_CREDENTIALS = True

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

"""CampusTrace 配置。

正式开发与验收只使用 MySQL 8.4，不静默回退 SQLite。这样数据库缺失时会明确失败，
避免在不具备行锁、字符集和约束等价性的环境上产生虚假通过结果。
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["127.0.0.1", "localhost"]),
    DJANGO_PUBLIC_TEST=(bool, False),
    DJANGO_SECURE_COOKIES=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")
environ.Env.read_env(BASE_DIR / '.env.amap')

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-development-key-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
PUBLIC_TEST_MODE = env("DJANGO_PUBLIC_TEST")
PUBLIC_TEST_BLOCKED_USERNAMES = set(
    env.list(
        "DJANGO_PUBLIC_TEST_BLOCKED_USERNAMES",
        default=[
            "admin_demo", "staff_east", "staff_west",
            "student_01", "student_02", "student_03", "student_04",
            "student_05", "student_06", "student_07", "student_08",
        ],
    )
)

# AI 默认为明示的本地规则桩，不会产生外部请求或费用。
# 配置真实提供方后仍需通过后端严格协议验证。
AI_PROVIDER_MODE = env("AI_PROVIDER_MODE", default="development_stub")
AI_PROVIDER_BASE_URL = env("AI_PROVIDER_BASE_URL", default="")
AI_PROVIDER_API_KEY = env("AI_PROVIDER_API_KEY", default="")
AI_PROVIDER_MODEL = env("AI_PROVIDER_MODEL", default="")
AI_REQUEST_TIMEOUT_SECONDS = env.int("AI_REQUEST_TIMEOUT_SECONDS", default=20)
AI_MAX_INPUT_CHARS = env.int("AI_MAX_INPUT_CHARS", default=1200)
AI_MAX_CONCURRENT = max(1, env.int('AI_MAX_CONCURRENT', default=1))
AI_REQUESTS_PER_MINUTE = max(1, env.int('AI_REQUESTS_PER_MINUTE', default=6))
AI_TOTAL_TIMEOUT_SECONDS = max(1, env.int('AI_TOTAL_TIMEOUT_SECONDS', default=90))
AI_RESULT_TTL_SECONDS = max(1, env.int('AI_RESULT_TTL_SECONDS', default=3600))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.accounts",
    "apps.stations",
    "apps.items",
    "apps.matching",
    "apps.claims",
    "apps.messaging",
    "apps.notifications",
    "apps.content",
    "apps.administration",
    "apps.assistant",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # 对 JSON、JS 代理响应启用标准压缩；正式反向代理可继续使用 Brotli/Gzip。
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.administration.middleware.RequestIdMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("MYSQL_DATABASE", default="campustrace"),
        "USER": env("MYSQL_USER", default="campustrace"),
        "PASSWORD": env("MYSQL_PASSWORD", default="campustrace-local-only"),
        "HOST": env("MYSQL_HOST", default="127.0.0.1"),
        "PORT": env("MYSQL_PORT", default="3307"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE'",
        },
        "CONN_MAX_AGE": 60,
        "ATOMIC_REQUESTS": True,
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
# 公网演示进程使用独立的空媒体目录，避免将本地用户上传文件带到公网。
# 正式对象存储部署仍可通过同一环境变量切换挂载位置。
MEDIA_ROOT = Path(env("DJANGO_MEDIA_ROOT", default=str(BASE_DIR / "media")))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env("DJANGO_SECURE_COOKIES")
CSRF_COOKIE_SECURE = env("DJANGO_SECURE_COOKIES")
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=env.list(
        "CORS_ALLOWED_ORIGINS",
        default=["http://127.0.0.1:5173", "http://localhost:5173"],
    ),
)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_HSTS_PRELOAD", default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.ActiveSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "config.pagination.CampusTracePagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "config.exceptions.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_RATES": {
        "login": "30/min",
        "register": "20/hour",
        "campus_feedback": "10/hour",
        "map_proxy": "120/min",
    },
}

DEMO_BASE_DATE = env("DEMO_BASE_DATE", default="2026-08-20T08:00:00+08:00")
AMAP_WEB_KEY = env('AMAP_WEB_KEY', default='')
AMAP_SECURITY_CODE = env('AMAP_SECURITY_CODE', default='')
AI_LOCAL_VISION_URL = env('AI_LOCAL_VISION_URL', default='')
AI_LOCAL_VISION_MODEL = env('AI_LOCAL_VISION_MODEL', default='')
AI_LOCAL_EMBEDDING_URL = env('AI_LOCAL_EMBEDDING_URL', default='')
AI_LOCAL_EMBEDDING_MODEL = env('AI_LOCAL_EMBEDDING_MODEL', default='')
AI_LOCAL_EMBEDDING_REVISION = env('AI_LOCAL_EMBEDDING_REVISION', default='v1')
AI_INDEX_SYNC_LIMIT = max(0, env.int('AI_INDEX_SYNC_LIMIT', default=32))

import json
import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
JINJA_DIR = BASE_DIR / "jinja2"
STATIC_DIR = BASE_DIR / "static"
MEDIA_DIR = BASE_DIR / "media"
JINJA_TEMPLATE_DIRS = [
    JINJA_DIR,
    BASE_DIR / "apps" / "dashboards" / "templates",
    BASE_DIR / "apps" / "campaigns" / "templates",
    BASE_DIR / "apps" / "ticketing" / "templates",
    BASE_DIR / "apps" / "support_center" / "templates",
    BASE_DIR / "apps" / "reporting" / "templates",
]

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "campaign-management-local-secret-key")
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sites",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "apps.accounts",
    "apps.campaigns",
    "apps.ticketing",
    "apps.support_center",
    "apps.reporting",
    "apps.dashboards",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": JINJA_TEMPLATE_DIRS,
        "APP_DIRS": True,
        "NAME": "jinja2",
        "OPTIONS": {
            "environment": "config.jinja2.environment",
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "config.context_processors.auth_configuration",
            ],
        },
    },
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [TEMPLATES_DIR],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "config.context_processors.auth_configuration",
            ],
        },
    },
]

database_engine = os.getenv("DB_ENGINE", "sqlite").lower()
if database_engine == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME", "campaign_management"),
            "USER": os.getenv("DB_USER", "root"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [STATIC_DIR]
STATIC_ROOT = BASE_DIR / "staticfiles"
if DEBUG:
    STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
else:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = MEDIA_DIR

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
SITE_ID = 1

LOGIN_REDIRECT_URL = "dashboards:home"
LOGOUT_REDIRECT_URL = "home"
LOGIN_URL = "account_login"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "full_name*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_ADAPTER = "apps.accounts.adapters.AccountAdapter"

SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "OAUTH_PKCE_ENABLED": True,
        "APPS": [
            {
                "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
                "secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            }
        ]
        if os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")
        else [],
    }
}

PROJECT_MANAGER_EMAIL = os.getenv("PROJECT_MANAGER_EMAIL", "campaignpm@inditech.co.in")
ENABLE_DEV_LOGIN = os.getenv("ENABLE_DEV_LOGIN", "true").lower() == "true"
EXTERNAL_TICKETING_SYNC_ENABLED = os.getenv("EXTERNAL_TICKETING_SYNC_ENABLED", "false").lower() == "true"
EXTERNAL_TICKETING_BASE_URL = os.getenv("EXTERNAL_TICKETING_BASE_URL", "").strip()
EXTERNAL_TICKETING_API_TOKEN = os.getenv("EXTERNAL_TICKETING_API_TOKEN", "").strip()
EXTERNAL_TICKETING_TIMEOUT = float(os.getenv("EXTERNAL_TICKETING_TIMEOUT", "10"))
EXTERNAL_TICKETING_SOURCE_SYSTEM = os.getenv("EXTERNAL_TICKETING_SOURCE_SYSTEM", "campaign_management").strip() or "campaign_management"
EXTERNAL_TICKETING_REQUESTER_PHONE_FALLBACK = os.getenv("EXTERNAL_TICKETING_REQUESTER_PHONE_FALLBACK", "").strip()
try:
    EXTERNAL_TICKETING_DEPARTMENT_MAP = json.loads(os.getenv("EXTERNAL_TICKETING_DEPARTMENT_MAP_JSON", "{}"))
except json.JSONDecodeError:
    EXTERNAL_TICKETING_DEPARTMENT_MAP = {}
REPORTING_API_USE_LIVE = os.getenv("REPORTING_API_USE_LIVE", "true").lower() == "true"
REPORTING_API_TIMEOUT = float(os.getenv("REPORTING_API_TIMEOUT", "5"))
REPORTING_API_RED_FLAG_ALERT_URL = os.getenv(
    "REPORTING_API_RED_FLAG_ALERT_URL",
    "https://reports.inditech.co.in/reporting/api/red_flag_alert/",
)
REPORTING_API_IN_CLINIC_URL = os.getenv(
    "REPORTING_API_IN_CLINIC_URL",
    "https://reports.inditech.co.in/reporting/api/in_clinic/",
)
REPORTING_API_PATIENT_EDUCATION_URL = os.getenv(
    "REPORTING_API_PATIENT_EDUCATION_URL",
    "https://reports.inditech.co.in/reporting/api/patient_education/",
)
WORDPRESS_HELPER_URL = os.getenv("WORDPRESS_HELPER_URL", "https://esapa.one/")
WORDPRESS_HELPER_SECRET = os.getenv("WORDPRESS_HELPER_SECRET", "sanyam1212")
WORDPRESS_HELPER_TIMEOUT = float(os.getenv("WORDPRESS_HELPER_TIMEOUT", "20"))
WORDPRESS_GROWTH_WEBINAR_FILTERS = os.getenv("WORDPRESS_GROWTH_WEBINAR_FILTERS", "SAPA Growth Clinics")
WORDPRESS_CERTIFICATE_COURSE_IDS = os.getenv("WORDPRESS_CERTIFICATE_COURSE_IDS", "8693,9204")
try:
    STATUS_MONITOR_EXTRA_TARGETS = json.loads(os.getenv("STATUS_MONITOR_EXTRA_TARGETS_JSON", "[]"))
except json.JSONDecodeError:
    STATUS_MONITOR_EXTRA_TARGETS = []

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@inditech.local")

MESSAGE_TAGS = {
    20: "info",
    25: "success",
    30: "warning",
    40: "danger",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        }
    },
    "loggers": {
        "apps.ticketing.external_ticketing": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        }
    },
}

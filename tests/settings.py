import os

SETTINGS_DIR = os.path.dirname(__file__)

DATABASE_ENGINE = "sqlite3"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sites",
    "avatar",
]

MIDDLEWARE = (
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
)

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "DIRS": [os.path.join(SETTINGS_DIR, "templates")],
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.request",
            ]
        },
    }
]

ROOT_URLCONF = "tests.urls"

SITE_ID = 1

SECRET_KEY = "something-something"

STATIC_URL = "/site_media/static/"

AVATAR_ALLOWED_FILE_EXTS = (".jpg", ".png")
AVATAR_MAX_SIZE = 1024 * 1024
AVATAR_MAX_AVATARS_PER_USER = 20
AVATAR_AUTO_GENERATE_SIZES = [51, 62, (33, 22), 80]

MEDIA_ROOT = os.path.join(SETTINGS_DIR, "../test-media")

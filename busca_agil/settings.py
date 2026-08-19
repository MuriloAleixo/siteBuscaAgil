from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# Em produção, defina DJANGO_SECRET_KEY, DJANGO_DEBUG=false e
# DJANGO_ALLOWED_HOSTS no .env (ou nas variáveis de ambiente do servidor).
# Sem isso, o projeto continua rodando com valores de desenvolvimento —
# nunca suba com DEBUG=true ou com a SECRET_KEY padrão em produção.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-busca-agil-dev-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").strip().lower() in ("1", "true", "yes", "on")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]

if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["*"]

if not DEBUG and SECRET_KEY.startswith("django-insecure-"):
    raise RuntimeError(
        "DJANGO_DEBUG=false mas DJANGO_SECRET_KEY não foi definida — gere uma "
        "chave segura (ex.: `python -c \"import secrets; print(secrets.token_urlsafe(50))\"`) "
        "e defina DJANGO_SECRET_KEY no .env antes de rodar em produção."
    )

if not DEBUG and not ALLOWED_HOSTS:
    raise RuntimeError(
        "DJANGO_DEBUG=false mas DJANGO_ALLOWED_HOSTS não foi definida — "
        "defina os domínios/IPs permitidos (separados por vírgula) no .env."
    )

# CSRF precisa saber a origem HTTPS real por trás de um proxy/domínio em
# produção (ex.: https://buscaagil.suaempresa.com.br); em dev fica vazio.
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "busca_agil.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates", BASE_DIR],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.busca_agil_user",
            ],
        },
    },
]

WSGI_APPLICATION = "busca_agil.wsgi.application"
ASGI_APPLICATION = "busca_agil.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Login é feito só com a conta Google (sem usuário/senha local) — o próprio
# consentimento do Google já pede o escopo de Drive, então login e
# autorização de Drive acontecem numa única tela do Google, não em duas
# telas nossas.
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_LOGOUT_ON_GET = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_STORE_TOKENS = True

# `post_login_sync` é quem garante (antes do usuário ver qualquer página)
# que a pasta/catálogo do usuário no Drive existem e estão espelhados
# localmente — só depois disso ele é mandado pro dashboard.
LOGIN_REDIRECT_URL = "/post-login/"
LOGOUT_REDIRECT_URL = "/index.html"
LOGIN_URL = "/index.html"

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APPS": [
            {
                "client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
                "secret": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
                "key": "",
            }
        ],
        # drive.file: só dá acesso aos arquivos que o próprio BuscaÁgil cria
        # no Drive do usuário — não enxerga o resto do Drive dele.
        "SCOPE": [
            "profile",
            "email",
            "https://www.googleapis.com/auth/drive.file",
        ],
        # access_type=offline + prompt=consent garantem que o Google sempre
        # devolva um refresh_token, necessário pro worker Celery conseguir
        # subir arquivos pro Drive fora do ciclo de vida do login.
        "AUTH_PARAMS": {
            "access_type": "offline",
            "prompt": "consent",
        },
    }
}

# Nome da pasta criada no Drive de cada usuário, onde ficam os arquivos
# enviados + o catalog.json daquele usuário (ver core/google_drive.py).
GOOGLE_DRIVE_APP_FOLDER_NAME = "buscaagil_upload"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
# Use a string for MEDIA_ROOT to avoid pathlib/storage edge-cases
MEDIA_ROOT = str(BASE_DIR / "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Celery: fila de mensagens (broker) e backend de resultados via Redis.
# A classificação via Gemini roda em worker(s) separado(s) do processo web,
# desacoplados pela fila — ver core/tasks.py.
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]

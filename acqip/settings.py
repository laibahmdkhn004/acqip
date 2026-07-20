import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Generic AI Configuration - Works with any provider
AI_PROVIDER = os.getenv('AI_PROVIDER', 'openai').lower()  # openai, openrouter, deepseek, anthropic, etc.
AI_API_KEY = os.getenv('AI_API_KEY')
AI_BASE_URL = os.getenv('AI_BASE_URL')
AI_MODEL = os.getenv('AI_MODEL', 'gpt-4')

# Provider-specific configurations
AI_CONFIGS = {
    'openai': {
        'model': AI_MODEL,
        'api_key': AI_API_KEY,
        'api_base': 'https://api.openai.com/v1',
        'provider': 'openai'
    },
    'openrouter': {
        'model': AI_MODEL,
        'api_key': AI_API_KEY,
        'api_base': 'https://openrouter.ai/api/v1',
        'provider': 'openrouter'
    },
    'deepseek': {
        'model': AI_MODEL,
        'api_key': AI_API_KEY,
        'api_base': 'https://api.deepseek.com',
        'provider': 'deepseek'
    },
    'anthropic': {
        'model': AI_MODEL,
        'api_key': AI_API_KEY,
        'api_base': 'https://api.anthropic.com',
        'provider': 'anthropic'
    },
    'groq': {
        'model': AI_MODEL,
        'api_key': AI_API_KEY,
        'api_base': 'https://api.groq.com/openai/v1',
        'provider': 'groq'
    },
    'ollama': {
        'model': AI_MODEL,
        'api_key': None,
        'api_base': 'http://localhost:11434/v1',
        'provider': 'ollama'
    },
    'together': {
        'model': AI_MODEL,
        'api_key': AI_API_KEY,
        'api_base': 'https://api.together.xyz/v1',
        'provider': 'together'
    },
    'huggingface': {
        'model': AI_MODEL,
        'api_key': AI_API_KEY,
        'api_base': 'https://api-inference.huggingface.co/v1',
        'provider': 'huggingface'
    }
}

# Get current provider config
AI_CONFIG = AI_CONFIGS.get(AI_PROVIDER, AI_CONFIGS['openai'])

# Override with environment variables if provided
if AI_BASE_URL:
    AI_CONFIG['api_base'] = AI_BASE_URL
if AI_MODEL:
    AI_CONFIG['model'] = AI_MODEL

# LiteLLM Configuration
LITELLM_CONFIG = {
    'api_key': AI_CONFIG['api_key'],
    'api_base': AI_CONFIG['api_base'],
    'timeout': 30.0,
    'max_retries': 2,
}

# Feature flags
FEATURE_FLAGS = {
    'ai_cqi_reports': bool(AI_API_KEY),
    'ai_analysis': bool(AI_API_KEY),
}

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-your-secret-key-here')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if host.strip()
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'acqip.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'acqip.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = []
_project_static_dir = os.path.join(BASE_DIR, 'static')
if os.path.isdir(_project_static_dir):
    STATICFILES_DIRS.append(_project_static_dir)

# Media files (uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

# Login/Logout URLs
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# Email / SMTP (password reset)
EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() == 'true'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv(
    'DEFAULT_FROM_EMAIL',
    EMAIL_HOST_USER or 'noreply@acqip.local',
)
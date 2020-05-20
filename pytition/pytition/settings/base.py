"""
Django settings for pytition project.

Generated by 'django-admin startproject' using Django 1.11.5.

For more information on this file, see
https://docs.djangoproject.com/en/1.11/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.11/ref/settings/
"""

import os
import django.conf.locale
from django.contrib.messages import constants as messages
from django.urls import reverse_lazy
from django.conf import global_settings
from django.utils.translation import gettext_lazy

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ALLOWED_HOSTS = ['0.0.0.0', '127.0.0.1', 'localhost', '[::1]']

# Application definition

INSTALLED_APPS = [
    'tinymce',
    'colorfield',
    'petition.apps.PetitionConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'widget_tweaks',
    'formtools',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.BCryptPasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.Argon2PasswordHasher',
]

ROOT_URLCONF = 'pytition.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'petition.helpers.footer_content_processor',
                'petition.helpers.settings_context_processor',
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',

            ],
        },
    },
]

WSGI_APPLICATION = 'pytition.wsgi.application'

if os.environ.get('USE_POSTGRESQL'):
    from .pgsql import DATABASES

#:| Set it to ``True`` if you want email sending to retry upon failure.
#:| Email transmition naturally have retries *if the first SMTP server accepts it*
#:| If your SMTP server refuses to handle the email (anti-flood throttle?) then it
#:| is up to you to retry, and this is what the mail queue does for you.
#:| This is especially needed if you don't own the first-hop SMTP server
#:| and cannot configure it to always accept your emails regardless of the sending
#:| frequency.
#:| It is **HIGHLY** recommended to set this to ``True``.
#:| If you chose to use the mail queue, you must also either
#:
#: * set a cron job (automatic task execution), or
#: * serve the Django app through uwsgi (recommended setup)
#:
#: .. warning:: The first time you switch this setting from ``False`` to ``True``, you must run the ``DJANGO_SETTINGS_MODULE=pytition.settings.config python3 pytition/manage.py migrate`` command again. Beware to run it while being in your virtualenv.
USE_MAIL_QUEUE = False

# set it to True if you use the 'mailer' backend, and a external Crontab has been set
MAIL_EXTERNAL_CRON_SET = False

# number of seconds to wait before sending emails. This will be usefull only if USE_MAIL_QUEUE=True and uwsgi is used
UWSGI_WAIT_FOR_MAIL_SEND_IN_S = 10
# number of seconds to wait before retrying emails. This will be usefull only if USE_MAIL_QUEUE=True and uwsgi is used
UWSGI_WAIT_FOR_RETRY_IN_S = 1 * 60
# number of seconds to wait before purging emails. This will be usefull only if USE_MAIL_QUEUE=True and uwsgi is used
UWSGI_WAIT_FOR_PURGE_IN_S = 1 * 24 * 60 * 60
UWSGI_NB_DAYS_TO_KEEP = 3

# Password validation
# https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/1.11/topics/i18n/

LANGUAGE_CODE = 'en-us'

USE_I18N = True

USE_L10N = True

USE_TZ = True
X_FRAME_OPTIONS = "SAMEORIGIN"
LOCALE_PATHS = (os.path.join(BASE_DIR, "locale"), )

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.environ.get('STATIC_ROOT')
LOGIN_URL = '/petition/login/'

TINYMCE_JS_URL = '/static/vendor/tinymce/js/tinymce/tinymce.min.js'
TINYMCE_DEFAULT_CONFIG = {
    'plugins': 'print preview fullpage searchreplace autolink directionality visualblocks visualchars fullscreen image link media template codesample table charmap hr pagebreak nonbreaking anchor toc insertdatetime advlist lists textcolor wordcount imagetools contextmenu colorpicker textpattern help',
    'theme': "modern",
    'cleanup_on_startup': True,
    'custom_undo_redo_levels': 10,
    'toolbar1': 'formatselect | bold italic strikethrough forecolor backcolor | link | alignleft aligncenter alignright alignjustify  | numlist bullist outdent indent  | removeformat | fontselect | fontsizeselect',
    'insert_toolbar': 'forecolor backcolor',
    'fontsize_formats': '8pt 10pt 12pt 14pt 18pt 24pt 36pt',
    'entity_encoding': 'raw',
    'relative_urls' : False,
    'convert_urls': True,
    'file_picker_types': 'image',
    'automatic_uploads': True,
    'images_upload_url': '/petition/image_upload',
    'image_upload_credentials': True,
    'images_upload_handler': """function(blobInfo, success, failure) {
        let xhr = new XMLHttpRequest();
        xhr.open('POST', '/petition/image_upload');
        xhr.setRequestHeader('X-CSRFTOKEN', get_csrf_token()); // manually set header
    
        xhr.onload = function() {
            if (xhr.status !== 200) {
                failure('HTTP Error: ' + xhr.status);
                return;
            }
    
            let json = JSON.parse(xhr.responseText);
    
            if (!json || typeof json.location !== 'string') {
                failure('Invalid JSON: ' + xhr.responseText);
                return;
            }
    
            success(json.location);
        };
    
        let formData = new FormData();
        formData.append('file', blobInfo.blob(), blobInfo.filename());
    
        xhr.send(formData);
        }
    """,
    'setup': """function(ed) {
       ed.on('change', function(e) {
            set_mce_changed(ed);
       });}""",
}
TINYMCE_INCLUDE_JQUERY = True

#:| The name of your Pytition instance.
SITE_NAME = "Pytition"

#:| Whether you want to allow anyone to create an account and host petitions
#:| on your Pytition instance.
#:| Set it to ``False`` for a private instance.
#:| Set it to ``True`` for a public instance.
ALLOW_REGISTER = True

LOGIN_REDIRECT_URL = reverse_lazy("user_dashboard")
DEFAULT_INDEX_THUMBNAIL = "/img/petition_icon.svg"

#:| Leave it set to None for no footer.
#:| This should contain the relative path to your footer template.
#:| That would be the location for any "legal mention" / "GDPR" / "TOS" link.
#:
#: Example::
#:
#:   FOOTER_TEMPLATE = 'layouts/footer.html.example'
FOOTER_TEMPLATE = None

#INDEX_PAGE_ORGA = "RAP"
#INDEX_PAGE_USER = "admin"
INDEX_PAGE = "HOME"
#INDEX_PAGE = "ALL_PETITIONS"
#INDEX_PAGE = "ORGA_PROFILE"
#INDEX_PAGE = "USER_PROFILE"
#INDEX_PAGE = "LOGIN_REGISTER"

# Anti bot feature
SIGNATURE_THROTTLE = 5 # 5 signatures from same IP allowed
SIGNATURE_THROTTLE_TIMING = 60*60*24 # in a 1 day time frame

LANGUAGES = [
    ('en', gettext_lazy('English')),
    ('es', gettext_lazy('Spanish')),
    ('fr', gettext_lazy('French')),
    ('it', gettext_lazy('Italian')),
    ('oc', gettext_lazy('Occitan')),
]

EXTRA_LANG_INFO = {
    'oc': {
        'code': 'oc',
        'name': 'Occitan',
    },
}
LANG_INFO = dict(django.conf.locale.LANG_INFO, **EXTRA_LANG_INFO)
django.conf.locale.LANG_INFO = LANG_INFO

MEDIA_ROOT = os.path.join(BASE_DIR, "mediaroot")
MEDIA_URL = "/mediaroot/"
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o644

DISABLE_USER_PETITION = False

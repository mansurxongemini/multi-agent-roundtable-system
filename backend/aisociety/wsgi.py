"""WSGI entrypoint (used by the Django admin / sync views only)."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aisociety.settings")

application = get_wsgi_application()

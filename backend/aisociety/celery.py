"""
Celery application.

Used for asynchronous, CPU/IO-heavy background work that should not block the
realtime orchestration loop — primarily the "Rolling Summary" compression of
old chat history (see orchestration/tasks.py).
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aisociety.settings")

app = Celery("aisociety")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")

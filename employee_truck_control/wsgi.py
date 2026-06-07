"""
WSGI config for employee_truck_control project.
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "employee_truck_control.settings")

application = get_wsgi_application()

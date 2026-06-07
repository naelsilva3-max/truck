"""
ASGI config for employee_truck_control project.
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "employee_truck_control.settings")

application = get_asgi_application()

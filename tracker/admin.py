from django.contrib import admin
from .models import Entry, WorkType
# Work data is managed through the owner-scoped API, not the shared admin.
admin.site.site_header = "Hourleaf · User administration"

from django.contrib import admin

# Work data is managed through the owner-scoped API, not the shared admin.
admin.site.site_header = "Hourleaf · User administration"

from django.contrib import admin

from .models import Alert, PerformanceSnapshot


admin.site.register(PerformanceSnapshot)
admin.site.register(Alert)

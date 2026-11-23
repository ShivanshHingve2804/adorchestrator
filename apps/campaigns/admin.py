from django.contrib import admin

from .models import Campaign, Creative, PlatformDeployment


admin.site.register(Campaign)
admin.site.register(Creative)
admin.site.register(PlatformDeployment)

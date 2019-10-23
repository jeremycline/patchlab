from django.contrib import admin

from patchlab.models import GitForge, BridgedSubmission


class GitForgeAdmin(admin.ModelAdmin):
    pass


class BridgedSubmissionAdmin(admin.ModelAdmin):
    pass


admin.site.register(GitForge, GitForgeAdmin)
admin.site.register(BridgedSubmission, BridgedSubmissionAdmin)

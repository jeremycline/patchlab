# SPDX-License-Identifier: GPL-2.0-or-later

from django.contrib import admin

from patchlab.models import GitForge, BridgedSubmission, Branch


class GitForgeAdmin(admin.ModelAdmin):
    pass


class BridgedSubmissionAdmin(admin.ModelAdmin):
    pass


class BranchAdmin(admin.ModelAdmin):
    pass


admin.site.register(GitForge, GitForgeAdmin)
admin.site.register(BridgedSubmission, BridgedSubmissionAdmin)
admin.site.register(Branch, BranchAdmin)

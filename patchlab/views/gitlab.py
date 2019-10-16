"""
Web hooks for bridging GitLab into email.
"""
from django.http import HttpResponse

from patchlab.tasks import email_comment, email_merge_request


def merge_request(request):
    email_merge_request.apply_async((request,))
    return HttpResponse()


def comment(request):
    email_comment.apply_async((request,))
    return HttpResponse()

"""
Web hooks for bridging GitLab into email.
"""
from django.http import HttpResponse


def merge_request(request):
    return HttpResponse()


def comment(request):
    return HttpResponse()

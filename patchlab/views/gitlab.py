"""Web hooks for bridging GitLab into email."""
import json

from django import http
from django.conf import settings
from django.views.decorators import csrf, http as http_decorators

from patchlab.tasks import email_comment, email_merge_request


# TODO maybe have one URL and check X-Gitlab-Event header.
@http_decorators.require_POST
@csrf.csrf_exempt
def merge_request(request: http.HttpRequest) -> http.HttpResponse:
    """
    Dispatch a series of emails for a merge request on Gitlab.

    The request body is a JSON document documented at
    https://docs.gitlab.com/ce/user/project/integrations/webhooks.html
    """
    try:
        secret = request.headers["X-Gitlab-Token"]
    except KeyError:
        return http.HttpResponseForbidden("Permission denied: missing web hook token")

    if secret != settings.GITLAB_WEBHOOK_SECRET:
        return http.HttpResponseForbidden("Permission denied: invalid web hook token")

    try:
        payload = json.loads(request.body, encoding=request.encoding)
    except json.JSONDecodeError:
        return http.HttpResponseBadRequest("JSON body required in POST")

    try:
        if any([label["title"] == "From email" for label in payload["labels"]]):
            return http.HttpResponse("Let's not loop infinitely")
    except KeyError:
        return http.HttpResponseBadRequest("Payload expected to have labels")

    email_merge_request.apply_async(
        (payload["project"]["id"], payload["object_attributes"]["id"])
    )
    return http.HttpResponse()


def comment(request):
    """
    Dispatch a comment posted on a pull request as an email in response to the
    original patch series email thread.

    The request body is a JSON document documented at
    https://docs.gitlab.com/ce/user/project/integrations/webhooks.html
    """
    email_comment.apply_async((request,))
    return http.HttpResponse()

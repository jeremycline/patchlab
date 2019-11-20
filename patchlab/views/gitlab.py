# SPDX-License-Identifier: GPL-2.0-or-later
"""Web hooks for bridging GitLab into email."""
import json
import urllib

from django import http
from django.conf import settings
from django.views.decorators import csrf, http as http_decorators

from patchlab.tasks import email_comment, merge_request_hook


@http_decorators.require_POST
@csrf.csrf_exempt
def web_hook(request: http.HttpRequest) -> http.HttpResponse:
    """
    Generic web hook handler for GitLab

    This is responsible for checking the authenticity of the request and
    dispatching it to the proper function based on the X-Gitlab-Event header.
    """
    try:
        secret = request.headers["X-Gitlab-Token"]
    except KeyError:
        return http.HttpResponseForbidden("Permission denied: missing web hook token")

    if secret != settings.PATCHLAB_GITLAB_WEBHOOK_SECRET:
        return http.HttpResponseForbidden("Permission denied: invalid web hook token")

    try:
        payload = json.loads(request.body, encoding=request.encoding)
    except json.JSONDecodeError:
        return http.HttpResponseBadRequest("JSON body required in POST")

    try:
        return WEBHOOKS[request.headers["X-Gitlab-Event"]](payload)
    except KeyError:
        return http.HttpResponseBadRequest("No web hook handler for request")


def merge_request(payload: dict) -> http.HttpResponse:
    """
    Dispatch a series of emails for a merge request on Gitlab.

    The request body is a JSON document documented at
    https://docs.gitlab.com/ce/user/project/integrations/webhooks.html
    """
    try:
        if any([label["title"] == "From email" for label in payload["labels"]]):
            return http.HttpResponse("Let's not loop infinitely")
    except KeyError:
        return http.HttpResponseBadRequest("Payload expected to have labels")

    if payload["object_attributes"]["action"] not in ("open", "reopen"):
        return http.HttpResponse("Skipping event as merge request has not been opened")

    project_id = payload["project"]["id"]
    merge_id = payload["object_attributes"]["id"]
    host = urllib.parse.urlsplit(payload["project"]["web_url"]).hostname
    merge_request_hook.apply_async((host, project_id, merge_id))
    return http.HttpResponse("Success!")


def comment(payload: dict) -> http.HttpResponse:
    """
    Dispatch a comment posted on a pull request as an email in response to the
    original patch series email thread.

    The request body is a JSON document documented at
    https://docs.gitlab.com/ce/user/project/integrations/webhooks.html
    """
    comment_type = payload["object_attributes"]["noteable_type"]
    if comment_type == "MergeRequest":
        pass
    elif comment_type == "Commit":
        pass

    email_comment.apply_async((payload,))
    return http.HttpResponse("Success!")


#: The set of web hook handlers that are currently supported.
#: Consult `Gitlab webhooks`_ documentation for complete list of webhooks and
#: the payload details.
#:
#: Merge Request Hook: This hook converts any merge-able merge request into
#: an email series. It does not check for, say, a completed pipeline.
#:
#: Note Hook: Converts any comments on a merge request into an email response
#:
#: .. _Gitlab webhooks: https://docs.gitlab.com/ee/user/project/integrations/webhooks.html
WEBHOOKS = {"Merge Request Hook": merge_request, "Note Hook": comment}

# SPDX-License-Identifier: GPL-2.0-or-later
"""Web hooks for bridging GitLab into email."""
import json
import urllib
import logging

from django import http
from django.conf import settings
from django.views.decorators import csrf, http as http_decorators

from patchlab.tasks import email_comment, merge_request_hook

_log = logging.getLogger(__name__)


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
        handler = WEBHOOKS[request.headers["X-Gitlab-Event"]]
        _log.info(
            "Handling web hook request with the '%s' handler",
            request.headers["X-Gitlab-Event"],
        )
    except KeyError:
        _log.error(
            "No web hook handler for '%s' events; Adjust your web hooks on GitLab",
            request.headers["X-Gitlab-Event"],
        )
        return http.HttpResponseBadRequest("No web hook handler for request")

    return handler(payload)


def merge_request(payload: dict) -> http.HttpResponse:
    """
    Dispatch a series of emails for a merge request on Gitlab.

    The request body is a JSON document documented at
    https://docs.gitlab.com/ce/user/project/integrations/webhooks.html
    """
    if payload["object_attributes"]["action"] not in ("open", "reopen", "update"):
        _log.info(
            "Ignoring merge request web hook since its action is %s",
            payload["object_attributes"]["action"],
        )
        return http.HttpResponse(
            "Skipping event as merge request has not been opened or updated"
        )

    # GitLab web hooks are not very clearly documented and keys are not always
    # present. It *seems* that if "oldrev" is present the merge request got updated
    # code-wise (additional commits, a force push) in which case we want to send
    # out a new revision.
    if (
        payload["object_attributes"]["action"] == "update"
        and "oldrev" not in payload["object_attributes"]
    ):
        _log.info(
            "A merge request web hook arrived with the 'update' action and without "
            "an 'oldrev' key so it is being skipped. If you believe this should have "
            "sent an email, file a bug. The 'oldrev' key is undocumented and I'm "
            "totally guessing at the meaning of fields in this web hook. Sorry!"
        )
        return http.HttpResponse(
            "Skipping event as merge request hook payload is missing 'oldrev'"
        )

    project_id = payload["project"]["id"]
    merge_id = payload["object_attributes"]["iid"]
    host = urllib.parse.urlsplit(payload["project"]["web_url"]).hostname
    merge_request_hook.apply_async((host, project_id, merge_id))
    return http.HttpResponse("Success!")


def pipeline(payload: dict) -> http.HttpResponse:
    """
    Dispatch a series of emails for a merge request on Gitlab.

    This differs from :func:`merge_request` in that it only triggers if the
    pipeline for a merge request completes successfully.
    """
    pipeline = payload["object_attributes"]
    if pipeline["status"] != "success":
        _log.info(
            "Ignoring pipeline web hook since its status is %s", pipeline["status"]
        )
        return http.HttpResponse("Skipping event as pipeline was not successful")

    if pipeline["source"] != "merge_request_event":
        _log.info(
            "Ignoring pipeline web hook since its source is %s; "
            "ensure your CI job is triggered by merge requests",
            pipeline["source"],
        )
        return http.HttpResponse(
            f"Skipping pipeline as it was caused by {pipeline['source']}"
        )

    project_id = payload["project"]["id"]
    merge_id = payload["merge_request"]["iid"]
    host = urllib.parse.urlsplit(payload["project"]["web_url"]).hostname

    _log.info("Dispatching task to email merge request for pipeline")
    merge_request_hook.apply_async((host, project_id, merge_id))
    return http.HttpResponse("Success!")


def comment(payload: dict) -> http.HttpResponse:
    """
    Dispatch a comment posted on a pull request as an email in response to the
    original patch series email thread.

    The request body is a JSON document documented at
    https://docs.gitlab.com/ce/user/project/integrations/webhooks.html
    """
    project_id = payload["object_attributes"]["project_id"]
    if payload["object_attributes"]["noteable_type"] == "MergeRequest":
        merge_id = payload["merge_request"]["iid"]
    else:
        merge_id = None
    host = urllib.parse.urlsplit(payload["project"]["web_url"]).hostname

    email_comment.apply_async(
        (host, project_id, payload["user"], payload["object_attributes"], merge_id,)
    )
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
WEBHOOKS = {
    "Merge Request Hook": merge_request,
    "Note Hook": comment,
    "Pipeline Hook": pipeline,
}

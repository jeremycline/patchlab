=============
Release Notes
=============

.. towncrier release notes start

v0.5.0 (2020-05-01)
===================

This release has been tested against Patchwork 2.2.1.

Features
--------

* Add a new setting, `PATCHLAB_FROM_EMAIL`, that is then formatted with the
  "forge_user" key. The default is "Email Bridge on behalf of {forge_user}
  <bridge@example.com>". forge_user is set to the Gitlab username.

Bug Fixes
---------

* If the Patchwork project was configured with a subject_match field that
  filtered out emails sent by Patchlab, the bridge would fail without a clear
  error. An error is now logged if this occurs with clear instructions on how
  to fix it.

* Bridging emails to comments was broken unless your Patchwork project id
  somehow matched your Gitlab's project id. This has been fixed.


v0.4.0 (2020-04-27)
===================

This update contains a database migration. Be sure to run it with
``django-admin migrate`` before restarting the services.

Features
--------

* Merge request descriptions are now wrapped to 72 columns in the email
  version.

* Cc users to a merge request if tagged in the commit. A filter is available to
  ensure it only sends to particular domains. See the `PATCHLAB_CC_FILTER`
  setting.

* Add "update" to merge request hook and filters to the task so the merge
  request web hook can be used. This works when merge requests from forks are
  sent, which the Pipelines event handler does not.

Bug Fixes
---------

* Fix the "MR is too big" template to use the merge iid. If there's no
  description, include a note in the email about that. Finally, a typo was
  fixed in the template.

* Use iid rather than id for merge requests bridged from email

* The subject prefix of outgoing patches was documented as defaulting to PATCH,
  but did not actually have a default and would not allow for an empty form
  submission. Reality now more closely resembles the documentation.


v0.3.0 (2019-12-06)
===================

This update contains a database migration. Be sure to run it with
``django-admin migrate`` before restarting the services.

Features
--------

* Retry merge request creation tasks on failure.

* Add the ability to bridge emailed comments to merge requests. Emails
  containing Acked-by/Nacked-by/Reviewed-by tags cause the merge request
  to be automatically labeled as such.

* Add a web hook handler for pipeline events. It's very similar to the merge
  request event handler, except it only emails out the merge request when the
  pipeline succeeds.

* Add configuration options to turn off pieces of the email-to-Gitlab bridge.
  Consult the configuration documentation for details.

* Add a configurable label that can be applied to merge requests that should
  not be bridged to email. The default is "🛑 Do Not Email"

* When a merge request is updated (new commits, force push, or if the pipeline
  is rerun for any other reason) a series is re-emailed as a re-roll. The
  series version is incremented and the emails are sent in response to the
  previous series.

Bug Fixes
---------

* Use the merge request iid instead of the id so Patchlab works with Gitlab
  instances with more than one project.

* Don't try to retrieve the Merge Request author's email and crash if it's not
  accessible. Most users hide their email and it's not required to email the
  patches to the list in any case.

* The documentation claimed the MULTILINE and IGNORECASE flags were used when
  matching Git forge branches via the subject prefix, but they were not. This
  has been fixed.

* The series2gitlab management comment now works with Celery.

* Filter out newlines from patch subjects in the Gitlab-to-email bridge which
  caused the task to crash unexpectedly due to Django security features.


v0.2.0 (2019-11-20)
===================

Features
--------

* Apply emailed patches in asynchronous Celery tasks. Each worker creates a
  git worktree to perform its work in. These worktrees are located in the
  working directory of the task process. You can set the working directory in
  the systemd unit file or by way of the ``celery worker --workdir`` argument.

Bug Fixes
---------

* The merge request to email bridge now works with multiple development branches.

* emails sent out for merge requests now include the correct "In-Reply-To"
  header to respond to the cover letter.

* Emailed patches include authorship information.


v0.1.0 (2019-11-15)
===================

Initial release.

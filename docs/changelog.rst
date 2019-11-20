=============
Release Notes
=============

.. towncrier release notes start

v0.2.0 (2019-11-20)
===================

Features
========

* Apply emailed patches in asynchronous Celery tasks. Each worker creates a
  git worktree to perform its work in. These worktrees are located in the
  working directory of the task process. You can set the working directory in
  the systemd unit file or by way of the ``celery worker --workdir`` argument.

Bug Fixes
=========

* The merge request to email bridge now works with multiple development branches.

* emails sent out for merge requests now include the correct "In-Reply-To"
  header to respond to the cover letter.

* Emailed patches include authorship information.


v0.1.0 (2019-11-15)
===================

Initial release.

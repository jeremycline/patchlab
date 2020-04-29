.. _config:

=============
Configuration
=============

The majority of the Patchlab configuration is inside a Django settings file.

Django
======

.. automodule:: patchlab.settings.base
.. autodata:: patchlab.settings.base.PATCHLAB_GITLAB_WEBHOOK_SECRET
.. autodata:: patchlab.settings.base.PATCHLAB_MAX_EMAILS
.. autodata:: patchlab.settings.base.PATCHLAB_REPO_DIR
.. autodata:: patchlab.settings.base.PATCHLAB_EMAIL_TO_GITLAB_MR
.. autodata:: patchlab.settings.base.PATCHLAB_EMAIL_TO_GITLAB_COMMENT
.. autodata:: patchlab.settings.base.PATCHLAB_IGNORE_GITLAB_LABELS
.. autodata:: patchlab.settings.base.PATCHLAB_CC_FILTER
.. autodata:: patchlab.settings.base.PATCHLAB_PIPELINE_SUCCESS_REQUIRED
.. autodata:: patchlab.settings.base.PATCHLAB_PIPELINE_MAX_WAIT
.. autodata:: patchlab.settings.base.PATCHLAB_FROM_EMAIL


Git
===

Patchlab makes use of the ``git`` command line to apply patches and open merge
requests on GitLab. As such, the user that runs the ``parsemail.sh`` or
``series2gitlab`` service needs a valid git configuration that contains at
least a user and email::

    [user]
    email = you@example.com
    name = Your Name

Git repositories should be stored in
``PATCHLAB_REPO_DIR/<git-forge-hostname>-<git-forge-id>`` and have write access
to the "origin" remote where it pushes branches.

Gitlab
======

Patchlab uses `python-gitlab`_ when interacting with Gitlab.
``/etc/python-gitlab.cfg`` or ``~/.python-gitlab.cfg`` should contain a
configuration section for each Gitlab host being bridged::

    [global]
    ssl_verify = true
    timeout = 30

    [gitlab.example.com]
    url = https://gitlab.example.com
    private_token = abc123

    [other-gitlab.example.com]
    url = https://other-gitlab.example.com
    private_token = 123abc

For details, see the `python-gitlab documentation`_.

.. _python-gitlab: https://python-gitlab.readthedocs.io/en/stable/
.. _python-gitlab documentation: https://python-gitlab.readthedocs.io/en/stable/cli.html#configuration

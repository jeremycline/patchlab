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

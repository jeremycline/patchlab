==============
Administration
==============

Patchlab is expected to run with Patchwork as a Django application. As such,
you should start by reading the `Patchwork`_ documentation and setting it up.

Once that is complete, add in the Patchlab :ref:`config` options and start up
the Patchwork server.


Requirements
============

Patchlab must run in the same WSGI application as Patchwork.

Network
-------

For web hook support (used to bridge merge requests to email), the host must
be able to *receive* web traffic from the Git forge you are bridging. That is,
if bridging a project on gitlab.com, gitlab.com must be able to send HTTP POST
requests to your web server.

Message Broker
--------------

Patchlab uses `Celery`_ for asynchronous tasks such as handling web hooks. This
is because web hooks have a reasonably short timeout period and need to be
quickly acknowledged.

Celery requires a `message broker`_ to function. AMQP is the default and
RabbitMQ is recommended, but Redis or Amazon SQS should also be acceptable.
Celery should be configured through the Django settings.py file; consult the
Celery `configuration
<https://docs.celeryproject.org/en/latest/userguide/configuration.html>`_
documentation for possible values.


Task Workers
------------

Asynchronous tasks are completed by Celery worker processes. Celery documents
various `daemonization`_ approaches and you are free to use their approaches or
create your own systemd service.


Database
--------

Patchlab adds a few additional database tables and exposes them in the Django
admin site. As such, you will need to run ``python manage.py migrate`` after
installing the application. The tables are documented below.

Git Forges
~~~~~~~~~~

.. autoclass:: patchlab.models.GitForge

Branch
~~~~~~

.. autoclass:: patchlab.models.Branch

Bridged Submissions
~~~~~~~~~~~~~~~~~~~

.. autoclass:: patchlab.models.BridgedSubmission


URLs
====

Patchlab inserts a number of URL patterns to the Patchwork URL patterns under
the ``patchlab/`` namespace. These URLs are web hooks that must be used when
configuring each project to be bridged from the Git forge to email.

Gitlab
------

To set up a Gitlab project for bridging to email, navigate to the project's home
page, then ``Settings -> Integrations`` and fill out the form. The URL should
point to your Patchwork instance. For instance, if your Patchwork application
runs at ``/`` on your web server ``example.com``, the URL would be
``https://example.com/patchlab/gitlab/``. You must also set the secret token
to whatever you have configured ``PATCHLAB_GITLAB_SECRET`` to be.

Next, select the event(s) you would like to cause the webhook to run. Currently,
only merge request and comment events are supported.


.. _Patchwork: https://patchwork.readthedocs.io/en/latest/
.. _Celery: https://celery.readthedocs.io/en/latest/
.. _message broker: https://docs.celeryproject.org/en/latest/getting-started/brokers/
.. _daemonization: https://celery.readthedocs.io/en/latest/userguide/daemonizing.html

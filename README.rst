========
PatchLab
========

A Django application designed to run with Patchwork to mirror patches to GitLab.

Development Environment
=======================

The easiest method to set up a development environment is to use Vagrant. On
Fedora::

    $ sudo dnf install vagrant libvirt vagrant-libvirt vagrant-sshfs ansible
    $ vagrant up

This sets up two virtual machines. You can ssh to them with ``vagrant ssh pw``
and ``vagrant ssh gitlab``. The ``pw`` host contains the development
installation of PatchLab.

GitLab
------

GitLab's web UI is available at https://localhost:8443/. You'll be prompted for
a password, set one and you'll be able to log in with it and the username
"root". Cloning over SSH is available on localhost:2222.

Before you can set up a web hook you need to allow web hooks to private networks
by navigating to https://localhost:8443/admin/application_settings/network and
checking the "Allow requests to the local network from web hooks and services"
box in the Outbound requests section.

Patchwork
---------

The Patchwork web UI is available at http://localhost:8000/. Before you can log
in you need to make a super user account; you can do so with::

    $ vagrant ssh pw
    $ workon patchlab
    $ python manage.py createsuperuser

Once you've created a super user you can log into the Django admin interface at
http://localhost:8000/admin/.

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

Patchwork
---------

The Patchwork web UI is available at http://localhost:8000/.

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

GitLab's web UI is available at https://localhost:8443/.

The Ansible role restores it from backup, so there is already an administrator,
"root", with the password "password". Cloning over SSH is available on
localhost:2222.

Before you can set up a web hook you need to allow web hooks to private networks
by navigating to https://localhost:8443/admin/application_settings/network and
checking the "Allow requests to the local network from web hooks and services"
box in the Outbound requests section.

Patchwork
---------

The Patchwork web UI is available at http://localhost:8000/. A preconfigured
super user "admin" has the password "admin" which you can use to log in to
http://localhost:8000/admin/.

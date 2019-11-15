========
PatchLab
========

A Django application designed to run with Patchwork to mirror patches to GitLab.

Development Environment
=======================

The easiest method to set up a development environment is to use Vagrant. On
Fedora::

    $ sudo dnf install vagrant libvirt vagrant-libvirt vagrant-sshfs ansible
    $ vagrant up gitlab
    $ vagrant up pw

This sets up two virtual machines. You can ssh to them with ``vagrant ssh pw``
and ``vagrant ssh gitlab``. The ``pw`` host contains the development
installation of PatchLab.

GitLab
------

GitLab's web UI is available at https://localhost:8443/.

The Ansible role restores it from backup, so there is already an administrator,
"root", with the password "password". Cloning over SSH is available on
port 2222.

A test project, "patchlab_test" is available and already includes a web hook
configured for merge request events.

Patchwork
---------

The Patchwork web UI is available at http://localhost:8000/. A preconfigured
super user "admin" has the password "admin" which you can use to log in to
http://localhost:8000/admin/.

The development enviroment also includes a preconfigured Patchwork Project for
"patchlab_test", along with the necessary Git forge and branch configuration.

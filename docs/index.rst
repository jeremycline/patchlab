.. PatchLab documentation master file, created by
   sphinx-quickstart on Thu Oct 10 16:19:14 2019.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

========
Patchlab
========

Patchlab is a Django application designed to be run with `Patchwork`_ in order
to bridge the email development workflow with Gitlab project. Merge requests
are converted to patches or patch series and patches emailed to the list result
in merge requests.

User Guide
==========
.. toctree::
   :maxdepth: 2

   installation
   configuration
   administration
   changelog


Developer Guide
===============

.. toctree::
   :maxdepth: 2

   contributing


.. _Patchwork: https://github.com/getpatchwork/patchwork

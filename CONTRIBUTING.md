Contributing
============

Thanks for your interest in improving django-avatar!

django-avatar is developed and published from
https://github.com/fiduswriter/django-avatar.

Making a change
---------------

* Fork the repository and open a pull request against ``main``.
* Verify your change locally before submitting. The supported Python and
  Django versions are the ones listed in ``.github/workflows/test.yml``::

      pip install -r requirements.txt -r tests/requirements.txt
      export DJANGO_SETTINGS_MODULE=tests.settings PYTHONPATH=.
      python -m django test tests

* New features and bug fixes come with tests that exercise the new or
  fixed behavior, and with documentation updates in ``docs/``.
* Add an entry to ``CHANGELOG.rst``.
* Breaking changes: keep them to a minimum. Public function signatures,
  settings, template tags and templates, urls, migrations and existing
  stored avatar data all count as interface. If a change is not
  technically necessary, it is a breaking change we would rather not
  have. Anything unavoidable must be spelled out in the pull request
  description and in the changelog entry.

Use of AI tooling
-----------------

Using AI coding assistants while preparing a contribution is fine; we do
not police how the code in a pull request was written. You are
responsible for what you submit:

* **The code has to actually run.** Run the test suite (and, if you
  touched storage or templates, try the affected flows) yourself.
  "The tool said it works" is not a verification.
* **Tests have to test what they claim to test.** A test should fail if
  the behavior it covers is removed. Tests that merely mirror
  implementation details, assert that a function was called, or check
  strings that happen to be in the current code will be asked to be
  changed or removed.
* **Breaking changes must be minimized and justified** (see above).
* **Be prepared to talk about your code.** During review we will ask
  what parts of the change do and why they are needed. If you cannot
  explain what the tool produced, say so openly — for example: "I asked
  the tool to add feature X and I don't know enough about the
  implementation to explain it." That is an acceptable and appreciated
  answer. It means we will review more closely, ask for changes, or in
  some cases implement the feature ourselves. A pull request whose code
  nobody can explain and which shows no sign of ever having been run
  may be closed.

Untested code, invented APIs and quiet rewrites of unrelated parts of
the code base are the most common reasons contributions get rejected.
Read your own diff before requesting review.

Licensing
---------

Contributions are provided under the license documented in
``LICENSE.txt`` (LGPL-3.0-or-later), unless you explicitly state
otherwise.

Changelog
=========
* 10.0.0
    * Avatars can now be attached to model instances other than the user model (#89). ``Avatar.user`` became nullable and the new ``content_type``/``object_id`` fields hold avatars of any other model. Template tags, utility functions, forms, providers and admin all accept any model instance, and the new views ``avatar:add_object``, ``avatar:change_object`` and ``avatar:delete_object`` let them be managed through the web. See the "Avatars for other models" section of the documentation.
    * Added ``LinkAvatarProvider``, which renders a link stored on the user or model instance (for example a profile image URL obtained from a third party login) instead of an uploaded image, and which is now part of the default ``AVATAR_PROVIDERS``. The name of the field holding the link is configured with ``AVATAR_LINK_FIELD`` (#41).
    * Added ``AvatarListField`` and ``AvatarUrlField`` for serializing avatar data along with users or other models in Django REST Framework serializers (#247).
    * Changed: The shipped templates now post to the ``add_url``/``change_url``/``delete_url`` context variables instead of the hardcoded user view urls, so the same templates work for the new object avatar views. Custom avatar templates (``AVATAR_ADD_TEMPLATE`` and friends) keep working unchanged, but do not support the object views until they use these context variables: used on an object page they would otherwise post to the requesting user's avatar instead of the object's.
    * Fixed: The ``avatar.api`` application was unusable: installing it raised an ``ImportError`` at startup, and not installing it meant its ``API_AVATAR_CHANGE_IMAGE`` setting was never registered, so ``PUT`` requests raised an ``AttributeError``. It is now installed as ``avatar.api`` (see the documentation). It remains optional for users who do not use the API.
    * Changed: When the primary avatar of a user is deleted, the new primary avatar is selected by date of upload, consistent with the fallback behavior of ``get_primary_avatar``.

* 9.0.0
    * Fix files not closed in `create_thumbnail`
    * Add Django 5.2 and 6.0 support
    * Add Python 3.13, 3.14 support
    * Drop Python 3.8, 3.9 support

* 8.0.1
    * Fix Django 5.1 compatibility

* 8.0.0 (October 16, 2023)
    * Add Django 4.2 support
    * Remove Python 3.7 support
    * Use path and path converters (changes all url names from prefix `avatar_` to `avatar:`.)
    * Add support for Django STORAGES (Django 4.2)
    * Add optional api app (requires djangorestframework)
    * Use ``Image.Resampling.LANCZOS`` instead of ``Image.LANCZOS`` that was removed in Pillow 10.0.0

* 7.1.1 (February 23, 2023)
    * Switch to setuptools for building

* 7.1.0 (February 23, 2023)
    * Add LibRavatar support
    * Faster admin when many users are present
    * Check for corrupted image during upload
    * Switch Pillow Resize method from ``Image.ANTIALIAS`` to ``Image.LANCZOS``
    * Removed Python 3.6 testing
    * Added Python 3.11 support

* 7.0.1 (October 27, 2022)
    * Remove height requirement for providers (broke 6 to 7 upgrades)

* 7.0.0 (August 16, 2022)
    * Allowed for rectangular avatars. Custom avatar tag templates now require the specification of both a ``width`` and ``height`` attribute instead of ``size``.
    * Made ``True`` the default value of ``AVATAR_CLEANUP_DELETED``. (Set to ``False`` to obtain previous behavior).
    * Fix invalidate_cache for on-the-fly created thumbnails.
    * New setting ``AVATAR_ALLOWED_MIMETYPES``. If enabled, it checks mimetypes of uploaded files using ``python-magic``. Default is ``None``.
    * Fix thumbnail transposing for Safari.

* 6.0.1 (August 12, 2022)
    * Exclude tests folder from distribution.

* 6.0.0 (August 12, 2022)
    * Added Django 3.2, 4.0 and 4.1 support.
    * Removed Django 1.9, 1.10, 1.11, 2.0, 2.1, 2.2 and 3.0 support.
    * Added Python 3.9 and 3.10 support.
    * Removed Python 2.7, 3.4 and 3.5 support.
    * Made ``"PNG"`` the default value for ``AVATAR_THUMB_FORMAT`` (Set to ``"JPEG"`` to obtain previous behavior).
    * Made ``False`` the default value for ``AVATAR_EXPOSE_USERNAMES`` (Set to ``True`` to obtain previous behavior).
    * Don't leak usernames through image alt-tags when ``AVATAR_EXPOSE_USERNAMES`` is `False`.
    * New setting ``AVATAR_THUMB_MODES``. Default is ``['RGB', 'RGBA']``.
    * Use original image as thumbnail if thumbnail creation failed but image saving succeeds.
    * Add farsi translation.
    * Introduce black and flake8 linting

* 5.0.0 (January 4, 2019)
    * Added Django 2.1, 2.2, and 3.0 support.
    * Added Python 3.7 and 3.8 support.
    * Removed Python 1.9 and 1.10 support.
    * Fixed bug where avatars couldn't be deleted if file was already deleted.

* 4.1.0 (December 20, 2017)
    * Added Django 2.0 support.
    * Added ``avatar_deleted`` signal.
    * Ensure thumbnails are the correct orientation.

* 4.0.0 (May 27, 2017)
    * **Backwards incompatible:** Added ``AVATAR_PROVIDERS`` setting. Avatar providers are classes that return an avatar URL for a given user.
    * Added ``verbose_name`` to ``Avatar`` model fields.
    * Added the ability to override the ``alt`` attribute using the ``avatar`` template tag.
    * Added Italian translations.
    * Improved German translations.
    * Fixed bug where ``rebuild_avatars`` would fail on Django 1.10+.
    * Added Django 1.11 support.
    * Added Python 3.6 support.
    * Removed Django 1.7 and 1.8 support.
    * Removed Python 3.3 support.

* 3.1.0 (September 10, 2016)
    * Added the ability to override templates using ``AVATAR_ADD_TEMPLATE``, ``AVATAR_CHANGE_TEMPLATE``, and ``AVATAR_DELETE_TEMPLATE``.
    * Added the ability to pass additional HTML attributes using the ``{% avatar %}`` template tag.
    * Fixed unused verbosity setting in ``rebuild_avatars.py``.
    * Added Django 1.10 support
    * Removed Python 3.2 support

* 3.0.0 (February 26, 2016):
    * Added the ability to hide usernames/emails from avatar URLs.
    * Added the ability to use a Facebook Graph avatar as a backup.
    * Added a way to customize where avatars are stored.
    * Added a setting to disable the avatar cache.
    * Updated thumbnail creation to preserve RGBA.
    * Fixed issue where ``render_primary`` would not work if username/email was greater than 30 characters.
    * Fixed issue where cache was not invalidated after updating avatar
    * **Backwards Incompatible:** Renamed the ``avatar.util`` module to ``avatar.utils``.

* 2.2.1 (January 11, 2016)
    * Added AVATAR_GRAVATAR_FIELD setting to define the user field to get the gravatar email.
    * Improved Django 1.9/1.10 compatibility
    * Improved Brazilian translations

* 2.2.0 (December 2, 2015)
    * Added Python 3.5 support
    * Added Django 1.9 support
    * Removed Python 2.6 support
    * Removed Django 1.4, 1.5, and 1.6 support

* 2.1.1 (August 10, 2015)
    * Added Polish locale
    * Fixed RemovedInDjango19Warning warnings

* 2.1 (May 2, 2015)
    * Django 1.7 and 1.8 support
    * Add South and Django migrations
    * Changed Gravatar link to use HTTPS by default
    * Fixed a bug where the admin avatar list page would only show a user's primary avatar
    * Updated render_primary view to accept usernames with @ signs in them
    * Updated translations (added Dutch, Japanese, and Simple Chinese)

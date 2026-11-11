import hashlib

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import models as db_models
from django.template.defaultfilters import slugify
from django.utils.encoding import force_bytes, force_str

from avatar.conf import settings

cached_funcs = set()


def get_username(user):
    """Return username of a User instance"""
    if hasattr(user, "get_username"):
        return user.get_username()
    else:
        return user.username


def get_user(userdescriptor):
    """Return user from a username/ID/ish identifier"""
    User = get_user_model()
    if isinstance(userdescriptor, int):
        user = User.objects.filter(id=userdescriptor).first()
        if user:
            return user
    elif userdescriptor.isdigit():
        user = User.objects.filter(id=int(userdescriptor)).first()
        if user:
            return user
    return User.objects.get_by_natural_key(userdescriptor)


def is_object_instance(obj):
    """
    True if ``obj`` is a model instance other than an instance of the user
    model. Avatars can be attached to users and to any other model instance.
    """
    return isinstance(obj, db_models.Model) and not isinstance(obj, get_user_model())


def get_object_identifier(obj):
    """
    Returns a stable string for identifying a user or an arbitrary model
    instance in cache keys and, for users, when usernames are exposed.
    Users are identified by their username, other model instances by their
    app label, model name and primary key.
    """
    if isinstance(obj, get_user_model()):
        return get_username(obj)
    if isinstance(obj, db_models.Model):
        opts = obj._meta
        return "%s.%s-%s" % (opts.app_label, opts.model_name, obj.pk)
    return obj


def get_object_directory_name(obj):
    """
    Returns the name of the storage directory used for the avatars of a user
    or of an arbitrary model instance. The naming schemes for users and for
    other model instances cannot collide.
    """
    if isinstance(obj, get_user_model()):
        return force_str(obj.pk)
    opts = obj._meta
    return "%s_%s-%s" % (opts.app_label, opts.model_name, obj.pk)


def get_avatars(obj):
    """
    Returns the avatars attached to a user or to any other model instance,
    ordered by the primary avatar first and then by most recent upload.
    """
    from avatar.models import Avatar  # avoid a circular import at module level

    if is_object_instance(obj):
        content_type = ContentType.objects.get_for_model(obj)
        return Avatar.objects.filter(
            content_type=content_type, object_id=str(obj.pk)
        ).order_by("-primary", "-date_uploaded")
    return obj.avatar_set.order_by("-primary", "-date_uploaded")


def get_cache_key(user_or_obj, prefix, width=None, height=None):
    """
    Returns a cache key consisten of a username or model instance identifier
    and image size.
    """
    if isinstance(user_or_obj, db_models.Model):
        user_or_obj = get_object_identifier(user_or_obj)
    key = f"{prefix}_{user_or_obj}"
    if width:
        key += f"_{width}"
    if height or width:
        key += f"x{height or width}"
    return "%s_%s" % (
        slugify(key)[:100],
        hashlib.md5(force_bytes(key)).hexdigest(),
    )


def cache_set(key, value):
    cache.set(key, value, settings.AVATAR_CACHE_TIMEOUT)
    return value


def cache_result(default_size=settings.AVATAR_DEFAULT_SIZE):
    """
    Decorator to cache the result of functions that take a ``user``, a
    ``width`` and a ``height`` value.
    """
    if not settings.AVATAR_CACHE_ENABLED:

        def decorator(func):
            return func

        return decorator

    def decorator(func):
        def cached_func(user, width=None, height=None, **kwargs):
            prefix = func.__name__
            cached_funcs.add(prefix)
            key = get_cache_key(user, prefix, width or default_size, height)
            result = cache.get(key)
            if result is None:
                result = func(user, width or default_size, height, **kwargs)
                cache_set(key, result)
                # add image size to set of cached sizes so we can invalidate them later
                sizes_key = get_cache_key(user, "cached_sizes")
                sizes = cache.get(sizes_key, set())
                sizes.add((width or default_size, height or width or default_size))
                cache_set(sizes_key, sizes)
            return result

        return cached_func

    return decorator


def invalidate_cache(user, width=None, height=None):
    """
    Function to be called when saving or changing a user's avatars.
    """
    sizes_key = get_cache_key(user, "cached_sizes")
    sizes = cache.get(sizes_key, set())
    if width is not None:
        sizes.add((width, height or width))
    for prefix in cached_funcs:
        for size in sizes:
            if isinstance(size, int):
                cache.delete(get_cache_key(user, prefix, size))
            else:
                # Size is specified with height and width.
                cache.delete(get_cache_key(user, prefix, size[0], size[1]))
    cache.set(sizes_key, set())


def get_default_avatar_url():
    base_url = getattr(settings, "STATIC_URL", None)
    if not base_url:
        base_url = getattr(settings, "MEDIA_URL", "")

    # Don't use base_url if the default url starts with http:// of https://
    if settings.AVATAR_DEFAULT_URL.startswith(("http://", "https://")):
        return settings.AVATAR_DEFAULT_URL
    # We'll be nice and make sure there are no duplicated forward slashes
    ends = base_url.endswith("/")

    begins = settings.AVATAR_DEFAULT_URL.startswith("/")
    if ends and begins:
        base_url = base_url[:-1]
    elif not ends and not begins:
        return "%s/%s" % (base_url, settings.AVATAR_DEFAULT_URL)

    return "%s%s" % (base_url, settings.AVATAR_DEFAULT_URL)


def get_primary_avatar(user, width=settings.AVATAR_DEFAULT_SIZE, height=None):
    if is_object_instance(user):
        avatar = get_avatars(user).first()
    else:
        User = get_user_model()
        if not isinstance(user, User):
            try:
                user = get_user(user)
            except User.DoesNotExist:
                return None
        # Order by -primary first; this means if a primary=True avatar exists
        # it will be first, and then ordered by date uploaded, otherwise a
        # primary=False avatar will be first.  Exactly the fallback behavior we
        # want.
        avatar = get_avatars(user).first()
    if avatar:
        if not avatar.thumbnail_exists(width, height):
            avatar.create_thumbnail(width, height)
    return avatar

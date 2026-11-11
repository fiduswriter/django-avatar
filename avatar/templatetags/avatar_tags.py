from django import template
from django.db import models as db_models
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.module_loading import import_string
from django.utils.translation import gettext as _

from avatar.conf import settings
from avatar.utils import (
    cache_result,
    get_avatars,
    get_default_avatar_url,
    get_user,
    get_user_model,
    is_object_instance,
)

register = template.Library()


@cache_result()
@register.simple_tag
def avatar_url(user, width=settings.AVATAR_DEFAULT_SIZE, height=None):
    if height is None:
        height = width
    for provider_path in settings.AVATAR_PROVIDERS:
        provider = import_string(provider_path)
        avatar_url = provider.get_avatar_url(user, width, height)
        if avatar_url:
            return avatar_url
    return get_default_avatar_url()


@cache_result()
@register.simple_tag
def avatar(user, width=settings.AVATAR_DEFAULT_SIZE, height=None, **kwargs):
    if height is None:
        height = width
    if is_object_instance(user):
        if settings.AVATAR_EXPOSE_USERNAMES:
            alt = str(user)
        else:
            alt = _("Avatar")
        url = avatar_url(user, width, height)
    elif not isinstance(user, get_user_model()):
        try:
            user = get_user(user)
            if settings.AVATAR_EXPOSE_USERNAMES:
                alt = str(user)
            else:
                alt = _("User Avatar")
            url = avatar_url(user, width, height)
        except get_user_model().DoesNotExist:
            url = get_default_avatar_url()
            alt = _("Default Avatar")
    else:
        if settings.AVATAR_EXPOSE_USERNAMES:
            alt = str(user)
        else:
            alt = _("User Avatar")
        url = avatar_url(user, width, height)
    kwargs.update({"alt": alt})

    context = {
        "user": user,
        "alt": alt,
        "width": width,
        "height": height,
        "kwargs": kwargs,
    }
    template_name = "avatar/avatar_tag.html"
    ext_context = None
    try:
        template_name, ext_context = url
    except ValueError:
        context["url"] = url
    if ext_context:
        context = dict(context, **ext_context)
    return render_to_string(template_name, context)


@register.filter
def has_avatar(user):
    if not isinstance(user, db_models.Model):
        return False
    return get_avatars(user).filter(primary=True).exists()


@cache_result()
@register.simple_tag
def primary_avatar(user, width=settings.AVATAR_DEFAULT_SIZE, height=None):
    """
    This tag tries to get the default avatar for a user without doing any db
    requests. It achieve this by linking to a special view that will do all the
    work for us. If that special view is then cached by a CDN for instance,
    we will avoid many db calls.

    For avatars attached to models other than the user model the avatar URL
    is rendered directly instead.
    """
    explicit_height = height is not None
    if height is None:
        height = width
    if is_object_instance(user):
        if settings.AVATAR_EXPOSE_USERNAMES:
            alt = str(user)
        else:
            alt = _("Avatar")
        url = avatar_url(user, width, height)
        return """<img src="%s" width="%s" height="%s" alt="%s" />""" % (
            url,
            width,
            height,
            alt,
        )
    kwargs = {"width": width}
    if settings.AVATAR_EXPOSE_USERNAMES:
        alt = str(user)
        kwargs["user"] = user
    else:
        alt = _("User Avatar")
        kwargs["user"] = user.id
    if explicit_height:
        kwargs["height"] = height

    url = reverse("avatar:render_primary", kwargs=kwargs)
    return """<img src="%s" width="%s" height="%s" alt="%s" />""" % (
        url,
        width,
        height,
        alt,
    )


@cache_result()
@register.simple_tag
def render_avatar(avatar, width=settings.AVATAR_DEFAULT_SIZE, height=None):
    if height is None:
        height = width
    if not avatar.thumbnail_exists(width, height):
        avatar.create_thumbnail(width, height)
    return """<img src="%s" alt="%s" width="%s" height="%s" />""" % (
        avatar.avatar_url(width, height),
        str(avatar),
        width,
        height,
    )

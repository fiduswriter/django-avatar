import hashlib
import re
from urllib.parse import urlencode, urljoin

import dns.resolver
from django.utils.module_loading import import_string

from avatar.conf import settings
from avatar.utils import force_bytes, get_default_avatar_url, get_primary_avatar

# If the FacebookAvatarProvider is used, a mechanism needs to be defined on
# how to obtain the user's Facebook UID. This is done via
# ``AVATAR_FACEBOOK_GET_ID``.
get_facebook_id = None

if "avatar.providers.FacebookAvatarProvider" in settings.AVATAR_PROVIDERS:
    if callable(settings.AVATAR_FACEBOOK_GET_ID):
        get_facebook_id = settings.AVATAR_FACEBOOK_GET_ID
    else:
        get_facebook_id = import_string(settings.AVATAR_FACEBOOK_GET_ID)


class DefaultAvatarProvider(object):
    """
    Returns the default url defined by ``settings.DEFAULT_AVATAR_URL``.
    """

    @classmethod
    def get_avatar_url(cls, obj, width, height=None):
        return get_default_avatar_url()


class PrimaryAvatarProvider(object):
    """
    Returns the primary Avatar from the avatar set of the given user or
    model instance.
    """

    @classmethod
    def get_avatar_url(cls, obj, width, height=None):
        if not height:
            height = width
        avatar = get_primary_avatar(obj, width, height)
        if avatar:
            return avatar.avatar_url(width, height)


class LinkAvatarProvider(object):
    """
    Returns a link stored on the user or model instance itself, for example
    the URL of a profile image obtained from a third party authentication
    service. Instead of uploading an image, only the link to the image is
    stored. The field holding the link is named according to
    ``settings.AVATAR_LINK_FIELD`` (default: ``avatar_link``).

    Avatars attached to the user or model instance (i.e. stored ``Avatar``
    instances) take precedence over stored links, unless the providers are
    reordered in ``settings.AVATAR_PROVIDERS``.
    """

    @classmethod
    def get_avatar_url(cls, obj, width, height=None):
        link = getattr(obj, settings.AVATAR_LINK_FIELD, None)
        if not link:
            return None
        return str(link).strip()


class GravatarAvatarProvider(object):
    """
    Returns the url for an avatar by the Gravatar service.

    Returns ``None`` if the given user or model instance has no field named
    according to ``settings.AVATAR_GRAVATAR_FIELD``.
    """

    @classmethod
    def get_avatar_url(cls, obj, width, _height=None):
        email = getattr(obj, settings.AVATAR_GRAVATAR_FIELD, None)
        if email is None:
            return None
        params = {"s": str(width)}
        if settings.AVATAR_GRAVATAR_DEFAULT:
            params["d"] = settings.AVATAR_GRAVATAR_DEFAULT
        if settings.AVATAR_GRAVATAR_FORCEDEFAULT:
            params["f"] = "y"
        path = "%s/?%s" % (
            hashlib.md5(force_bytes(email)).hexdigest(),
            urlencode(params),
        )

        return urljoin(settings.AVATAR_GRAVATAR_BASE_URL, path)


class LibRAvatarProvider:
    """
    Returns the url of an avatar by the LibRavatar service.

    Returns ``None`` if the given user or model instance has no field named
    according to ``settings.AVATAR_GRAVATAR_FIELD``.
    """

    @classmethod
    def get_avatar_url(cls, obj, width, _height=None):
        email = getattr(obj, settings.AVATAR_GRAVATAR_FIELD, None)
        if email is None:
            return None
        email = email.encode("utf-8")
        try:
            _, domain = email.split(b"@")
            answers = dns.resolver.query("_avatars._tcp." + domain, "SRV")
            hostname = re.sub(r"\.$", "", str(answers[0].target))
            # query returns "example.com." and while http requests are fine with this,
            # https most certainly do not consider "example.com." and "example.com" to be the same.
            port = str(answers[0].port)
            if port == "443":
                baseurl = "https://" + hostname + "/avatar/"
            else:
                baseurl = "http://" + hostname + ":" + port + "/avatar/"
        except Exception:
            baseurl = "https://seccdn.libravatar.org/avatar/"

        params = {"s": str(width)}
        if settings.AVATAR_GRAVATAR_DEFAULT:
            params["d"] = settings.AVATAR_GRAVATAR_DEFAULT
        if settings.AVATAR_GRAVATAR_FORCEDEFAULT:
            params["f"] = "y"
        path = "%s/?%s" % (
            hashlib.md5(force_bytes(email.strip().lower())).hexdigest(),
            urlencode(params),
        )
        return urljoin(baseurl, path)


class FacebookAvatarProvider(object):
    """
    Returns the url of a Facebook profile image.
    """

    @classmethod
    def get_avatar_url(cls, obj, width, height=None):
        if not height:
            height = width
        fb_id = get_facebook_id(obj)
        if fb_id:
            url = "https://graph.facebook.com/{fb_id}/picture?type=square&width={width}&height={height}"
            return url.format(fb_id=fb_id, width=width, height=height)


class InitialsAvatarProvider(object):
    """
    Returns a tuple with template_name and context for rendering the given
    user's or model instance's avatar as their initials in white against a
    background with random hue based on their primary key.
    """

    @classmethod
    def get_avatar_url(cls, obj, width, _height=None):
        initials = (
            getattr(obj, "first_name", "")[:1] + getattr(obj, "last_name", "")[:1]
        )
        if not initials:
            if hasattr(obj, "username"):
                initials = obj.username[:1]
            else:
                initials = str(obj)[:1]
        initials = initials.upper()
        context = {
            "fontsize": (width * 1.1) / 2,
            "initials": initials,
            "hue": obj.pk % 360,
            "saturation": "65%",
            "lightness": "60%",
        }
        return ("avatar/initials.html", context)

from appconf import AppConf
from django.conf import settings
from PIL import Image


class AvatarConf(AppConf):
    DEFAULT_SIZE = 80
    RESIZE_METHOD = Image.Resampling.LANCZOS
    STORAGE_DIR = "avatars"
    PATH_HANDLER = "avatar.models.avatar_path_handler"
    GRAVATAR_BASE_URL = "https://www.gravatar.com/avatar/"
    GRAVATAR_FIELD = "email"
    GRAVATAR_DEFAULT = None
    AVATAR_GRAVATAR_FORCEDEFAULT = False
    DEFAULT_URL = "avatar/img/default.jpg"
    MAX_AVATARS_PER_USER = 42
    MAX_SIZE = 1024 * 1024
    THUMB_FORMAT = "PNG"
    THUMB_QUALITY = 85
    THUMB_MODES = ("RGB", "RGBA")
    HASH_FILENAMES = False
    HASH_USERDIRNAMES = False
    EXPOSE_USERNAMES = False
    ALLOWED_FILE_EXTS = None
    ALLOWED_MIMETYPES = None
    CACHE_TIMEOUT = 60 * 60
    if hasattr(settings, "DEFAULT_FILE_STORAGE"):
        STORAGE = settings.DEFAULT_FILE_STORAGE  # deprecated settings
    STORAGE_ALIAS = "default"
    CLEANUP_DELETED = True
    AUTO_GENERATE_SIZES = (DEFAULT_SIZE,)
    FACEBOOK_GET_ID = None
    CACHE_ENABLED = True
    RANDOMIZE_HASHES = False
    ADD_TEMPLATE = ""
    CHANGE_TEMPLATE = ""
    DELETE_TEMPLATE = ""
    # Field on a user or model instance that holds a stored avatar link
    # (e.g. a profile image URL obtained from a third party login).
    LINK_FIELD = "avatar_link"
    # Callable taking (request, obj) and returning whether the request may
    # manage the avatars of the non-user object ``obj``.
    OBJECT_PERMISSION = "avatar.views.default_object_permission"
    PROVIDERS = (
        "avatar.providers.PrimaryAvatarProvider",
        "avatar.providers.LinkAvatarProvider",
        "avatar.providers.LibRAvatarProvider",
        "avatar.providers.GravatarAvatarProvider",
        "avatar.providers.DefaultAvatarProvider",
    )

    def configure_auto_generate_avatar_sizes(self, value):
        return value or getattr(
            settings, "AVATAR_AUTO_GENERATE_SIZES", (self.DEFAULT_SIZE,)
        )

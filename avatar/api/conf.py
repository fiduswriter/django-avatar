from appconf import AppConf
from django.conf import (  # noqa: F401 -- re-exported by `from .conf import settings`
    settings,
)


class AvatarAPIConf(AppConf):
    # allow updating avatar image in put method
    AVATAR_CHANGE_IMAGE = False

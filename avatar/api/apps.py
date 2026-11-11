from django.apps import AppConfig
from django.db.models import signals


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "avatar.api"

    def ready(self):
        from avatar.models import Avatar

        from .conf import settings as api_settings
        from .signals import (
            create_default_thumbnails,
            remove_previous_avatar_images_when_update,
        )

        if api_settings.API_AVATAR_CHANGE_IMAGE:
            signals.pre_save.connect(
                remove_previous_avatar_images_when_update, sender=Avatar
            )
            signals.post_save.connect(create_default_thumbnails, sender=Avatar)

from django.contrib import admin
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from avatar.models import Avatar
from avatar.signals import avatar_updated
from avatar.utils import get_user_model


class AvatarAdmin(admin.ModelAdmin):
    list_display = ("get_avatar", "owner", "primary", "date_uploaded")
    list_filter = ("primary", "content_type")
    autocomplete_fields = ("user",)
    search_fields = (
        "user__%s" % getattr(get_user_model(), "USERNAME_FIELD", "username"),
        "object_id",
    )
    list_per_page = 50

    @admin.display(description=_("Owner"))
    def owner(self, avatar_in):
        return str(avatar_in.owner)

    def get_avatar(self, avatar_in):
        context = {
            "user": avatar_in.owner,
            "url": avatar_in.avatar.url,
            "alt": str(avatar_in.owner),
            "size": 80,
        }
        return render_to_string("avatar/avatar_tag.html", context)

    get_avatar.short_description = _("Avatar")
    get_avatar.allow_tags = True

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        avatar_updated.send(sender=Avatar, user=request.user, avatar=obj)


admin.site.register(Avatar, AvatarAdmin)

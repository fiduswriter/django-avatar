import os

from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps
from rest_framework import serializers

from avatar.conf import settings
from avatar.conf import settings as api_setting
from avatar.models import Avatar
from avatar.utils import (
    get_avatars,
    get_default_avatar_url,
    get_primary_avatar,
)


class AvatarSerializer(serializers.ModelSerializer):
    avatar_url = serializers.HyperlinkedIdentityField(
        view_name="avatar-detail",
    )
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Avatar
        fields = ["id", "avatar_url", "avatar", "primary", "user"]
        extra_kwargs = {"avatar": {"required": True}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = kwargs.get("context").get("request", None)

        self.user = request.user

    def get_fields(self, *args, **kwargs):
        fields = super(AvatarSerializer, self).get_fields(*args, **kwargs)
        request = self.context.get("request", None)

        # remove avatar url field in detail page
        if bool(self.context.get("view").kwargs):
            fields.pop("avatar_url")

        # remove avatar field in put method
        if request and getattr(request, "method", None) == "PUT":
            # avatar updates only when primary=true and API_AVATAR_CHANGE_IMAGE = True
            if (
                not api_setting.API_AVATAR_CHANGE_IMAGE
                or self.instance
                and not self.instance.primary
            ):
                fields.pop("avatar")
            else:
                fields.get("avatar", None).required = False
        return fields

    def validate_avatar(self, value):
        data = value

        if settings.AVATAR_ALLOWED_MIMETYPES:
            try:
                import magic
            except ImportError:
                raise ImportError(
                    "python-magic library must be installed in order to use uploaded file content limitation"
                )

            # Construct 256 bytes needed for mime validation
            magic_buffer = bytes()
            for chunk in data.chunks():
                magic_buffer += chunk
                if len(magic_buffer) >= 256:
                    break

            # https://github.com/ahupp/python-magic#usage
            mime = magic.from_buffer(magic_buffer, mime=True)
            if mime not in settings.AVATAR_ALLOWED_MIMETYPES:
                raise serializers.ValidationError(
                    _(
                        "File content is invalid. Detected: %(mimetype)s Allowed content types are: %(valid_mime_list)s"
                    )
                    % {
                        "valid_mime_list": ", ".join(settings.AVATAR_ALLOWED_MIMETYPES),
                        "mimetype": mime,
                    }
                )

        if settings.AVATAR_ALLOWED_FILE_EXTS:
            root, ext = os.path.splitext(data.name.lower())
            if ext not in settings.AVATAR_ALLOWED_FILE_EXTS:
                valid_exts = ", ".join(settings.AVATAR_ALLOWED_FILE_EXTS)
                error = _(
                    "%(ext)s is an invalid file extension. "
                    "Authorized extensions are : %(valid_exts_list)s"
                )
                raise serializers.ValidationError(
                    error % {"ext": ext, "valid_exts_list": valid_exts}
                )

        if data.size > settings.AVATAR_MAX_SIZE:
            error = _(
                "Your file is too big (%(size)s), "
                "the maximum allowed size is %(max_valid_size)s"
            )
            raise serializers.ValidationError(
                error
                % {
                    "size": filesizeformat(data.size),
                    "max_valid_size": filesizeformat(settings.AVATAR_MAX_SIZE),
                }
            )

        try:
            image = Image.open(data)
            ImageOps.exif_transpose(image)
        except TypeError:
            raise serializers.ValidationError(_("Corrupted image"))

        count = Avatar.objects.filter(user=self.user).count()
        if 1 < settings.AVATAR_MAX_AVATARS_PER_USER <= count:
            error = _(
                "You already have %(nb_avatars)d avatars, "
                "and the maximum allowed is %(nb_max_avatars)d."
            )
            raise serializers.ValidationError(
                error
                % {
                    "nb_avatars": count,
                    "nb_max_avatars": settings.AVATAR_MAX_AVATARS_PER_USER,
                }
            )
        return data


class _AvatarSizedFieldMixin:
    """
    Shared width/height handling for the avatar serialization fields.
    """

    def __init__(self, width=None, height=None, *args, **kwargs):
        self.width = width or settings.AVATAR_DEFAULT_SIZE
        self.height = height or self.width
        # The fields serialize the whole user or model instance they are
        # declared on, not one of its attributes.
        kwargs.setdefault("source", "*")
        super().__init__(*args, **kwargs)


class AvatarListField(_AvatarSizedFieldMixin, serializers.SerializerMethodField):
    """
    Read-only field that serializes the full list of avatars attached to the
    user or model instance being serialized, along with its other fields.
    Each avatar is rendered as a dictionary with its ``id``, the URL of the
    resized image, whether it is the primary avatar and its upload date.

    Use it in your own serializer::

        class UserSerializer(serializers.ModelSerializer):
            avatars = AvatarListField(width=80, height=80)

            class Meta:
                model = get_user_model()
                fields = ("username", "avatars")
    """

    def to_representation(self, value):
        date_field = serializers.DateTimeField()
        result = []
        for avatar in get_avatars(value):
            if not avatar.thumbnail_exists(self.width, self.height):
                avatar.create_thumbnail(self.width, self.height)
            result.append(
                {
                    "id": avatar.pk,
                    "url": avatar.avatar_url(self.width, self.height),
                    "primary": avatar.primary,
                    "date_uploaded": date_field.to_representation(avatar.date_uploaded),
                }
            )
        return result


class AvatarUrlField(_AvatarSizedFieldMixin, serializers.SerializerMethodField):
    """
    Read-only field serializing the URL of the primary avatar of the user or
    model instance being serialized, resized to the given width and height.
    Falls back to the default avatar URL when no avatar exists.
    """

    def to_representation(self, value):
        avatar = get_primary_avatar(value, width=self.width, height=self.height)
        if avatar:
            return avatar.avatar_url(self.width, self.height)
        return get_default_avatar_url()

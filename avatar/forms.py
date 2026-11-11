import os

from django import forms
from django.forms import widgets
from django.template.defaultfilters import filesizeformat
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps

from avatar.conf import settings
from avatar.utils import get_avatars


def avatar_img(avatar, width, height):
    if not avatar.thumbnail_exists(width, height):
        avatar.create_thumbnail(width, height)
    return mark_safe(
        '<img src="%s" alt="%s" width="%s" height="%s" />'
        % (avatar.avatar_url(width, height), str(avatar), width, height)
    )


class UploadAvatarForm(forms.Form):
    avatar = forms.ImageField(label=_("avatar"))

    def __init__(self, *args, **kwargs):
        # The user or model instance the avatar should be attached to.
        self.obj = kwargs.pop("obj")
        super().__init__(*args, **kwargs)

    def clean_avatar(self):
        data = self.cleaned_data["avatar"]

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
                raise forms.ValidationError(
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
                raise forms.ValidationError(
                    error % {"ext": ext, "valid_exts_list": valid_exts}
                )

        if data.size > settings.AVATAR_MAX_SIZE:
            error = _(
                "Your file is too big (%(size)s), "
                "the maximum allowed size is %(max_valid_size)s"
            )
            raise forms.ValidationError(
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
            raise forms.ValidationError(_("Corrupted image"))

        count = get_avatars(self.obj).count()
        if 1 < settings.AVATAR_MAX_AVATARS_PER_USER <= count:
            error = _(
                "You already have %(nb_avatars)d avatars, "
                "and the maximum allowed is %(nb_max_avatars)d."
            )
            raise forms.ValidationError(
                error
                % {
                    "nb_avatars": count,
                    "nb_max_avatars": settings.AVATAR_MAX_AVATARS_PER_USER,
                }
            )
        return


class PrimaryAvatarForm(forms.Form):
    def __init__(self, *args, **kwargs):
        kwargs.pop("obj")
        width = kwargs.pop("width", settings.AVATAR_DEFAULT_SIZE)
        height = kwargs.pop("height", settings.AVATAR_DEFAULT_SIZE)
        avatars = kwargs.pop("avatars")
        super().__init__(*args, **kwargs)
        self.fields["choice"] = forms.ChoiceField(
            choices=[(c.id, avatar_img(c, width, height)) for c in avatars],
            widget=widgets.RadioSelect,
        )


class DeleteAvatarForm(forms.Form):
    def __init__(self, *args, **kwargs):
        kwargs.pop("obj")
        width = kwargs.pop("width", settings.AVATAR_DEFAULT_SIZE)
        height = kwargs.pop("height", settings.AVATAR_DEFAULT_SIZE)
        avatars = kwargs.pop("avatars")
        super().__init__(*args, **kwargs)
        self.fields["choices"] = forms.MultipleChoiceField(
            label=_("Choices"),
            choices=[(c.id, avatar_img(c, width, height)) for c in avatars],
            widget=widgets.CheckboxSelectMultiple,
        )

import binascii
import hashlib
import os
from contextlib import closing
from io import BytesIO

from django.core.files import File
from django.core.files.base import ContentFile
from django.db import models
from django.db.models import signals
from django.utils.encoding import force_bytes, force_str
from django.utils.module_loading import import_string
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps

from avatar.conf import settings
from avatar.utils import get_username, invalidate_cache

try:  # Django 4.2+
    from django.core.files.storage import storages

    avatar_storage = storages[settings.AVATAR_STORAGE_ALIAS]
except ImportError:
    from django.core.files.storage import get_storage_class

    avatar_storage = get_storage_class(settings.AVATAR_STORAGE)()


def avatar_path_handler(
    instance=None, filename=None, width=None, height=None, ext=None
):
    tmppath = [settings.AVATAR_STORAGE_DIR]
    if settings.AVATAR_HASH_USERDIRNAMES:
        tmp = hashlib.md5(force_bytes(get_username(instance.user))).hexdigest()
        tmppath.extend(tmp[0:2])
    if settings.AVATAR_EXPOSE_USERNAMES:
        tmppath.append(get_username(instance.user))
    else:
        tmppath.append(force_str(instance.user.pk))
    if not filename:
        # Filename already stored in database
        filename = instance.avatar.name
        if ext:
            (root, oldext) = os.path.splitext(filename)
            filename = root + "." + ext.lower()
    else:
        # File doesn't exist yet
        (root, oldext) = os.path.splitext(filename)
        if settings.AVATAR_HASH_FILENAMES:
            if settings.AVATAR_RANDOMIZE_HASHES:
                root = binascii.hexlify(os.urandom(16)).decode("ascii")
            else:
                root = hashlib.md5(force_bytes(root)).hexdigest()
        if ext:
            filename = root + "." + ext.lower()
        else:
            filename = root + oldext.lower()
    if width or height:
        tmppath.extend(["resized", str(width), str(height)])
    tmppath.append(os.path.basename(filename))
    return os.path.join(*tmppath)


avatar_file_path = import_string(settings.AVATAR_PATH_HANDLER)


def find_extension(format):
    format = format.lower()

    if format == "jpeg":
        format = "jpg"

    return format


class AvatarField(models.ImageField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.max_length = 1024
        self.upload_to = avatar_file_path
        self.storage = avatar_storage
        self.blank = True

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, (), {}


class Avatar(models.Model):
    user = models.ForeignKey(
        getattr(settings, "AUTH_USER_MODEL", "auth.User"),
        verbose_name=_("user"),
        on_delete=models.CASCADE,
    )
    primary = models.BooleanField(
        verbose_name=_("primary"),
        default=False,
    )
    avatar = AvatarField(verbose_name=_("avatar"))
    date_uploaded = models.DateTimeField(
        verbose_name=_("uploaded at"),
        default=now,
    )

    class Meta:
        app_label = "avatar"
        verbose_name = _("avatar")
        verbose_name_plural = _("avatars")

    def __str__(self):
        return _("Avatar for %s") % self.user

    def save(self, *args, **kwargs):
        avatars = Avatar.objects.filter(user=self.user)
        if self.pk:
            avatars = avatars.exclude(pk=self.pk)
        if settings.AVATAR_MAX_AVATARS_PER_USER > 1:
            if self.primary:
                avatars = avatars.filter(primary=True)
                avatars.update(primary=False)
        else:
            avatars.delete()
        super().save(*args, **kwargs)

    def thumbnail_exists(self, width, height=None):
        return self.avatar.storage.exists(self.avatar_name(width, height))

    def transpose_image(self, image):
        EXIF_ORIENTATION = 0x0112
        exif_code = image.getexif().get(EXIF_ORIENTATION, 1)
        if exif_code and exif_code != 1:
            image = ImageOps.exif_transpose(image)
        return image

    def create_thumbnail(self, width, height=None, quality=None):
        if height is None:
            height = width
        # invalidate the cache of the thumbnail with the given size first
        invalidate_cache(self.user, width, height)
        try:
            orig = self.avatar.storage.open(self.avatar.name, "rb")
        except IOError:
            return  # What should we do here?  Render a "sorry, didn't work" img?

        with closing(orig):
            try:
                image = Image.open(orig)
            except IOError:
                thumb_file = File(orig)
            else:
                image = self.transpose_image(image)
                quality = quality or settings.AVATAR_THUMB_QUALITY
                w, h = image.size
                if w != width or h != height:
                    ratioReal = 1.0 * w / h
                    ratioWant = 1.0 * width / height
                    if ratioReal > ratioWant:
                        diff = int((w - (h * ratioWant)) / 2)
                        image = image.crop((diff, 0, w - diff, h))
                    elif ratioReal < ratioWant:
                        diff = int((h - (w / ratioWant)) / 2)
                        image = image.crop((0, diff, w, h - diff))
                    if settings.AVATAR_THUMB_FORMAT == "JPEG" and image.mode == "RGBA":
                        image = image.convert("RGB")
                    elif image.mode not in (settings.AVATAR_THUMB_MODES):
                        image = image.convert(settings.AVATAR_THUMB_MODES[0])
                    image = image.resize((width, height), settings.AVATAR_RESIZE_METHOD)
                    thumb = BytesIO()
                    image.save(thumb, settings.AVATAR_THUMB_FORMAT, quality=quality)
                    thumb_file = ContentFile(thumb.getvalue())
                else:
                    thumb_file = File(orig)
            thumb_name = self.avatar_name(width, height)
            thumb = self.avatar.storage.save(thumb_name, thumb_file)
            invalidate_cache(self.user, width, height)

    def avatar_url(self, width, height=None):
        return self.avatar.storage.url(self.avatar_name(width, height))

    def get_absolute_url(self):
        return self.avatar_url(settings.AVATAR_DEFAULT_SIZE)

    def avatar_name(self, width, height=None):
        if height is None:
            height = width
        ext = find_extension(settings.AVATAR_THUMB_FORMAT)
        return avatar_file_path(instance=self, width=width, height=height, ext=ext)


def invalidate_avatar_cache(sender, instance, **kwargs):
    if hasattr(instance, "user"):
        invalidate_cache(instance.user)


def create_default_thumbnails(sender, instance, created=False, **kwargs):
    invalidate_avatar_cache(sender, instance)
    if created:
        for size in settings.AVATAR_AUTO_GENERATE_SIZES:
            if isinstance(size, int):
                instance.create_thumbnail(size, size)
            else:
                # Size is specified with height and width.
                instance.create_thumbnail(size[0], size[1])


def remove_avatar_images(instance=None, delete_main_avatar=True, **kwargs):
    base_filepath = instance.avatar.name
    path, filename = os.path.split(base_filepath)
    # iterate through resized avatars directories and delete resized avatars
    resized_path = os.path.join(path, "resized")
    try:
        resized_widths, _ = instance.avatar.storage.listdir(resized_path)
    except FileNotFoundError:
        resized_widths = []
    for width in resized_widths:
        resized_width_path = os.path.join(resized_path, width)
        resized_heights, _ = instance.avatar.storage.listdir(resized_width_path)
        for height in resized_heights:
            if instance.thumbnail_exists(width, height):
                instance.avatar.storage.delete(instance.avatar_name(width, height))
    if delete_main_avatar:
        if instance.avatar.storage.exists(instance.avatar.name):
            instance.avatar.storage.delete(instance.avatar.name)


signals.post_save.connect(create_default_thumbnails, sender=Avatar)
signals.post_delete.connect(invalidate_avatar_cache, sender=Avatar)

if settings.AVATAR_CLEANUP_DELETED:
    signals.post_delete.connect(remove_avatar_images, sender=Avatar)

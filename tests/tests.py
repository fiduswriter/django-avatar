import math
import os.path
import sys
from pathlib import Path
from shutil import rmtree
from unittest import skipIf

from django.contrib.admin.sites import AdminSite
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.core import management
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files import File
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from PIL import Image, ImageChops
from rest_framework import serializers as drf_serializers

from avatar.admin import AvatarAdmin
from avatar.api.serializers import AvatarListField, AvatarUrlField
from avatar.conf import settings
from avatar.models import Avatar
from avatar.providers import (
    GravatarAvatarProvider,
    LibRAvatarProvider,
    LinkAvatarProvider,
)
from avatar.signals import avatar_deleted
from avatar.templatetags import avatar_tags
from avatar.utils import (
    get_avatars,
    get_cache_key,
    get_default_avatar_url,
    get_primary_avatar,
    get_user_model,
    invalidate_cache,
)


class AssertSignal:
    def __init__(self):
        self.signal_sent_count = 0
        self.avatar = None
        self.user = None
        self.sender = None
        self.signal = None

    def __call__(self, user, avatar, sender, signal):
        self.user = user
        self.avatar = avatar
        self.sender = sender
        self.signal = signal
        self.signal_sent_count += 1


def upload_helper(o, filename):
    f = open(os.path.join(o.testdatapath, filename), "rb")
    response = o.client.post(
        reverse("avatar:add"),
        {
            "avatar": f,
        },
        follow=True,
    )
    f.close()
    return response


def root_mean_square_difference(image1, image2):
    "Calculate the root-mean-square difference between two images"
    diff = ImageChops.difference(image1, image2).convert("L")
    h = diff.histogram()
    sq = (value * (idx**2) for idx, value in enumerate(h))
    sum_of_squares = sum(sq)
    rms = math.sqrt(sum_of_squares / float(image1.size[0] * image1.size[1]))
    return rms


class AvatarTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = os.path.dirname(__file__)
        cls.testdatapath = os.path.join(cls.path, "data")
        cls.testmediapath = os.path.join(cls.path, "../test-media/")
        return super().setUpClass()

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "test", "lennon@thebeatles.com", "testpassword"
        )
        self.user.save()
        self.client.login(username="test", password="testpassword")
        self.site = AdminSite()
        Image.init()

    def tearDown(self):
        if os.path.exists(self.testmediapath):
            rmtree(self.testmediapath)
        return super().tearDown()

    def assertMediaFileExists(self, path):
        full_path = os.path.join(self.testmediapath, f".{path}")
        if not Path(full_path).resolve().is_file():
            raise AssertionError(f"File does not exist: {full_path}")

    def test_admin_get_avatar_returns_different_image_tags(self):
        self.test_normal_image_upload()
        self.test_normal_image_upload()
        primary = Avatar.objects.get(primary=True)
        old = Avatar.objects.get(primary=False)

        aa = AvatarAdmin(Avatar, self.site)
        primary_link = aa.get_avatar(primary)
        old_link = aa.get_avatar(old)

        self.assertNotEqual(primary_link, old_link)

    def test_non_image_upload(self):
        response = upload_helper(self, "nonimagefile")
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.context["upload_avatar_form"].errors, {})

    def test_normal_image_upload(self):
        response = upload_helper(self, "test.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertEqual(response.context["upload_avatar_form"].errors, {})
        avatar = get_primary_avatar(self.user)
        self.assertIsNotNone(avatar)
        self.assertEqual(avatar.user, self.user)
        self.assertTrue(avatar.primary)

    # We allow the .tiff file extension but not the mime type
    @skipIf(sys.platform == "win32", "Skipping test on Windows platform")
    @override_settings(AVATAR_ALLOWED_FILE_EXTS=(".png", ".gif", ".jpg", ".tiff"))
    @override_settings(
        AVATAR_ALLOWED_MIMETYPES=("image/png", "image/gif", "image/jpeg")
    )
    def test_unsupported_image_format_upload(self):
        """Check with python-magic that we detect corrupted / unapprovd image files correctly"""
        response = upload_helper(self, "test.tiff")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.redirect_chain), 0)  # Redirect only if it worked
        self.assertNotEqual(response.context["upload_avatar_form"].errors, {})

    # We allow the .tiff file extension and the mime type
    @skipIf(sys.platform == "win32", "Skipping test on Windows platform")
    @override_settings(AVATAR_ALLOWED_FILE_EXTS=(".png", ".gif", ".jpg", ".tiff"))
    @override_settings(
        AVATAR_ALLOWED_MIMETYPES=("image/png", "image/gif", "image/jpeg", "image/tiff")
    )
    def test_supported_image_format_upload(self):
        """Check with python-magic that we detect corrupted / unapprovd image files correctly"""
        response = upload_helper(self, "test.tiff")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.redirect_chain), 1)  # Redirect only if it worked
        self.assertEqual(response.context["upload_avatar_form"].errors, {})

    @skipIf(sys.platform == "win32", "Skipping test on Windows platform")
    @override_settings(AVATAR_ALLOWED_FILE_EXTS=(".jpg", ".png"))
    def test_image_without_wrong_extension(self):
        response = upload_helper(self, "imagefilewithoutext")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.redirect_chain), 0)  # Redirect only if it worked
        self.assertNotEqual(response.context["upload_avatar_form"].errors, {})

    @skipIf(sys.platform == "win32", "Skipping test on Windows platform")
    @override_settings(AVATAR_ALLOWED_FILE_EXTS=(".jpg", ".png"))
    def test_image_with_wrong_extension(self):
        response = upload_helper(self, "imagefilewithwrongext.ogg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.redirect_chain), 0)  # Redirect only if it worked
        self.assertNotEqual(response.context["upload_avatar_form"].errors, {})

    def test_image_too_big(self):
        # use with AVATAR_MAX_SIZE = 1024 * 1024
        response = upload_helper(self, "testbig.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.redirect_chain), 0)  # Redirect only if it worked
        self.assertNotEqual(response.context["upload_avatar_form"].errors, {})

    def test_default_url(self):
        response = self.client.get(
            reverse(
                "avatar:render_primary",
                kwargs={
                    "user": self.user.username,
                    "width": 80,
                },
            )
        )
        loc = response["Location"]
        base_url = getattr(settings, "STATIC_URL", None)
        if not base_url:
            base_url = settings.MEDIA_URL
        self.assertTrue(base_url in loc)
        self.assertTrue(loc.endswith(settings.AVATAR_DEFAULT_URL))

    def test_non_existing_user(self):
        a = get_primary_avatar("nonexistinguser")
        self.assertEqual(a, None)

    def test_there_can_be_only_one_primary_avatar(self):
        for _ in range(1, 10):
            self.test_normal_image_upload()
        count = Avatar.objects.filter(user=self.user, primary=True).count()
        self.assertEqual(count, 1)

    def test_delete_avatar(self):
        self.test_normal_image_upload()
        avatar = Avatar.objects.filter(user=self.user)
        self.assertEqual(len(avatar), 1)
        receiver = AssertSignal()
        avatar_deleted.connect(receiver)
        response = self.client.post(
            reverse("avatar:delete"),
            {
                "choices": [avatar[0].id],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.redirect_chain), 1)
        count = Avatar.objects.filter(user=self.user).count()
        self.assertEqual(count, 0)
        self.assertEqual(receiver.user, self.user)
        self.assertEqual(receiver.avatar, avatar[0])
        self.assertEqual(receiver.sender, Avatar)
        self.assertEqual(receiver.signal_sent_count, 1)

    def test_delete_avatar_without_resized_directory(self):
        self.test_normal_image_upload()
        avatar = Avatar.objects.get(user=self.user)
        resized_path = os.path.join(
            self.testmediapath,
            os.path.dirname(avatar.avatar.name),
            "resized",
        )
        if os.path.exists(resized_path):
            rmtree(resized_path)
        avatar.delete()
        self.assertEqual(Avatar.objects.filter(user=self.user).count(), 0)

    def test_delete_primary_avatar_and_new_primary(self):
        self.test_there_can_be_only_one_primary_avatar()
        primary = get_primary_avatar(self.user)
        oid = primary.id
        self.client.post(
            reverse("avatar:delete"),
            {
                "choices": [oid],
            },
        )
        primaries = Avatar.objects.filter(user=self.user, primary=True)
        self.assertEqual(len(primaries), 1)
        self.assertNotEqual(oid, primaries[0].id)
        avatars = get_avatars(self.user)
        self.assertEqual(avatars[0].id, primaries[0].id)

    def test_change_avatar_get(self):
        self.test_normal_image_upload()
        response = self.client.get(reverse("avatar:change"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["avatar"])

    def test_change_avatar_post_updates_primary_avatar(self):
        self.test_there_can_be_only_one_primary_avatar()
        old_primary = Avatar.objects.get(user=self.user, primary=True)
        choice = Avatar.objects.filter(user=self.user, primary=False)[0]
        response = self.client.post(
            reverse("avatar:change"),
            {
                "choice": choice.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        new_primary = Avatar.objects.get(user=self.user, primary=True)
        self.assertEqual(new_primary.pk, choice.pk)
        # Avatar with old primary pk exists but it is not primary anymore
        self.assertTrue(
            Avatar.objects.filter(
                user=self.user, pk=old_primary.pk, primary=False
            ).exists()
        )

    def test_too_many_avatars(self):
        for _ in range(0, settings.AVATAR_MAX_AVATARS_PER_USER):
            self.test_normal_image_upload()
        count_before = Avatar.objects.filter(user=self.user).count()
        response = upload_helper(self, "test.png")
        count_after = Avatar.objects.filter(user=self.user).count()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.redirect_chain), 0)  # Redirect only if it worked
        self.assertNotEqual(response.context["upload_avatar_form"].errors, {})
        self.assertEqual(count_before, count_after)

    def test_automatic_thumbnail_creation_RGBA(self):
        upload_helper(self, "django.png")
        avatar = get_primary_avatar(self.user)
        image = Image.open(
            avatar.avatar.storage.open(
                avatar.avatar_name(settings.AVATAR_DEFAULT_SIZE), "rb"
            )
        )
        self.assertEqual(image.mode, "RGBA")

    @override_settings(AVATAR_THUMB_FORMAT="JPEG")
    def test_automatic_thumbnail_creation_CMYK(self):
        upload_helper(self, "django_pony_cmyk.jpg")
        avatar = get_primary_avatar(self.user)
        image = Image.open(
            avatar.avatar.storage.open(
                avatar.avatar_name(settings.AVATAR_DEFAULT_SIZE), "rb"
            )
        )
        self.assertEqual(image.mode, "RGB")

    def test_automatic_thumbnail_creation_image_type_conversion(self):
        upload_helper(self, "django_pony_cmyk.jpg")
        self.assertMediaFileExists(
            f"/avatars/{self.user.id}/resized/80/80/django_pony_cmyk.png"
        )

    def test_thumbnail_transpose_based_on_exif(self):
        upload_helper(self, "image_no_exif.jpg")
        avatar = get_primary_avatar(self.user)
        image_no_exif = Image.open(
            avatar.avatar.storage.open(
                avatar.avatar_name(settings.AVATAR_DEFAULT_SIZE), "rb"
            )
        )

        upload_helper(self, "image_exif_orientation.jpg")
        avatar = get_primary_avatar(self.user)
        image_with_exif = Image.open(
            avatar.avatar.storage.open(
                avatar.avatar_name(settings.AVATAR_DEFAULT_SIZE), "rb"
            )
        )

        self.assertLess(root_mean_square_difference(image_with_exif, image_no_exif), 1)

    def test_automatic_thumbnail_creation_nondefault_filename(self):
        upload_helper(self, "django #3.png")
        self.assertMediaFileExists(
            f"/avatars/{self.user.id}/resized/80/80/django_3.png"
        )

    def test_has_avatar_False_if_no_avatar(self):
        self.assertFalse(avatar_tags.has_avatar(self.user))

    def test_has_avatar_False_if_not_user_model(self):
        self.assertFalse(avatar_tags.has_avatar("Look, I'm a string"))

    def test_has_avatar_True(self):
        upload_helper(self, "test.png")

        self.assertTrue(avatar_tags.has_avatar(self.user))

    def test_avatar_tag_works_with_username(self):
        upload_helper(self, "test.png")
        avatar = get_primary_avatar(self.user)

        result = avatar_tags.avatar(self.user.username)

        self.assertIn('<img src="{}"'.format(avatar.avatar_url(80)), result)
        self.assertIn('width="80" height="80" alt="User Avatar" />', result)

    @override_settings(AVATAR_EXPOSE_USERNAMES=True)
    def test_avatar_tag_works_with_exposed_username(self):
        upload_helper(self, "test.png")
        avatar = get_primary_avatar(self.user)

        result = avatar_tags.avatar(self.user.username)

        self.assertIn('<img src="{}"'.format(avatar.avatar_url(80)), result)
        self.assertIn('width="80" height="80" alt="test" />', result)

    def test_avatar_tag_works_with_user(self):
        upload_helper(self, "test.png")
        avatar = get_primary_avatar(self.user)

        result = avatar_tags.avatar(self.user)

        self.assertIn('<img src="{}"'.format(avatar.avatar_url(80)), result)
        self.assertIn('width="80" height="80" alt="User Avatar" />', result)

    def test_avatar_tag_works_with_custom_size(self):
        upload_helper(self, "test.png")
        avatar = get_primary_avatar(self.user)

        result = avatar_tags.avatar(self.user, 100)

        self.assertIn('<img src="{}"'.format(avatar.avatar_url(100)), result)
        self.assertIn('width="100" height="100" alt="User Avatar" />', result)

    def test_avatar_tag_works_with_rectangle(self):
        upload_helper(self, "test.png")
        avatar = get_primary_avatar(self.user)

        result = avatar_tags.avatar(self.user, 100, 150)

        self.assertIn('<img src="{}"'.format(avatar.avatar_url(100, 150)), result)
        self.assertIn('width="100" height="150" alt="User Avatar" />', result)

    def test_avatar_tag_works_with_kwargs(self):
        upload_helper(self, "test.png")
        avatar = get_primary_avatar(self.user)

        result = avatar_tags.avatar(self.user, title="Avatar")
        html = '<img src="{}" width="80" height="80" alt="User Avatar" title="Avatar" />'.format(
            avatar.avatar_url(80)
        )
        self.assertInHTML(html, result)

    def test_primary_avatar_tag_works(self):
        upload_helper(self, "test.png")

        result = avatar_tags.primary_avatar(self.user)

        self.assertIn(f'<img src="/avatar/render_primary/{self.user.id}/80/"', result)
        self.assertIn('width="80" height="80" alt="User Avatar" />', result)

        response = self.client.get(f"/avatar/render_primary/{self.user.id}/80/")
        self.assertEqual(response.status_code, 302)
        self.assertMediaFileExists(response.url)

    def test_primary_avatar_tag_works_with_custom_size(self):
        upload_helper(self, "test.png")

        result = avatar_tags.primary_avatar(self.user, 90)

        self.assertIn(f'<img src="/avatar/render_primary/{self.user.id}/90/"', result)
        self.assertIn('width="90" height="90" alt="User Avatar" />', result)

        response = self.client.get(f"/avatar/render_primary/{self.user.id}/90/")
        self.assertEqual(response.status_code, 302)
        self.assertMediaFileExists(response.url)

    def test_primary_avatar_tag_works_with_rectangle(self):
        upload_helper(self, "test.png")

        result = avatar_tags.primary_avatar(self.user, 60, 110)

        self.assertIn(
            f'<img src="/avatar/render_primary/{self.user.id}/60/110/"', result
        )
        self.assertIn('width="60" height="110" alt="User Avatar" />', result)

        response = self.client.get(f"/avatar/render_primary/{self.user.id}/60/110/")
        self.assertEqual(response.status_code, 302)
        self.assertMediaFileExists(response.url)

    @override_settings(AVATAR_EXPOSE_USERNAMES=True)
    def test_primary_avatar_tag_works_with_exposed_user(self):
        upload_helper(self, "test.png")

        result = avatar_tags.primary_avatar(self.user)

        self.assertIn(
            f'<img src="/avatar/render_primary/{self.user.username}/80/"', result
        )
        self.assertIn('width="80" height="80" alt="test" />', result)

        response = self.client.get(f"/avatar/render_primary/{self.user.username}/80/")
        self.assertEqual(response.status_code, 302)
        self.assertMediaFileExists(response.url)

    def test_default_add_template(self):
        response = self.client.get("/avatar/add/")
        self.assertContains(response, "Upload New Image")
        self.assertNotContains(response, "ALTERNATE ADD TEMPLATE")

    @override_settings(AVATAR_ADD_TEMPLATE="alt/add.html")
    def test_custom_add_template(self):
        response = self.client.get("/avatar/add/")
        self.assertNotContains(response, "Upload New Image")
        self.assertContains(response, "ALTERNATE ADD TEMPLATE")

    def test_default_change_template(self):
        response = self.client.get("/avatar/change/")
        self.assertContains(response, "Upload New Image")
        self.assertNotContains(response, "ALTERNATE CHANGE TEMPLATE")

    @override_settings(AVATAR_CHANGE_TEMPLATE="alt/change.html")
    def test_custom_change_template(self):
        response = self.client.get("/avatar/change/")
        self.assertNotContains(response, "Upload New Image")
        self.assertContains(response, "ALTERNATE CHANGE TEMPLATE")

    def test_default_delete_template(self):
        upload_helper(self, "test.png")
        response = self.client.get("/avatar/delete/")
        self.assertContains(response, "like to delete.")
        self.assertNotContains(response, "ALTERNATE DELETE TEMPLATE")

    @override_settings(AVATAR_DELETE_TEMPLATE="alt/delete.html")
    def test_custom_delete_template(self):
        response = self.client.get("/avatar/delete/")
        self.assertNotContains(response, "like to delete.")
        self.assertContains(response, "ALTERNATE DELETE TEMPLATE")

    def get_media_file_mtime(self, path):
        full_path = os.path.join(self.testmediapath, f".{path}")
        return os.path.getmtime(full_path)

    def test_rebuild_avatars(self):
        upload_helper(self, "test.png")
        avatar_51_url = get_primary_avatar(self.user).avatar_url(51)
        self.assertMediaFileExists(avatar_51_url)
        avatar_51_mtime = self.get_media_file_mtime(avatar_51_url)

        avatar_62_url = get_primary_avatar(self.user).avatar_url(62)
        self.assertMediaFileExists(avatar_62_url)
        avatar_62_mtime = self.get_media_file_mtime(avatar_62_url)

        avatar_33_22_url = get_primary_avatar(self.user).avatar_url(33, 22)
        self.assertMediaFileExists(avatar_33_22_url)
        avatar_33_22_mtime = self.get_media_file_mtime(avatar_33_22_url)

        avatar_80_url = get_primary_avatar(self.user).avatar_url(80)
        self.assertMediaFileExists(avatar_80_url)
        avatar_80_mtime = self.get_media_file_mtime(avatar_80_url)
        # Rebuild all avatars
        management.call_command("rebuild_avatars", verbosity=0)
        # Make sure the media files all exist, but that their modification times differ
        self.assertMediaFileExists(avatar_51_url)
        self.assertNotEqual(avatar_51_mtime, self.get_media_file_mtime(avatar_51_url))
        self.assertMediaFileExists(avatar_62_url)
        self.assertNotEqual(avatar_62_mtime, self.get_media_file_mtime(avatar_62_url))
        self.assertMediaFileExists(avatar_33_22_url)
        self.assertNotEqual(
            avatar_33_22_mtime, self.get_media_file_mtime(avatar_33_22_url)
        )
        self.assertMediaFileExists(avatar_80_url)
        self.assertNotEqual(avatar_80_mtime, self.get_media_file_mtime(avatar_80_url))

    def test_invalidate_cache(self):
        upload_helper(self, "test.png")
        sizes_key = get_cache_key(self.user, "cached_sizes")
        sizes = cache.get(sizes_key, set())
        # Only default 80x80 thumbnail is cached
        self.assertEqual(len(sizes), 1)
        # Invalidate cache
        invalidate_cache(self.user)
        sizes = cache.get(sizes_key, set())
        # No thumbnail is cached.
        self.assertEqual(len(sizes), 0)
        # Create a custom 25x25 thumbnail and check that it is cached
        avatar_tags.avatar(self.user, 25)
        sizes = cache.get(sizes_key, set())
        self.assertEqual(len(sizes), 1)
        # Invalidate cache again.
        invalidate_cache(self.user)
        sizes = cache.get(sizes_key, set())
        # It should now be empty again
        self.assertEqual(len(sizes), 0)


class UserWithAvatarsSerializer(drf_serializers.ModelSerializer):
    avatars = AvatarListField(width=100, height=50)
    avatar_url = AvatarUrlField(width=100, height=50)

    class Meta:
        model = get_user_model()
        fields = ("username", "avatars", "avatar_url")


class ObjectAvatarMixin:
    """Shared setup for avatars attached to non-user model instances."""

    @classmethod
    def setUpClass(cls):
        cls.path = os.path.dirname(__file__)
        cls.testdatapath = os.path.join(cls.path, "data")
        cls.testmediapath = os.path.join(cls.path, "../test-media/")
        return super().setUpClass()

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            "test", "lennon@thebeatles.com", "testpassword"
        )
        self.staff_user = get_user_model().objects.create_user(
            "stafftest", "staff@example.com", "staffpassword", is_staff=True
        )
        self.client.login(username="test", password="testpassword")
        self.site = Site.objects.get_current()
        Image.init()

    def tearDown(self):
        if os.path.exists(self.testmediapath):
            rmtree(self.testmediapath)
        return super().tearDown()

    def create_object_avatar(self, obj, filename="test.png", primary=True):
        avatar = Avatar(primary=primary)
        avatar.set_owner(obj)
        with open(os.path.join(self.testdatapath, filename), "rb") as f:
            avatar.avatar.save(filename, File(f))
        avatar.save()
        return avatar


class GenericObjectAvatarTests(ObjectAvatarMixin, TestCase):
    def test_avatar_can_be_attached_to_another_model(self):
        avatar = self.create_object_avatar(self.site)
        self.assertIsNone(avatar.user)
        self.assertEqual(avatar.owner, self.site)
        stored = Avatar.objects.get(pk=avatar.pk)
        self.assertEqual(stored.content_object, self.site)
        self.assertEqual(stored.owner, self.site)
        self.assertEqual(get_primary_avatar(self.site), avatar)

    def test_avatar_requires_an_owner(self):
        avatar = Avatar(primary=True)
        with self.assertRaises(ValidationError):
            avatar.save()

    def test_avatar_cannot_have_two_owners(self):
        avatar = Avatar(primary=True, user=self.user)
        avatar.content_type = ContentType.objects.get_for_model(Site)
        avatar.object_id = str(self.site.pk)
        with self.assertRaises(ValidationError):
            avatar.full_clean()

    def test_set_owner_on_user_clears_object_fields(self):
        avatar = Avatar(primary=True)
        avatar.set_owner(self.site)
        avatar.set_owner(self.user)
        self.assertEqual(avatar.user, self.user)
        self.assertIsNone(avatar.content_type)
        self.assertIsNone(avatar.object_id)

    def test_one_primary_avatar_per_object(self):
        first = self.create_object_avatar(self.site, filename="test.png")
        second = self.create_object_avatar(self.site, filename="django.png")
        self.assertEqual(get_avatars(self.site).filter(primary=True).count(), 1)
        self.assertEqual(get_primary_avatar(self.site), second)
        self.assertFalse(Avatar.objects.get(pk=first.pk).primary)

    def test_object_avatar_paths_do_not_collide_with_user_paths(self):
        user_avatar = self.create_object_avatar(self.user, filename="test.png")
        site_avatar = self.create_object_avatar(self.site, filename="test.png")
        self.assertNotEqual(user_avatar.avatar.name, site_avatar.avatar.name)
        self.assertTrue(
            user_avatar.avatar.name.startswith("avatars/%s/" % self.user.pk)
        )
        self.assertIn("sites_site-%s" % self.site.pk, site_avatar.avatar.name)

    def test_object_add_view_requires_permission(self):
        url = reverse(
            "avatar:add_object",
            kwargs={
                "app_label": "sites",
                "model_name": "site",
                "object_pk": self.site.pk,
            },
        )
        with open(os.path.join(self.testdatapath, "test.png"), "rb") as f:
            response = self.client.post(url, {"avatar": f})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(get_avatars(self.site).count(), 0)

    def test_object_add_view_staff_upload(self):
        self.client.login(username="stafftest", password="staffpassword")
        url = reverse(
            "avatar:add_object",
            kwargs={
                "app_label": "sites",
                "model_name": "site",
                "object_pk": self.site.pk,
            },
        )
        with open(os.path.join(self.testdatapath, "test.png"), "rb") as f:
            response = self.client.post(url, {"avatar": f})
        self.assertEqual(response.status_code, 302)
        avatars = get_avatars(self.site)
        self.assertEqual(avatars.count(), 1)
        self.assertTrue(avatars[0].primary)
        self.assertIsNone(avatars[0].user)

    def test_object_change_and_delete_views(self):
        self.client.login(username="stafftest", password="staffpassword")
        first = self.create_object_avatar(self.site, filename="test.png")
        second = self.create_object_avatar(
            self.site, filename="django.png", primary=False
        )
        kwargs = {
            "app_label": "sites",
            "model_name": "site",
            "object_pk": self.site.pk,
        }
        response = self.client.post(
            reverse("avatar:change_object", kwargs=kwargs),
            {"choice": second.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Avatar.objects.get(pk=second.pk).primary)
        self.assertFalse(Avatar.objects.get(pk=first.pk).primary)

        response = self.client.post(
            reverse("avatar:delete_object", kwargs=kwargs),
            {"choices": [second.pk]},
        )
        self.assertEqual(response.status_code, 302)
        remaining = get_avatars(self.site)
        self.assertEqual(remaining.count(), 1)
        self.assertEqual(remaining[0].pk, first.pk)

    def test_unknown_model_object_view_404(self):
        self.client.login(username="stafftest", password="staffpassword")
        url = reverse(
            "avatar:add_object",
            kwargs={
                "app_label": "nosuchapp",
                "model_name": "nosuchmodel",
                "object_pk": "1",
            },
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_avatar_tag_renders_object_avatar(self):
        avatar = self.create_object_avatar(self.site)
        result = avatar_tags.avatar(self.site, 80)
        self.assertIn('<img src="%s"' % avatar.avatar_url(80), result)
        self.assertIn('width="80" height="80" alt="Avatar" />', result)

    def test_primary_avatar_tag_for_object(self):
        avatar = self.create_object_avatar(self.site)
        result = avatar_tags.primary_avatar(self.site)
        self.assertIn('<img src="%s"' % avatar.avatar_url(80), result)

    def test_has_avatar_for_object(self):
        self.assertFalse(avatar_tags.has_avatar(self.site))
        self.create_object_avatar(self.site)
        self.assertTrue(avatar_tags.has_avatar(self.site))

    def test_admin_owner_column(self):
        avatar = self.create_object_avatar(self.site)
        aa = AvatarAdmin(Avatar, AdminSite())
        self.assertEqual(aa.owner(avatar), str(self.site))


class LinkAvatarProviderTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = Site.objects.get_current()

    def test_link_provider_returns_stored_link(self):
        self.site.name = "https://example.com/logo.png"
        with override_settings(AVATAR_LINK_FIELD="name"):
            url = LinkAvatarProvider.get_avatar_url(self.site, 80)
        self.assertEqual(url, "https://example.com/logo.png")

    def test_link_provider_none_without_field(self):
        self.site.name = "https://example.com/logo.png"
        self.assertIsNone(LinkAvatarProvider.get_avatar_url(self.site, 80))

    def test_stored_link_for_user(self):
        user = get_user_model().objects.create_user(
            "linkuser", "link@example.com", "password"
        )
        user.first_name = " https://example.com/profile.png "
        with override_settings(AVATAR_LINK_FIELD="first_name"):
            url = LinkAvatarProvider.get_avatar_url(user, 80)
        self.assertEqual(url, "https://example.com/profile.png")

    def test_avatar_tag_uses_stored_link(self):
        self.site.name = "https://example.com/logo.png"
        with override_settings(AVATAR_LINK_FIELD="name"):
            result = avatar_tags.avatar(self.site, 80)
        self.assertIn('<img src="https://example.com/logo.png"', result)

    def test_uploaded_avatar_takes_precedence_over_link(self):
        avatar = Avatar(primary=True)
        avatar.set_owner(self.site)
        with open(
            os.path.join(os.path.dirname(__file__), "data", "test.png"), "rb"
        ) as f:
            avatar.avatar.save("test.png", File(f))
        avatar.save()
        try:
            self.site.name = "https://example.com/logo.png"
            with override_settings(AVATAR_LINK_FIELD="name"):
                url = avatar_tags.avatar_url(self.site, 80)
            self.assertEqual(url, avatar.avatar_url(80))
        finally:
            avatar.delete()

    def test_gravatar_and_libravatar_return_none_without_email_field(self):
        self.assertIsNone(GravatarAvatarProvider.get_avatar_url(self.site, 80))
        self.assertIsNone(LibRAvatarProvider.get_avatar_url(self.site, 80))


class AvatarSerializationTests(ObjectAvatarMixin, TestCase):
    def test_avatars_serialized_along_with_user(self):
        avatar = self.create_object_avatar(self.user, filename="test.png")
        data = UserWithAvatarsSerializer(self.user).data
        self.assertEqual(len(data["avatars"]), 1)
        entry = data["avatars"][0]
        self.assertEqual(entry["id"], avatar.pk)
        self.assertTrue(entry["primary"])
        self.assertEqual(entry["url"], avatar.avatar_url(100, 50))
        self.assertTrue(entry["date_uploaded"])
        self.assertEqual(data["avatar_url"], avatar.avatar_url(100, 50))

    def test_multiple_avatars_keep_primary_first(self):
        self.create_object_avatar(self.user, filename="django.png", primary=False)
        primary = self.create_object_avatar(self.user, filename="test.png")
        data = UserWithAvatarsSerializer(self.user).data
        self.assertEqual(len(data["avatars"]), 2)
        self.assertEqual(data["avatars"][0]["id"], primary.pk)
        self.assertTrue(data["avatars"][0]["primary"])
        self.assertFalse(data["avatars"][1]["primary"])

    def test_serializer_without_avatars(self):
        data = UserWithAvatarsSerializer(self.user).data
        self.assertEqual(data["avatars"], [])
        self.assertEqual(data["avatar_url"], get_default_avatar_url())

    def test_avatars_serialized_along_with_other_model(self):
        class SiteSerializer(drf_serializers.ModelSerializer):
            avatars = AvatarListField()

            class Meta:
                model = Site
                fields = ("domain", "avatars")

        avatar = self.create_object_avatar(self.site)
        data = SiteSerializer(self.site).data
        self.assertEqual(len(data["avatars"]), 1)
        self.assertEqual(data["avatars"][0]["id"], avatar.pk)

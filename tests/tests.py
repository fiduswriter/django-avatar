import math
import os.path
import sys
from pathlib import Path
from shutil import rmtree
from unittest import skipIf

from django.contrib.admin.sites import AdminSite
from django.core import management
from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from PIL import Image, ImageChops

from avatar.admin import AvatarAdmin
from avatar.conf import settings
from avatar.models import Avatar
from avatar.signals import avatar_deleted
from avatar.templatetags import avatar_tags
from avatar.utils import (
    get_cache_key,
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
        avatars = Avatar.objects.filter(user=self.user)
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

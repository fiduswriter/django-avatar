from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.module_loading import import_string
from django.utils.translation import gettext as _

from avatar.conf import settings
from avatar.forms import DeleteAvatarForm, PrimaryAvatarForm, UploadAvatarForm
from avatar.models import Avatar
from avatar.signals import avatar_deleted, avatar_updated
from avatar.utils import (
    get_avatars,
    get_default_avatar_url,
    get_primary_avatar,
    invalidate_cache,
)


def get_object_permission():
    """
    The callable that decides whether a request may manage the avatars of a
    model instance other than the requesting user. Configured via
    ``settings.AVATAR_OBJECT_PERMISSION``.
    """
    return import_string(settings.AVATAR_OBJECT_PERMISSION)


def default_object_permission(request, obj):
    """
    Default permission for the avatar views of objects other than the
    requesting user: only staff members may change their avatars.
    """
    return request.user.is_staff


def _get_next(request):
    """
    The part that's the least straightforward about views in this module is
    how they determine their redirects after they have finished computation.

    In short, they will try and determine the next place to go in the
    following order:

    1. If there is a variable named ``next`` in the *POST* parameters, the
       view will redirect to that variable's value.
    2. If there is a variable named ``next`` in the *GET* parameters, the
       view will redirect to that variable's value.
    3. If Django can determine the previous page from the HTTP headers, the
       view will redirect to that previous page.
    """
    next = request.POST.get(
        "next", request.GET.get("next", request.META.get("HTTP_REFERER", None))
    )
    if not next:
        next = request.path
    return next


def _resolve_object(request, app_label, model_name, object_pk):
    """
    Resolve the model instance whose avatars are managed, defaulting to the
    requesting user.
    """
    if app_label is None:
        return request.user
    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        raise Http404("Unknown model %s.%s" % (app_label, model_name))
    obj = get_object_or_404(model, pk=object_pk)
    if not get_object_permission()(request, obj):
        raise PermissionDenied
    return obj


def _avatar_urls(app_label, model_name, object_pk):
    """
    URLs for the add, change and delete views of the same avatar owner, to be
    used by the templates.
    """
    if app_label is not None:
        kwargs = {
            "app_label": app_label,
            "model_name": model_name,
            "object_pk": object_pk,
        }
        return {
            "%s_url" % name: reverse("avatar:%s_object" % name, kwargs=kwargs)
            for name in ("add", "change", "delete")
        }
    return {
        "%s_url" % name: reverse("avatar:%s" % name)
        for name in ("add", "change", "delete")
    }


def _get_avatars(obj):
    # Default set. Needs to be sliced, but that's it. Keep the natural order.
    avatars = get_avatars(obj)

    # Current avatar
    primary_avatar = avatars.order_by("-primary")[:1]
    if primary_avatar:
        avatar = primary_avatar[0]
    else:
        avatar = None

    if settings.AVATAR_MAX_AVATARS_PER_USER == 1:
        avatars = primary_avatar
    else:
        # Slice the default set now that we used
        # the queryset for the primary avatar
        avatars = avatars[: settings.AVATAR_MAX_AVATARS_PER_USER]
    return (avatar, avatars)


@login_required
def add(
    request,
    extra_context=None,
    next_override=None,
    upload_form=UploadAvatarForm,
    app_label=None,
    model_name=None,
    object_pk=None,
    *args,
    **kwargs,
):
    if extra_context is None:
        extra_context = {}
    obj = _resolve_object(request, app_label, model_name, object_pk)
    avatar, avatars = _get_avatars(obj)
    upload_avatar_form = upload_form(
        request.POST or None, request.FILES or None, obj=obj
    )
    if request.method == "POST" and "avatar" in request.FILES:
        if upload_avatar_form.is_valid():
            avatar = Avatar(primary=True)
            avatar.set_owner(obj)
            image_file = request.FILES["avatar"]
            avatar.avatar.save(image_file.name, image_file)
            avatar.save()
            messages.success(request, _("Successfully uploaded a new avatar."))
            avatar_updated.send(sender=Avatar, user=request.user, avatar=avatar)
            return redirect(next_override or _get_next(request))
    context = {
        "avatar": avatar,
        "avatars": avatars,
        "upload_avatar_form": upload_avatar_form,
        "next": next_override or _get_next(request),
    }
    context.update(extra_context)
    context.update(_avatar_urls(app_label, model_name, object_pk))
    template_name = settings.AVATAR_ADD_TEMPLATE or "avatar/add.html"
    return render(request, template_name, context)


@login_required
def change(
    request,
    extra_context=None,
    next_override=None,
    upload_form=UploadAvatarForm,
    primary_form=PrimaryAvatarForm,
    app_label=None,
    model_name=None,
    object_pk=None,
    *args,
    **kwargs,
):
    if extra_context is None:
        extra_context = {}
    obj = _resolve_object(request, app_label, model_name, object_pk)
    avatar, avatars = _get_avatars(obj)
    if avatar:
        kwargs = {"initial": {"choice": avatar.id}}
    else:
        kwargs = {}
    upload_avatar_form = upload_form(obj=obj, **kwargs)
    primary_avatar_form = primary_form(
        request.POST or None, obj=obj, avatars=avatars, **kwargs
    )
    if request.method == "POST":
        updated = False
        if "choice" in request.POST and primary_avatar_form.is_valid():
            avatar = Avatar.objects.get(id=primary_avatar_form.cleaned_data["choice"])
            avatar.primary = True
            avatar.save()
            updated = True
            invalidate_cache(obj)
            messages.success(request, _("Successfully updated your avatar."))
        if updated:
            avatar_updated.send(sender=Avatar, user=request.user, avatar=avatar)
        return redirect(next_override or _get_next(request))

    context = {
        "avatar": avatar,
        "avatars": avatars,
        "upload_avatar_form": upload_avatar_form,
        "primary_avatar_form": primary_avatar_form,
        "next": next_override or _get_next(request),
    }
    context.update(extra_context)
    context.update(_avatar_urls(app_label, model_name, object_pk))
    template_name = settings.AVATAR_CHANGE_TEMPLATE or "avatar/change.html"
    return render(request, template_name, context)


@login_required
def delete(
    request,
    extra_context=None,
    next_override=None,
    app_label=None,
    model_name=None,
    object_pk=None,
    *args,
    **kwargs,
):
    if extra_context is None:
        extra_context = {}
    obj = _resolve_object(request, app_label, model_name, object_pk)
    avatar, avatars = _get_avatars(obj)
    delete_avatar_form = DeleteAvatarForm(
        request.POST or None, obj=obj, avatars=avatars
    )
    if request.method == "POST":
        if delete_avatar_form.is_valid():
            ids = delete_avatar_form.cleaned_data["choices"]
            for a in avatars:
                if str(a.id) in ids:
                    avatar_deleted.send(sender=Avatar, user=request.user, avatar=a)
            if str(avatar.id) in ids and avatars.count() > len(ids):
                # Find the next best avatar, and set it as the new primary
                for a in avatars:
                    if str(a.id) not in ids:
                        a.primary = True
                        a.save()
                        avatar_updated.send(
                            sender=Avatar, user=request.user, avatar=avatar
                        )
                        break
            Avatar.objects.filter(id__in=ids).delete()
            messages.success(request, _("Successfully deleted the requested avatars."))
            return redirect(next_override or _get_next(request))

    context = {
        "avatar": avatar,
        "avatars": avatars,
        "delete_avatar_form": delete_avatar_form,
        "next": next_override or _get_next(request),
    }
    context.update(extra_context)
    context.update(_avatar_urls(app_label, model_name, object_pk))
    template_name = settings.AVATAR_DELETE_TEMPLATE or "avatar/confirm_delete.html"
    return render(request, template_name, context)


def render_primary(request, user=None, width=settings.AVATAR_DEFAULT_SIZE, height=None):
    if height is None:
        height = width
    width = int(width)
    height = int(height)
    avatar = get_primary_avatar(user, width=width, height=height)
    if width == 0 and height == 0:
        avatar = get_primary_avatar(
            user,
            width=settings.AVATAR_DEFAULT_SIZE,
            height=settings.AVATAR_DEFAULT_SIZE,
        )
    else:
        avatar = get_primary_avatar(user, width=width, height=height)
    if avatar:
        # FIXME: later, add an option to render the resized avatar dynamically
        # instead of redirecting to an already created static file. This could
        # be useful in certain situations, particulary if there is a CDN and
        # we want to minimize the storage usage on our static server, letting
        # the CDN store those files instead
        url = avatar.avatar_url(width, height)
    else:
        url = get_default_avatar_url()

    return redirect(url)

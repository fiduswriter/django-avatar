from django.urls import path

from avatar import views

# For reversing namespaced urls
# https://docs.djangoproject.com/en/4.1/topics/http/urls/#reversing-namespaced-urls
app_name = "avatar"

# Model instances other than users are addressed via their app label, model
# name and primary key, e.g. "myapp/company/42".
_OBJECT = "object/<slug:app_label>/<slug:model_name>/<str:object_pk>"

urlpatterns = [
    path("add/", views.add, name="add"),
    path("change/", views.change, name="change"),
    path("delete/", views.delete, name="delete"),
    path(f"{_OBJECT}/add/", views.add, name="add_object"),
    path(f"{_OBJECT}/change/", views.change, name="change_object"),
    path(f"{_OBJECT}/delete/", views.delete, name="delete_object"),
    # https://docs.djangoproject.com/en/4.1/topics/http/urls/#path-converters
    path(
        "render_primary/<slug:user>/<int:width>/",
        views.render_primary,
        name="render_primary",
    ),
    path(
        "render_primary/<slug:user>/<int:width>/<int:height>/",
        views.render_primary,
        name="render_primary",
    ),
]

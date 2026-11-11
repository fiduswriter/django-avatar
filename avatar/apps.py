from django.apps import AppConfig


class Config(AppConfig):
    name = "avatar"
    default_auto_field = "django.db.models.AutoField"
    dependencies = ["django.contrib.contenttypes"]

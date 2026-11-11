import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "__latest__"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("avatar", "0003_auto_20170827_1345"),
    ]

    operations = [
        migrations.AddField(
            model_name="avatar",
            name="content_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="contenttypes.contenttype",
                verbose_name="content type",
            ),
        ),
        migrations.AddField(
            model_name="avatar",
            name="object_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=255,
                null=True,
                verbose_name="object id",
            ),
        ),
        migrations.AlterField(
            model_name="avatar",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to=settings.AUTH_USER_MODEL,
                verbose_name="user",
            ),
        ),
    ]

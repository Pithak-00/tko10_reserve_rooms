from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0004_room_google_calendar_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="rakumo_event_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Rakumo イベントID",
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0003_reservation_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="room",
            name="google_calendar_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="例: xxxxx@resource.calendar.google.com",
                max_length=255,
                verbose_name="Google カレンダーID（Rakumo会議室）",
            ),
        ),
    ]

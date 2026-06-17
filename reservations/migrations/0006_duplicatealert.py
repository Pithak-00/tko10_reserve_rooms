from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0005_reservation_rakumo_event_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="DuplicateAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_resolved", models.BooleanField(default=False, verbose_name="解消済み")),
                ("detected_at", models.DateTimeField(auto_now_add=True, verbose_name="検知日時")),
                ("resolved_at", models.DateTimeField(blank=True, null=True, verbose_name="解消日時")),
                ("room", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="duplicate_alerts",
                    to="reservations.room",
                    verbose_name="会議室",
                )),
                ("reservation_a", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="alert_as",
                    to="reservations.reservation",
                    verbose_name="予約A",
                )),
                ("reservation_b", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="alert_bs",
                    to="reservations.reservation",
                    verbose_name="予約B",
                )),
            ],
            options={
                "verbose_name": "重複アラート",
                "verbose_name_plural": "重複アラート",
                "db_table": "duplicate_alerts",
                "ordering": ["-detected_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="duplicatealert",
            constraint=models.UniqueConstraint(
                fields=["reservation_a", "reservation_b"],
                name="unique_duplicate_pair",
            ),
        ),
    ]

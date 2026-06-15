from django.db import migrations, models


def backfill_is_rakumo_source(apps, schema_editor):
    """既存の同期済み予約（notes='※ Rakumoから自動同期'）にフラグを付ける"""
    Reservation = apps.get_model('reservations', 'Reservation')
    Reservation.objects.filter(
        notes='※ Rakumoから自動同期'
    ).update(is_rakumo_source=True)


class Migration(migrations.Migration):

    dependencies = [
        ('reservations', '0006_duplicatealert'),
    ]

    operations = [
        migrations.AddField(
            model_name='reservation',
            name='is_rakumo_source',
            field=models.BooleanField(
                default=False,
                verbose_name='Rakumo発信予約',
                help_text='Rakumo（本社Google Calendar）から同期された予約の場合 True。管理者でもキャンセル不可。',
            ),
        ),
        migrations.RunPython(backfill_is_rakumo_source, migrations.RunPython.noop),
    ]

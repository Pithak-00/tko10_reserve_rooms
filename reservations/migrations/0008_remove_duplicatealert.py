from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reservations', '0007_reservation_is_rakumo_source'),
    ]

    operations = [
        migrations.DeleteModel(
            name='DuplicateAlert',
        ),
    ]

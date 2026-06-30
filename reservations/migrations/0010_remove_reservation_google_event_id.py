from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reservations', '0009_alter_building_id_alter_departmentroom_id_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='reservation',
            name='google_event_id',
        ),
    ]

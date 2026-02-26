# InboundRecord에서 단일 image 필드 제거

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0009_migrate_inbound_images'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='inboundrecord',
            name='image',
        ),
    ]

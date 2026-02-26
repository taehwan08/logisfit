# 입고 이미지 모델 생성

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0007_add_image_to_inbound'),
    ]

    operations = [
        migrations.CreateModel(
            name='InboundImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='inbound/%Y/%m/', verbose_name='이미지')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='등록일시')),
                ('inbound_record', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='images',
                    to='inventory.inboundrecord',
                    verbose_name='입고 기록',
                )),
            ],
            options={
                'verbose_name': '입고 이미지',
                'verbose_name_plural': '입고 이미지 목록',
                'db_table': 'inbound_images',
                'ordering': ['created_at'],
            },
        ),
    ]

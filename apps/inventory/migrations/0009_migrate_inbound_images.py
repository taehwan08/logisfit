# 기존 InboundRecord.image → InboundImage 데이터 마이그레이션

from django.db import migrations


def migrate_images_forward(apps, schema_editor):
    """기존 단일 이미지를 InboundImage 모델로 이관한다."""
    InboundRecord = apps.get_model('inventory', 'InboundRecord')
    InboundImage = apps.get_model('inventory', 'InboundImage')

    records_with_images = InboundRecord.objects.exclude(image='').exclude(image__isnull=True)
    images_to_create = []
    for record in records_with_images:
        images_to_create.append(
            InboundImage(
                inbound_record=record,
                image=record.image,
            )
        )

    if images_to_create:
        InboundImage.objects.bulk_create(images_to_create)


def migrate_images_backward(apps, schema_editor):
    """InboundImage에서 첫 번째 이미지를 InboundRecord.image로 복원한다."""
    InboundRecord = apps.get_model('inventory', 'InboundRecord')
    InboundImage = apps.get_model('inventory', 'InboundImage')

    for img in InboundImage.objects.order_by('inbound_record_id', 'created_at'):
        InboundRecord.objects.filter(
            pk=img.inbound_record_id, image=''
        ).update(image=img.image)


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0008_inboundimage'),
    ]

    operations = [
        migrations.RunPython(migrate_images_forward, migrate_images_backward),
    ]

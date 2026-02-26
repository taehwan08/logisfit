# 로케이션 바코드를 대문자로 통일 (3c-5d → 3C-5D)
# 동일 대문자 바코드가 이미 존재하면 해당 로케이션으로 레코드를 병합한다.

from django.db import migrations


def uppercase_barcodes(apps, schema_editor):
    """기존 로케이션 바코드를 모두 대문자로 변환한다.

    동일 대문자 바코드를 가진 로케이션이 여러 개 있으면,
    첫 번째 것을 남기고 나머지의 재고 기록(InventoryRecord)을
    첫 번째 로케이션으로 옮긴 뒤 중복 로케이션을 삭제한다.
    """
    Location = apps.get_model('inventory', 'Location')
    InventoryRecord = apps.get_model('inventory', 'InventoryRecord')

    # 대문자 변환이 필요한 로케이션을 그룹핑
    from collections import defaultdict
    groups = defaultdict(list)

    for loc in Location.objects.all().order_by('pk'):
        upper_barcode = loc.barcode.upper()
        groups[upper_barcode].append(loc)

    for upper_barcode, locations in groups.items():
        # 대표 로케이션 (가장 먼저 생성된 것)
        primary = locations[0]

        if primary.barcode != upper_barcode:
            primary.barcode = upper_barcode
            primary.save(update_fields=['barcode'])

        # 중복 로케이션 병합
        for dup in locations[1:]:
            # 재고 기록을 대표 로케이션으로 이관
            InventoryRecord.objects.filter(location=dup).update(location=primary)
            # 중복 로케이션 삭제
            dup.delete()


def noop(apps, schema_editor):
    """역방향 마이그레이션은 아무것도 하지 않는다.

    소문자 복원은 원본 데이터가 없으므로 불가.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0010_remove_inboundrecord_image'),
    ]

    operations = [
        migrations.RunPython(uppercase_barcodes, noop),
    ]

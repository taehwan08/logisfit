"""
기존 Product.barcode → ProductBarcode 데이터 마이그레이션

기존 상품의 barcode 값을 ProductBarcode(is_primary=True)로 복사합니다.
Product.barcode 필드 자체는 하위호환을 위해 유지합니다.
중복 바코드(동일 barcode 값이 여러 Product에 존재)는 첫 번째만 primary로 등록하고
나머지는 건너뜁니다(unique 제약 때문).
"""
from django.db import migrations


def forward(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    ProductBarcode = apps.get_model('inventory', 'ProductBarcode')

    seen_barcodes = set()
    to_create = []

    for product in Product.objects.exclude(barcode='').order_by('pk'):
        barcode = product.barcode.strip()
        if not barcode or barcode in seen_barcodes:
            continue
        seen_barcodes.add(barcode)
        to_create.append(
            ProductBarcode(
                product=product,
                barcode=barcode,
                is_primary=True,
            )
        )

    if to_create:
        ProductBarcode.objects.bulk_create(to_create, ignore_conflicts=True)


def backward(apps, schema_editor):
    # ProductBarcode 데이터를 삭제해도 Product.barcode는 그대로 유지됨
    ProductBarcode = apps.get_model('inventory', 'ProductBarcode')
    ProductBarcode.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0015_add_product_extensions'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]

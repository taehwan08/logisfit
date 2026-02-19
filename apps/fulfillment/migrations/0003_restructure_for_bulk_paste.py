# Generated manually for bulk paste restructuring

from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('fulfillment', '0002_fulfillmentcomment'),
        ('clients', '0003_brand_brand_uq_brand_client_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. 새 필드 추가
        migrations.AddField(
            model_name='fulfillmentorder',
            name='brand',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='fulfillment_orders',
                to='clients.brand',
                verbose_name='브랜드',
            ),
        ),
        migrations.AddField(
            model_name='fulfillmentorder',
            name='order_type',
            field=models.CharField(blank=True, max_length=100, verbose_name='발주유형'),
        ),
        migrations.AddField(
            model_name='fulfillmentorder',
            name='order_confirmed',
            field=models.CharField(blank=True, max_length=100, verbose_name='발주확정'),
        ),
        migrations.AddField(
            model_name='fulfillmentorder',
            name='sku_id',
            field=models.CharField(blank=True, max_length=100, verbose_name='SKU ID'),
        ),
        migrations.AddField(
            model_name='fulfillmentorder',
            name='center',
            field=models.CharField(blank=True, max_length=100, verbose_name='센터'),
        ),
        migrations.AddField(
            model_name='fulfillmentorder',
            name='confirmed_quantity',
            field=models.IntegerField(
                default=0,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name='확정수량',
            ),
        ),

        # 2. order_date: DateField → CharField
        #    먼저 기존 인덱스 제거 (order_date 인덱스)
        migrations.RemoveIndex(
            model_name='fulfillmentorder',
            name='idx_fulfill_order_date',
        ),
        #    order_date 필드 변경: DateField(default=timezone.now) → CharField
        migrations.AlterField(
            model_name='fulfillmentorder',
            name='order_date',
            field=models.CharField(blank=True, max_length=50, verbose_name='발주일시'),
        ),

        # 3. receiving_date: DateField(null=True) → CharField
        migrations.AlterField(
            model_name='fulfillmentorder',
            name='receiving_date',
            field=models.CharField(blank=True, max_length=50, default='', verbose_name='입고일'),
            preserve_default=False,
        ),

        # 4. ordering 변경 (Meta)
        migrations.AlterModelOptions(
            name='fulfillmentorder',
            options={
                'ordering': ['-created_at'],
                'verbose_name': '출고 주문',
                'verbose_name_plural': '출고 주문 목록',
            },
        ),
    ]

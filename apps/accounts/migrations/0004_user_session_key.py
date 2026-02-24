from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_passwordresetcode'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='session_key',
            field=models.CharField(
                blank=True,
                max_length=40,
                null=True,
                verbose_name='세션 키',
            ),
        ),
    ]

# Generated manually for password reset code model
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_user_clients'),
    ]

    operations = [
        migrations.CreateModel(
            name='PasswordResetCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=6, verbose_name='인증번호')),
                ('is_used', models.BooleanField(default=False, verbose_name='사용 여부')),
                ('attempt_count', models.IntegerField(default=0, verbose_name='시도 횟수')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='생성일시')),
                ('expires_at', models.DateTimeField(verbose_name='만료일시')),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='password_reset_codes',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='사용자',
                )),
            ],
            options={
                'verbose_name': '비밀번호 리셋 인증번호',
                'verbose_name_plural': '비밀번호 리셋 인증번호',
                'db_table': 'accounts_password_reset_codes',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['user', 'is_used', 'expires_at'], name='idx_reset_code_lookup'),
                ],
            },
        ),
    ]

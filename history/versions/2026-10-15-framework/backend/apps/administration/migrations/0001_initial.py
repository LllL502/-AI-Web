import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('items', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AbuseReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(max_length=80)),
                ('detail', models.CharField(blank=True, max_length=1000)),
                ('status', models.CharField(choices=[('OPEN', '待处理'), ('RESOLVED', '已处理'), ('DISMISSED', '已忽略')], default='OPEN', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='items.item')),
                ('reporter', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reports', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(db_index=True, max_length=80)),
                ('target_type', models.CharField(db_index=True, max_length=100)),
                ('target_id', models.CharField(db_index=True, max_length=64)),
                ('before', models.JSONField(blank=True, default=dict)),
                ('after', models.JSONField(blank=True, default=dict)),
                ('request_id', models.CharField(blank=True, db_index=True, max_length=64)),
                ('ip_digest', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PersistentTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_type', models.CharField(max_length=80)),
                ('status', models.CharField(choices=[('PENDING', '等待'), ('RUNNING', '运行中'), ('SUCCEEDED', '成功'), ('FAILED', '失败')], db_index=True, default='PENDING', max_length=16)),
                ('progress', models.PositiveSmallIntegerField(default=0)),
                ('payload', models.JSONField(default=dict)),
                ('result', models.JSONField(default=dict)),
                ('error_code', models.CharField(blank=True, max_length=80)),
                ('error_message', models.CharField(blank=True, max_length=1000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tasks', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]

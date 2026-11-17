import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CampusLocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('code', models.SlugField(max_length=64, unique=True)),
                ('aliases', models.JSONField(blank=True, default=list)),
                ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('public_precision', models.PositiveSmallIntegerField(default=1, help_text='公开位置精度等级')),
                ('is_active', models.BooleanField(default=True)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='stations.campuslocation')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Station',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('code', models.SlugField(max_length=64, unique=True)),
                ('address', models.CharField(max_length=255)),
                ('opening_hours', models.JSONField(default=dict)),
                ('capacity', models.PositiveIntegerField(default=100)),
                ('status', models.CharField(choices=[('OPEN', '开放'), ('BUSY', '繁忙'), ('CLOSED', '暂停服务')], default='OPEN', max_length=16)),
                ('contact_phone', models.CharField(blank=True, max_length=32)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('location', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stations', to='stations.campuslocation')),
            ],
        ),
        migrations.CreateModel(
            name='StationMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('can_review', models.BooleanField(default=True)),
                ('can_handover', models.BooleanField(default=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('station', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='stations.station')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='station_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('user', 'station'), name='uq_station_membership_user_station')],
            },
        ),
    ]

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('items', '0001_initial'),
        ('stations', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Claim',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('statement', models.TextField(max_length=3000)),
                ('evidence', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('DRAFT', '草稿'), ('SUBMITTED', '已提交'), ('NEEDS_INFO', '待补充'), ('APPROVED', '已批准'), ('HANDOVER_PENDING', '待交接'), ('COMPLETED', '已完成'), ('REJECTED', '已驳回'), ('CANCELLED', '已取消')], db_index=True, default='DRAFT', max_length=24)),
                ('decision_note', models.CharField(blank=True, max_length=1000)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('claimant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='claims', to=settings.AUTH_USER_MODEL)),
                ('found_item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='claims', to='items.item')),
                ('related_lost_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='supporting_claims', to='items.item')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reviewed_claims', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='ActiveReservation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('found_item', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='active_reservation', to='items.item')),
                ('claim', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='active_reservation', to='claims.claim')),
            ],
        ),
        migrations.CreateModel(
            name='ClaimEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('from_status', models.CharField(blank=True, max_length=24)),
                ('to_status', models.CharField(max_length=24)),
                ('note', models.CharField(blank=True, max_length=1000)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='claim_events', to=settings.AUTH_USER_MODEL)),
                ('claim', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='claims.claim')),
            ],
            options={
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='HandoverAppointment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scheduled_at', models.DateTimeField()),
                ('code_digest', models.CharField(max_length=128)),
                ('code_expires_at', models.DateTimeField()),
                ('failed_attempts', models.PositiveSmallIntegerField(default=0)),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('claimant_confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('staff_confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('claim', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='appointment', to='claims.claim')),
                ('station', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='appointments', to='stations.station')),
            ],
        ),
        migrations.CreateModel(
            name='ReturnRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('receipt_number', models.CharField(max_length=40, unique=True)),
                ('completed_at', models.DateTimeField()),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('claim', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='return_record', to='claims.claim')),
                ('completed_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='completed_returns', to=settings.AUTH_USER_MODEL)),
                ('found_item', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='return_record', to='items.item')),
            ],
        ),
    ]

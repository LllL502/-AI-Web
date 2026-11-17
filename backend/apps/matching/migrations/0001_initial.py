import django.core.validators
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
            name='AlgorithmConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('version', models.CharField(max_length=32, unique=True)),
                ('weights', models.JSONField()),
                ('thresholds', models.JSONField(default=dict)),
                ('preprocessing', models.JSONField(default=dict)),
                ('is_published', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='algorithm_configs', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='IndexVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.CharField(max_length=64, unique=True)),
                ('document_count', models.PositiveIntegerField()),
                ('vocabulary_size', models.PositiveIntegerField()),
                ('artifact_path', models.CharField(max_length=500)),
                ('corpus_checksum', models.CharField(max_length=64)),
                ('is_active', models.BooleanField(db_index=True, default=False)),
                ('built_at', models.DateTimeField(auto_now_add=True)),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='indexes', to='matching.algorithmconfig')),
            ],
        ),
        migrations.CreateModel(
            name='MatchRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('PENDING', '等待'), ('RUNNING', '运行中'), ('COMPLETED', '已完成'), ('FAILED', '失败')], db_index=True, default='PENDING', max_length=16)),
                ('candidate_count', models.PositiveIntegerField(default=0)),
                ('error_code', models.CharField(blank=True, max_length=80)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='runs', to='matching.algorithmconfig')),
                ('index_version', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='runs', to='matching.indexversion')),
                ('query_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='match_runs', to='items.item')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='match_runs', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='MatchCandidate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rank', models.PositiveIntegerField()),
                ('raw_score', models.DecimalField(decimal_places=6, max_digits=7, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(1)])),
                ('coverage', models.DecimalField(decimal_places=6, max_digits=7, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(1)])),
                ('final_score', models.DecimalField(decimal_places=6, max_digits=7, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(1)])),
                ('factors', models.JSONField()),
                ('explanation', models.JSONField(default=dict)),
                ('is_actionable', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('candidate_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='candidate_matches', to='items.item')),
                ('run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='candidates', to='matching.matchrun')),
            ],
            options={
                'ordering': ['run_id', 'rank'],
            },
        ),
        migrations.CreateModel(
            name='MatchFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(choices=[('MATCH', '匹配'), ('NOT_MATCH', '不匹配'), ('UNSURE', '不确定')], max_length=32)),
                ('reason', models.CharField(blank=True, max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('candidate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedback', to='matching.matchcandidate')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='match_feedback', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('candidate', 'user'), name='uq_candidate_feedback_user')],
            },
        ),
        migrations.AddConstraint(
            model_name='matchcandidate',
            constraint=models.UniqueConstraint(fields=('run', 'candidate_item'), name='uq_run_candidate'),
        ),
        migrations.AddConstraint(
            model_name='matchcandidate',
            constraint=models.UniqueConstraint(fields=('run', 'rank'), name='uq_run_rank'),
        ),
    ]

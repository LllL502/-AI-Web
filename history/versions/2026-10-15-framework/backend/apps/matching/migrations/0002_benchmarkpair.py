import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('items', '0001_initial'),
        ('matching', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BenchmarkPair',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_match', models.BooleanField()),
                ('split', models.CharField(choices=[('TRAIN', '训练'), ('VALIDATION', '验证'), ('TEST', '测试')], max_length=16)),
                ('is_synthetic', models.BooleanField(default=True)),
                ('source_note', models.CharField(default='固定规则生成的演示基准', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('found_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='benchmark_found_pairs', to='items.item')),
                ('lost_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='benchmark_lost_pairs', to='items.item')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('lost_item', 'found_item'), name='uq_benchmark_lost_found')],
            },
        ),
    ]

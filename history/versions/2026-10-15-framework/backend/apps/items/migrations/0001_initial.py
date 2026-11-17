import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('stations', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80)),
                ('code', models.SlugField(max_length=64, unique=True)),
                ('synonyms', models.JSONField(blank=True, default=list)),
                ('is_active', models.BooleanField(default=True)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='items.category')),
            ],
        ),
        migrations.CreateModel(
            name='Item',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('LOST', '遗失'), ('FOUND', '招领')], db_index=True, max_length=8)),
                ('title', models.CharField(max_length=120)),
                ('description', models.TextField(max_length=3000)),
                ('brand', models.CharField(blank=True, max_length=80)),
                ('color', models.CharField(blank=True, max_length=80)),
                ('occurred_at', models.DateTimeField(db_index=True)),
                ('location_detail', models.CharField(blank=True, max_length=255)),
                ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('review_status', models.CharField(choices=[('DRAFT', '草稿'), ('PENDING', '待审核'), ('APPROVED', '已通过'), ('REJECTED', '已驳回')], db_index=True, default='DRAFT', max_length=16)),
                ('business_status', models.CharField(choices=[('OPEN', '寻找中'), ('RESERVED', '认领保留中'), ('RETURNED', '已归还'), ('CLOSED', '已关闭'), ('EXPIRED', '已过期')], db_index=True, default='OPEN', max_length=16)),
                ('review_note', models.CharField(blank=True, max_length=500)),
                ('published_revision', models.PositiveIntegerField(blank=True, null=True)),
                ('is_demo', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='items', to='items.category')),
                ('location', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='items', to='stations.campuslocation')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='items', to=settings.AUTH_USER_MODEL)),
                ('station', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='items', to='stations.station')),
            ],
        ),
        migrations.CreateModel(
            name='Favorite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='favorites', to=settings.AUTH_USER_MODEL)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='favorited_by', to='items.item')),
            ],
        ),
        migrations.CreateModel(
            name='ItemRevision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('revision', models.PositiveIntegerField()),
                ('snapshot', models.JSONField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='item_revisions', to=settings.AUTH_USER_MODEL)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='revisions', to='items.item')),
            ],
            options={
                'ordering': ['item_id', 'revision'],
            },
        ),
        migrations.CreateModel(
            name='MediaAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.ImageField(upload_to='items/%Y/%m/%d/')),
                ('thumbnail', models.ImageField(blank=True, upload_to='items/thumbs/%Y/%m/%d/')),
                ('sha256', models.CharField(db_index=True, max_length=64)),
                ('width', models.PositiveIntegerField(blank=True, null=True)),
                ('height', models.PositiveIntegerField(blank=True, null=True)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('is_public', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='media', to='items.item')),
            ],
        ),
        migrations.CreateModel(
            name='PrivateClue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prompt', models.CharField(max_length=255)),
                ('answer_digest', models.CharField(max_length=128)),
                ('answer_hint', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='private_clues', to='items.item')),
            ],
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('criteria', models.JSONField(default=dict)),
                ('minimum_score', models.DecimalField(decimal_places=4, default=0.65, max_digits=5, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(1)])),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscriptions', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['kind', 'review_status', 'business_status', '-occurred_at'], name='item_public_feed_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['owner', '-created_at'], name='item_owner_created_idx'),
        ),
        migrations.AddConstraint(
            model_name='favorite',
            constraint=models.UniqueConstraint(fields=('user', 'item'), name='uq_favorite_user_item'),
        ),
        migrations.AddConstraint(
            model_name='itemrevision',
            constraint=models.UniqueConstraint(fields=('item', 'revision'), name='uq_item_revision_number'),
        ),
    ]

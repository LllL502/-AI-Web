import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("items", "0002_item_coordinate_system"),
        ("stations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ItemLocationCandidate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "rank",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(5),
                        ]
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="location_candidates",
                        to="items.item",
                    ),
                ),
                (
                    "location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="item_location_candidates",
                        to="stations.campuslocation",
                    ),
                ),
            ],
            options={"ordering": ["rank", "id"]},
        ),
        migrations.AddConstraint(
            model_name="itemlocationcandidate",
            constraint=models.UniqueConstraint(
                fields=("item", "location"), name="uq_item_location_candidate"
            ),
        ),
        migrations.AddConstraint(
            model_name="itemlocationcandidate",
            constraint=models.UniqueConstraint(fields=("item", "rank"), name="uq_item_location_rank"),
        ),
    ]

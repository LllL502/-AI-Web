from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("claims", "0002_claim_direct_handover")]

    operations = [
        migrations.AddField(
            model_name="claim",
            name="claimant_deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]

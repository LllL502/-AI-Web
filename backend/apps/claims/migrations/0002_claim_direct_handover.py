from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("claims", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="claim",
            name="handover_method",
            field=models.CharField(
                blank=True,
                choices=[("STATION", "服务站交接"), ("DIRECT", "双方直接交接")],
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="claim",
            name="claimant_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="claim",
            name="finder_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

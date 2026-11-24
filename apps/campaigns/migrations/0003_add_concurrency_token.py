import uuid

from django.db import migrations, models


def populate_concurrency_tokens(apps, schema_editor):
    Campaign = apps.get_model("campaigns", "Campaign")
    for campaign in Campaign.objects.filter(concurrency_token__isnull=True).iterator():
        campaign.concurrency_token = uuid.uuid4()
        campaign.save(update_fields=["concurrency_token"])


class Migration(migrations.Migration):
    initial = False

    dependencies = [
        ("campaigns", "0001_initial"),
        ("budgets", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="concurrency_token",
            field=models.UUIDField(editable=False, unique=True, null=True),
        ),
        migrations.RunPython(
            populate_concurrency_tokens,
            migrations.RunPython.noop,
        ),
    ]

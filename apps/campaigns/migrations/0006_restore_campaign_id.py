from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("campaigns", "0002_campaign_schema_baseline"),
        ("campaigns", "0005_alter_campaign_concurrency_token"),
    ]

    operations = [migrations.RenameField(model_name="campaign", old_name="idim", new_name="id")]

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("campaigns", "0003_add_concurrency_token")]

    operations = [migrations.RenameField(model_name="campaign", old_name="id", new_name="idim")]

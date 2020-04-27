# Allow the patch prefix to be blank and default to the empty string.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("patchlab", "0003_add_submission_version"),
    ]

    operations = [
        migrations.AlterField(
            model_name="branch",
            name="subject_prefix",
            field=models.CharField(
                blank=True,
                default="",
                help_text="The prefix to include in emails in addition to 'PATCHvN'. The default is no prefix.",
                max_length=64,
            ),
        ),
    ]

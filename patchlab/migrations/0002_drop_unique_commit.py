# Generated by Django 2.2.7 on 2019-11-19 06:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("patchlab", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="bridgedsubmission",
            name="commit",
            field=models.CharField(blank=True, max_length=128, null=True),
        )
    ]

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("support_center", "0009_supportitem_is_visible_to_experts_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SupportWidgetMetricReset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("system", models.CharField(max_length=120, unique=True)),
                ("reset_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["system"],
            },
        ),
    ]

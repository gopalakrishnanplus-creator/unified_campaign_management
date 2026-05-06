from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("support_center", "0007_supportitem_is_visible_to_publishers"),
    ]

    operations = [
        migrations.AddField(
            model_name="supportrequest",
            name="origin_channel",
            field=models.CharField(
                choices=[("direct", "Direct"), ("assistant", "Assistant"), ("widget", "Widget")],
                default="direct",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="supportrequest",
            name="pm_ticket_raised_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="SupportWidgetEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_type", models.CharField(max_length=24)),
                ("source_system", models.CharField(blank=True, max_length=120)),
                ("source_flow", models.CharField(blank=True, max_length=120)),
                ("event_type", models.CharField(choices=[("opened", "Opened"), ("resolved", "Resolved")], max_length=24)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "support_category",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="widget_events", to="support_center.supportcategory"),
                ),
                (
                    "support_page",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="widget_events", to="support_center.supportpage"),
                ),
                (
                    "support_request",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="widget_events", to="support_center.supportrequest"),
                ),
                (
                    "support_super_category",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="widget_events", to="support_center.supportsupercategory"),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]

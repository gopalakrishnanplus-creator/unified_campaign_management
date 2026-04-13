from django.db import migrations, models


def sync_escalated_ticket_flags(apps, schema_editor):
    Ticket = apps.get_model("ticketing", "Ticket")
    Ticket.objects.filter(support_request__is_escalated=True).update(is_escalated=True, priority="critical")


class Migration(migrations.Migration):
    dependencies = [
        ("support_center", "0006_supportrequest_queue_ticket_number_and_more"),
        ("ticketing", "0009_alter_ticketattachment_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="is_escalated",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(sync_escalated_ticket_flags, migrations.RunPython.noop),
    ]

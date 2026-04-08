from django.core.management.base import BaseCommand, CommandError

from apps.ticketing.external_ticketing import ExternalTicketingSyncError, external_ticketing_enabled, sync_external_directory


class Command(BaseCommand):
    help = "Syncs departments and manager assignments from the internal ticketing system directory API."

    def handle(self, *args, **options):
        if not external_ticketing_enabled():
            raise CommandError("External ticketing sync is not enabled. Check EXTERNAL_TICKETING_* settings.")
        try:
            departments = sync_external_directory()
        except ExternalTicketingSyncError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Synced {len(departments)} departments from the internal ticketing directory."))
        for department in departments:
            manager = department.default_recipient.full_name if department.default_recipient_id else "Unassigned"
            self.stdout.write(
                f"- {department.display_name} [{department.display_code}] -> {manager}"
            )

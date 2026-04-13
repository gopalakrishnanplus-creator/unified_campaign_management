from __future__ import annotations

from collections import OrderedDict


BASE_URL = "http://127.0.0.1:8002"
VERIFIED_DATE = "2026-04-11"
MANUALS_DIR = "docs/product-user-flows"
ASSETS_DIR = f"{MANUALS_DIR}/assets"
DECKS_DIR = "output/doc/user-flow-decks"
QA_DIR = f"{DECKS_DIR}/qa-pdf"


ROLE_MAP = OrderedDict(
    [
        (
            "Project Manager",
            "Runs the PM dashboard, reviews unresolved support issues, creates tickets, and monitors campaign performance.",
        ),
        (
            "Department Owner / Support Lead",
            "Works the scoped ticket queue, changes status, delegates work, and records notes.",
        ),
        (
            "Doctor",
            "Uses page-wise FAQs, widgets, and the guided assistant to self-serve or escalate issues.",
        ),
        (
            "Clinic Staff",
            "Uses the clinic-staff support center for operational FAQs and escalation into the PM queue.",
        ),
        (
            "Brand Manager",
            "Uses the brand-manager support center for authentication, sharing, and reporting support questions.",
        ),
        (
            "Field Rep",
            "Uses the field-rep support center for activation, login, onboarding, and sharing issues.",
        ),
        (
            "Patient",
            "Uses the patient support center for patient-education and Red Flag Alert access issues.",
        ),
        (
            "Integration Partner / Trainer",
            "Uses the FAQ links API and embeddable widgets to publish support flows into other properties.",
        ),
    ]
)


WORKFLOWS = [
    {
        "order": 1,
        "slug": "platform-overview-and-role-map",
        "section": "Platform Overview",
        "title": "Platform Overview and Role Map",
        "purpose": (
            "Explain the live product surface, the implemented user roles, and the handoff points between self-service support, "
            "project-management triage, and ticket execution."
        ),
        "primary_user": "Internal trainer, implementation lead, or any new team member onboarding to the platform.",
        "entry_point": f"{BASE_URL}/",
        "summary": [
            "The product is a Django-based campaign operations hub with public support experiences and authenticated PM/ticketing dashboards.",
            "Self-service users enter through role-specific support hubs, while internal teams use the PM dashboard, ticket queue, and reporting pages.",
            "The implemented product centers on support enablement, escalation, reporting, and ticket routing rather than separate branded portals for every role.",
        ],
        "steps": [
            {
                "title": "Open the platform home page",
                "user_does": "Open the root URL to view the shared navigation and campaign landing page.",
                "user_sees": "A public home page with campaign summary content plus links into every role-specific support center.",
                "why": "This is the simplest way to orient a new user to the main product surfaces before discussing role-specific tasks.",
                "expected_result": "The trainer can point to the support-role navigation, sign-in path, and campaign context on one screen.",
                "notes": "Use this step to explain that most external users stay in the public support flows, while internal users move into authenticated dashboards.",
                "screenshot": {
                    "filename": "01-homepage.png",
                    "caption": "Platform home page",
                    "show": "The public landing page, navigation links for every support role, and the sign-in option.",
                },
            },
            {
                "title": "Explain the internal command center",
                "user_does": "Move from the public home page into the Project Management dashboard after sign-in.",
                "user_sees": "A decision-focused dashboard with ticket KPIs, pending PM reviews, and navigation to ticketing and performance views.",
                "why": "This screen anchors every internal workflow and shows where unresolved external issues are managed.",
                "expected_result": "New team members understand that `/app/` is the operational hub for PM-led work.",
                "notes": "The PM dashboard is the main internal entry point for project managers and is prioritized throughout this pack.",
                "screenshot": {
                    "filename": "02-project-manager-dashboard.png",
                    "caption": "Project Management dashboard",
                    "show": "The dashboard hero, KPI cards, and operational action links.",
                },
            },
            {
                "title": "Show the self-service support experience",
                "user_does": "Open a live role-specific support center such as Doctor Support.",
                "user_sees": "Page-wise FAQ cards, widget launch links, and escalation options that feed the PM queue.",
                "why": "This shows how external users begin a support journey without requiring a separate authenticated portal.",
                "expected_result": "The audience understands where self-service begins and how issues reach the internal team if unresolved.",
                "notes": "This implementation differs from older extracted notes that describe richer standalone portals for some roles.",
                "screenshot": {
                    "filename": "03-doctor-support-landing.png",
                    "caption": "Role-based support landing page",
                    "show": "The doctor support center with page-wise FAQ cards and the free-text support block.",
                },
            },
            {
                "title": "Connect role handoffs end to end",
                "user_does": "Walk through the role map from support user to PM review to departmental ticket ownership.",
                "user_sees": "A clear explanation of where each workflow starts, what happens when an issue is unresolved, and which role owns the next action.",
                "why": "This gives trainers a single narrative to introduce the whole system before diving into detail decks.",
                "expected_result": "Participants can describe the high-level journey without needing to inspect the codebase.",
                "notes": "Use the role map and flow diagram in this manual when presenting to new internal teams.",
                "screenshot": {
                    "filename": "04-field-rep-support-landing.png",
                    "caption": "Field Rep support entry point",
                    "show": "A second role-based support center to reinforce that each audience gets its own support catalog.",
                },
            },
        ],
        "success_criteria": [
            "The audience can name the implemented user roles and their starting pages.",
            "The audience can explain how public support flows hand unresolved issues into the PM dashboard.",
            "The audience understands that the codebase currently emphasizes support, PM operations, reporting, and ticketing over custom role-specific portals.",
        ],
        "related_documents": [
            "README.md",
            "docs/extracted/our-systems.txt",
            "docs/extracted/customer-support.txt",
            "docs/extracted/ticketing.txt",
        ],
        "trainer_tips": [
            "Lead with the PM dashboard, because it ties together support escalation, ticketing, and campaign performance.",
            "Call out the difference between live product behavior and older extracted notes where necessary.",
        ],
        "status": (
            "Live-verified against the application on 2026-04-11. Older extracted notes mention richer role-specific portals, but the implemented product surface is primarily role-specific support centers plus PM and ticketing dashboards."
        ),
    },
    {
        "order": 2,
        "slug": "project-manager-dashboard-and-triage",
        "section": "Project Management & Operations",
        "title": "Project Manager Dashboard and Triage",
        "purpose": "Document how a Project Manager uses the command-center dashboard to monitor workload, inspect pending items, and launch the next operational action.",
        "primary_user": "Project Manager",
        "entry_point": f"{BASE_URL}/accounts/dev-login/",
        "summary": [
            "The PM dashboard centralizes ticket KPIs, quick links, pending support reviews, a high-priority queue, and operational drill-downs.",
            "Campaign filters can change the dashboard scope without leaving the page.",
            "The page is the fastest way to move from monitoring into ticket creation or deeper analysis.",
        ],
        "steps": [
            {
                "title": "Sign in and open the PM dashboard",
                "user_does": "Use the development login shortcut or the standard authenticated sign-in flow, then open `/app/`.",
                "user_sees": "A dashboard hero area, campaign filter, and quick links for ticketing and performance.",
                "why": "This is the primary operational entry point for PM-led work.",
                "expected_result": "The PM lands on the dashboard without needing to open multiple admin pages.",
                "notes": "In the demo environment, `/accounts/dev-login/` is the fastest path for capture and training.",
                "screenshot": {
                    "filename": "01-dashboard-overview.png",
                    "caption": "PM dashboard overview",
                    "show": "The hero section, campaign filter, and shortcut links to core PM tools.",
                },
            },
            {
                "title": "Review summary KPIs and the current queue shape",
                "user_does": "Scan the KPI cards and category, status, and priority breakdowns.",
                "user_sees": "Decision-ready counts for total tickets, open work, critical issues, and queue distribution.",
                "why": "This lets the PM understand workload and urgency before drilling into the queue.",
                "expected_result": "The PM knows which queue slices deserve immediate attention.",
                "notes": "Use the category and status blocks to explain how the dashboard surfaces bottlenecks without opening the full ticket list first.",
                "screenshot": {
                    "filename": "02-dashboard-operational-details.png",
                    "caption": "PM dashboard KPI and queue breakdown",
                    "show": "Summary cards plus the dashboard breakdowns for category, status, and priority.",
                },
            },
            {
                "title": "Inspect unresolved support submissions",
                "user_does": "Scroll to the PM review table for “Other” submissions that came from widgets or the assistant.",
                "user_sees": "A pending-review table with the originating system, flow, page context, and the escalation action.",
                "why": "This connects public support journeys directly into PM operations.",
                "expected_result": "The PM can decide whether to raise a formal ticket from the unresolved issue.",
                "notes": "If the table is empty, trainers should explain that unresolved support requests are created only when users choose “Other” or submit a PM-review route.",
                "screenshot": {
                    "filename": "03-dashboard-pending-issues.png",
                    "caption": "PM review queue",
                    "show": "The table of pending “Other” support submissions waiting for ticket creation.",
                },
            },
            {
                "title": "Launch the next action from the dashboard",
                "user_does": "Use the quick actions to open the full ticket queue, create a ticket, or move into the performance dashboard.",
                "user_sees": "Clickable navigation paths that keep the PM inside the main operations loop.",
                "why": "The dashboard is designed to reduce context-switching and keep the PM in one command center.",
                "expected_result": "The PM can move from overview to execution in one click.",
                "notes": "Show both the full queue and the campaign performance link so the PM understands the dashboard’s dual operational and analytical roles.",
                "screenshot": {
                    "filename": "04-dashboard-high-priority-queue.png",
                    "caption": "High-priority queue from the PM dashboard",
                    "show": "The high-priority queue card and contextual launch paths into the detailed ticket list.",
                },
            },
        ],
        "success_criteria": [
            "The PM can find current workload, pending support reviews, and urgent tickets without leaving `/app/`.",
            "The PM can explain when to stay on the dashboard versus when to open ticketing or performance views.",
        ],
        "related_documents": [
            "README.md",
            "docs/testing-guide.md",
        ],
        "trainer_tips": [
            "Start every PM training session here to establish a consistent operating rhythm.",
            "Use the pending-review table as the bridge into the unresolved support workflow deck.",
        ],
        "status": "Live-verified against the seeded demo environment on 2026-04-11.",
    },
    {
        "order": 3,
        "slug": "project-manager-review-other-submissions",
        "section": "Project Management & Operations",
        "title": "Project Manager Review of “Other” Support Submissions",
        "purpose": "Document the end-to-end escalation path from an unresolved assistant/widget issue into a PM-reviewed ticket.",
        "primary_user": "Project Manager",
        "entry_point": f"{BASE_URL}/support/doctor/assistant/",
        "summary": [
            "Public users can select “Other” in the guided support assistant or widget when no FAQ resolves their issue.",
            "Those submissions land in the PM dashboard for review before a ticket is created.",
            "The PM can open the pre-filled raise-ticket screen, confirm routing, and create the formal ticket.",
        ],
        "steps": [
            {
                "title": "Capture the unresolved issue in the assistant",
                "user_does": "A support user drills down to the relevant system, flow, and screen, then chooses “Other” and describes the issue.",
                "user_sees": "The assistant’s “Other issue” form with fields for name, phone number, email, description, and optional image upload.",
                "why": "This path preserves the context the PM needs to classify the problem accurately.",
                "expected_result": "The unresolved issue is ready to be submitted for PM review.",
                "notes": "This is the core public-to-internal escalation handoff in the live product.",
                "screenshot": {
                    "filename": "01-doctor-assistant-other-form.png",
                    "caption": "Assistant unresolved issue form",
                    "show": "The guided support assistant after “Other” is selected, with the PM-review form visible.",
                },
            },
            {
                "title": "Confirm that the support request was logged",
                "user_does": "Submit the unresolved issue form from the assistant.",
                "user_sees": "A success page confirming that the issue is recorded and available in the PM dashboard.",
                "why": "This reassures the external user and sets expectations that the issue has moved into PM review.",
                "expected_result": "A `SupportRequest` exists in pending PM review status.",
                "notes": "Use the success message wording during training so users understand they are not yet looking at a final support resolution.",
                "screenshot": {
                    "filename": "02-doctor-request-success.png",
                    "caption": "Support request logged confirmation",
                    "show": "The confirmation page that appears after an unresolved issue is submitted for PM review.",
                },
            },
            {
                "title": "Review the pending issue on the PM dashboard",
                "user_does": "Open `/app/` and locate the pending “Other” submission in the PM review table.",
                "user_sees": "The system, user type, flow, page, section, screen, issue description, and the `Raise Ticket` action.",
                "why": "This is where the PM decides whether the issue should become a ticket and where it should be routed.",
                "expected_result": "The PM has enough context to continue into ticket creation without re-contacting the user.",
                "notes": "Use this step to show that the assistant preserves the screen-level context in the PM review queue.",
                "screenshot": {
                    "filename": "03-pm-pending-review.png",
                    "caption": "Pending unresolved issue in the PM queue",
                    "show": "The PM dashboard table row that corresponds to the just-submitted unresolved issue.",
                },
            },
            {
                "title": "Create the formal ticket from the pre-filled PM form",
                "user_does": "Open the `Raise Ticket` screen, confirm the category and type, choose a department and campaign, and submit the form.",
                "user_sees": "A ticket-creation page pre-filled with the support request description and routing context.",
                "why": "This minimizes re-entry and keeps the original support context attached to the ticket.",
                "expected_result": "A new ticket is created and linked back to the originating support request.",
                "notes": "The PM only needs to fill missing internal routing fields such as department and campaign.",
                "screenshot": {
                    "filename": "04-raise-ticket-form.png",
                    "caption": "Raise ticket from support issue",
                    "show": "The PM review form with support context pre-filled and ready for final ticket creation.",
                },
            },
            {
                "title": "Verify the created ticket detail",
                "user_does": "Open the resulting ticket detail page after the PM submits the synced ticket form.",
                "user_sees": "The new ticket’s title, description, classification, assignment, and workflow controls.",
                "why": "This confirms the unresolved support issue is now in the internal execution workflow.",
                "expected_result": "The PM can hand the work off to the correct department or begin managing it immediately.",
                "notes": "If an image was uploaded, trainers should also point out where the resulting note attachment appears on the ticket detail page.",
                "screenshot": {
                    "filename": "05-raised-ticket-detail.png",
                    "caption": "Ticket created from a support request",
                    "show": "The resulting ticket detail page after the PM raises the synced ticket.",
                },
            },
        ],
        "success_criteria": [
            "The audience can explain how unresolved support issues move into PM review.",
            "The PM can create a formal ticket without losing system, flow, or page context.",
        ],
        "related_documents": [
            "README.md",
            "docs/testing-guide.md",
            "docs/support-widget-integration.md",
        ],
        "trainer_tips": [
            "Show the assistant capture and PM review together so the handoff feels continuous rather than like two unrelated screens.",
            "Emphasize that this workflow is for unresolved support gaps, not every FAQ interaction.",
        ],
        "status": "Live-verified against the assistant, PM dashboard, and ticket-creation flow on 2026-04-11.",
    },
    {
        "order": 4,
        "slug": "project-manager-manual-ticket-creation",
        "section": "Project Management & Operations",
        "title": "Project Manager Manual Ticket Creation and Routing",
        "purpose": "Document how a Project Manager creates a new ticket directly from the ticketing workspace when the issue did not originate in the support assistant or widget.",
        "primary_user": "Project Manager",
        "entry_point": f"{BASE_URL}/ticketing/new/",
        "summary": [
            "The PM can create tickets directly from `/ticketing/new/` using the configured categories, ticket types, and departments.",
            "The form supports category and ticket-type selection, source-system tagging, campaign association, requester details, and status/priority defaults.",
            "On submission, the PM lands directly on the ticket detail page to continue routing or execution.",
        ],
        "steps": [
            {
                "title": "Open the ticket creation form",
                "user_does": "From the PM dashboard or ticket queue, choose `Create ticket`.",
                "user_sees": "A form for the title, description, category, ticket type, user type, source system, priority, department, campaign, and requester details.",
                "why": "This is the starting point for manually raised internal issues, back-office requests, or PM-created escalations.",
                "expected_result": "The PM is ready to enter the full routing payload for the new issue.",
                "notes": "Use the live form to show the seeded department and taxonomy options during training.",
                "screenshot": {
                    "filename": "01-ticket-create-form.png",
                    "caption": "Manual ticket creation form",
                    "show": "The `Create ticket` form with routing, classification, and requester fields visible.",
                },
            },
            {
                "title": "Complete classification and routing",
                "user_does": "Choose the ticket category, type, priority, department, and campaign, then confirm the requester details.",
                "user_sees": "A routing-ready form that can classify the ticket before it is created.",
                "why": "Correct classification and routing reduce rework later in the lifecycle.",
                "expected_result": "The form is complete and ready to submit.",
                "notes": "If the desired type is missing, the PM can create a new ticket type inline during submission.",
                "screenshot": {
                    "filename": "02-ticket-create-routing.png",
                    "caption": "Manual ticket routing fields",
                    "show": "The lower portion of the ticket form where the PM chooses department, campaign, and requester details.",
                },
            },
            {
                "title": "Create the ticket and review the result",
                "user_does": "Submit the form and open the resulting ticket detail page.",
                "user_sees": "A new ticket with the chosen classification, assignment, requester details, and workflow controls.",
                "why": "This is where the PM confirms the new issue entered the system as expected.",
                "expected_result": "The ticket exists in the queue and can be delegated, updated, or reviewed immediately.",
                "notes": "In training, point out that the PM lands on the detail page rather than back on the list view.",
                "screenshot": {
                    "filename": "03-manual-ticket-detail.png",
                    "caption": "Manual ticket detail page",
                    "show": "The detail page of a newly created manual ticket.",
                },
            },
            {
                "title": "Return to the queue and validate the entry",
                "user_does": "Open the ticket queue and confirm the new ticket appears in the expected sort order or filtered slice.",
                "user_sees": "The central queue with the newly created ticket listed alongside existing work.",
                "why": "This demonstrates where manually created work becomes visible to the broader operations team.",
                "expected_result": "The PM can see the new ticket in the queue and continue into execution if needed.",
                "notes": "Use search or filters to highlight the new ticket quickly during training.",
                "screenshot": {
                    "filename": "04-ticket-queue-filtered.png",
                    "caption": "Manual ticket visible in the queue",
                    "show": "The ticket queue filtered or sorted so the newly created manual ticket is visible.",
                },
            },
        ],
        "success_criteria": [
            "The PM can create a new ticket without relying on a support-originated request.",
            "The ticket appears in the queue with the expected category, department, and requester context.",
        ],
        "related_documents": [
            "README.md",
            "docs/testing-guide.md",
        ],
        "trainer_tips": [
            "Use this workflow for internal issues, discovered defects, or requests raised outside the self-service support surface.",
            "Reinforce the difference between manually created tickets and PM-reviewed support requests.",
        ],
        "status": "Live-verified against the ticket-create form and queue on 2026-04-11.",
    },
    {
        "order": 5,
        "slug": "department-owner-ticket-execution",
        "section": "Project Management & Operations",
        "title": "Department Owner Ticket Execution",
        "purpose": "Document how a departmental owner or support lead works their scoped queue, opens ticket detail, and updates the ticket lifecycle.",
        "primary_user": "Department Owner / Support Lead",
        "entry_point": f"{BASE_URL}/admin/login/ then {BASE_URL}/ticketing/",
        "summary": [
            "Department owners see a scoped subset of the ticket queue rather than the full PM command center.",
            "They can open ticket detail pages, change status, delegate the ticket, add notes, and review routing history.",
            "This workflow is the execution layer that follows PM triage and ticket creation.",
        ],
        "steps": [
            {
                "title": "Authenticate as a department owner",
                "user_does": "Sign in as a staff user and open the ticket queue.",
                "user_sees": "A ticket list limited to the departmental scope relevant to that user.",
                "why": "This keeps operational users focused on the work they own.",
                "expected_result": "The department owner sees only the queue slice they are meant to manage.",
                "notes": "In the demo environment, staff users can authenticate through the Django admin login and then navigate into `/ticketing/`.",
                "screenshot": {
                    "filename": "01-owner-ticket-queue.png",
                    "caption": "Department-owner ticket queue",
                    "show": "The scoped queue showing only the tickets visible to the department owner.",
                },
            },
            {
                "title": "Open a ticket from the queue",
                "user_does": "Select a ticket number from the scoped queue.",
                "user_sees": "The ticket detail page with classification, assignment, requester data, notes, and routing history.",
                "why": "This is the operational workspace for day-to-day execution.",
                "expected_result": "The department owner can review the full context of the issue before making changes.",
                "notes": "Use this step to point out the difference between the PM dashboard summary and the detailed execution workspace.",
                "screenshot": {
                    "filename": "02-owner-ticket-detail.png",
                    "caption": "Department-owner ticket detail",
                    "show": "The ticket detail page opened from the scoped queue.",
                },
            },
            {
                "title": "Update status or delegate the work",
                "user_does": "Use the status-change and delegate controls in the ticket detail sidebar.",
                "user_sees": "Status and assignee controls that update the ticket without leaving the detail page.",
                "why": "These controls keep ticket execution lightweight and traceable.",
                "expected_result": "The department owner can move work forward or hand it to the right individual.",
                "notes": "Show the routing controls even if you do not change the live ticket during training.",
                "screenshot": {
                    "filename": "03-owner-routing-actions.png",
                    "caption": "Department-owner routing controls",
                    "show": "The status update and delegation controls on the ticket detail page.",
                },
            },
            {
                "title": "Record execution notes and review history",
                "user_does": "Use the note form and review the routing history timeline on the ticket detail page.",
                "user_sees": "A notes section for operational commentary plus an immutable routing history panel.",
                "why": "These sections document how the ticket was worked over time.",
                "expected_result": "The department owner understands where to record progress and how to audit prior movement.",
                "notes": "If attachments are used in production, explain that note uploads appear alongside the note history.",
                "screenshot": {
                    "filename": "04-owner-notes-and-history.png",
                    "caption": "Notes and routing history",
                    "show": "The lower portion of the ticket detail page with notes and routing history visible.",
                },
            },
        ],
        "success_criteria": [
            "The department owner can open only their relevant queue and work a ticket without PM assistance.",
            "The department owner knows where to update status, delegate work, and record notes.",
        ],
        "related_documents": [
            "README.md",
            "docs/testing-guide.md",
        ],
        "trainer_tips": [
            "Clarify that the PM dashboard is not the primary operational screen for department owners.",
            "Use a real scoped queue to explain role-based visibility and responsibility.",
        ],
        "status": "Live-verified using a staff department-owner account and scoped ticket queue on 2026-04-11.",
    },
    {
        "order": 6,
        "slug": "project-manager-campaign-performance-and-reporting",
        "section": "Project Management & Operations",
        "title": "Project Manager Campaign Performance and Reporting",
        "purpose": "Document how a Project Manager reviews campaign performance, subsystem metrics, and reporting contracts.",
        "primary_user": "Project Manager",
        "entry_point": f"{BASE_URL}/app/performance/",
        "summary": [
            "The performance dashboard separates analytical review from the PM dashboard’s operational triage surface.",
            "It aggregates campaign metrics, subsystem sections, adoption data, and external growth metrics.",
            "The reporting contracts page exposes the expected JSON contract for downstream integration or validation.",
        ],
        "steps": [
            {
                "title": "Open the campaign performance dashboard",
                "user_does": "From the PM dashboard, choose `Campaign performance` or navigate directly to `/app/performance/`.",
                "user_sees": "A performance-oriented dashboard with campaign filter controls and metric sections.",
                "why": "This keeps analytical review separate from the main ticket operations surface.",
                "expected_result": "The PM can switch from triage mode into performance review without losing campaign context.",
                "notes": "Use the campaign filter to demonstrate how PMs can narrow the scope when discussing a single program.",
                "screenshot": {
                    "filename": "01-performance-dashboard-overview.png",
                    "caption": "Campaign performance dashboard",
                    "show": "The top of the performance dashboard with campaign scope controls and summary messaging.",
                },
            },
            {
                "title": "Review campaign KPIs and subsystem sections",
                "user_does": "Scroll through the subsystem blocks and supporting KPI cards.",
                "user_sees": "Live-or-fallback reporting sections for Red Flag Alert, In-clinic, Patient Education, adoption, and external growth.",
                "why": "This is where the PM reviews health and growth across delivery systems.",
                "expected_result": "The PM can describe current performance without manually aggregating multiple reporting feeds.",
                "notes": "If live data is unavailable, the UI still presents fallback content sourced from local snapshots.",
                "screenshot": {
                    "filename": "02-performance-dashboard-kpis.png",
                    "caption": "Performance metrics and subsystem sections",
                    "show": "The KPI cards and subsystem summaries inside the campaign performance dashboard.",
                },
            },
            {
                "title": "Open the reporting contracts reference",
                "user_does": "Navigate to `/reporting/contracts/` from the global nav.",
                "user_sees": "The human-readable reporting contract page that documents the expected payload structure.",
                "why": "This helps PMs, analysts, and implementers align on what the reporting APIs return.",
                "expected_result": "The PM knows where to find contract definitions when investigating metric discrepancies.",
                "notes": "This page is especially useful during cross-team troubleshooting or data-validation conversations.",
                "screenshot": {
                    "filename": "03-reporting-contracts.png",
                    "caption": "Reporting contracts reference",
                    "show": "The reporting contracts page that documents the subsystem payload structure.",
                },
            },
            {
                "title": "Use performance insights to inform operational work",
                "user_does": "Cross-reference performance findings with ticketing and PM triage as needed.",
                "user_sees": "A clear separation between analytical review and operational workflows, linked through shared campaign scope.",
                "why": "PMs often move from performance anomalies into ticketing or support follow-up.",
                "expected_result": "The PM can connect performance review to operational follow-through.",
                "notes": "This workflow intentionally complements, rather than duplicates, the main PM dashboard.",
                "screenshot": {
                    "filename": "04-performance-dashboard-system-status.png",
                    "caption": "Performance dashboard operational context",
                    "show": "A lower section of the dashboard that helps trainers explain how reporting context supports operational decisions.",
                },
            },
        ],
        "success_criteria": [
            "The PM can use the performance dashboard to review campaign health independently from ticket triage.",
            "The PM knows where to inspect the reporting payload contract when needed.",
        ],
        "related_documents": [
            "README.md",
            "docs/reporting-api-contract.md",
            "docs/testing-guide.md",
        ],
        "trainer_tips": [
            "Keep this workflow distinct from the PM dashboard so trainees understand which page is for action versus analysis.",
            "Use one campaign-filter example to show how the same program can be tracked across operations and performance.",
        ],
        "status": "Live-verified using the performance dashboard and reporting contract page on 2026-04-11.",
    },
    {
        "order": 7,
        "slug": "doctor-self-service-support",
        "section": "Self-Service Support",
        "title": "Doctor Self-Service Support",
        "purpose": "Document how a doctor uses the support landing page, FAQ pages, widgets, and assistant to resolve issues or escalate them.",
        "primary_user": "Doctor",
        "entry_point": f"{BASE_URL}/support/doctor/",
        "summary": [
            "Doctors enter through a dedicated support center with page-wise FAQ cards for Customer Support, In-clinic, Patient Education, and Red Flag Alert topics.",
            "Each page can be opened as a full article set or as an embeddable widget.",
            "If the issue is not solved, the doctor can escalate through the assistant or free-text support form.",
        ],
        "steps": [
            {
                "title": "Open the Doctor Support landing page",
                "user_does": "Navigate to `/support/doctor/`.",
                "user_sees": "A page-wise FAQ landing page with cards for each supported doctor-facing screen or journey.",
                "why": "This is the doctor’s main starting point for self-service support.",
                "expected_result": "The doctor can identify the relevant screen or flow without needing an internal user.",
                "notes": "The support catalog is organized page-wise, which is different from a generic help-center structure.",
                "screenshot": {
                    "filename": "01-doctor-support-landing.png",
                    "caption": "Doctor support landing page",
                    "show": "The doctor landing page with page-wise FAQ cards and escalation options.",
                },
            },
            {
                "title": "Open a page-wise FAQ view",
                "user_does": "Choose a page such as the In-clinic doctor verification page.",
                "user_sees": "A full FAQ page with sections, question cards, and page context.",
                "why": "This gives the doctor a richer reading experience than the compact widget.",
                "expected_result": "The doctor can scan the relevant FAQs for the current screen.",
                "notes": "Use a page with multiple FAQs during training so the structure is obvious.",
                "screenshot": {
                    "filename": "02-doctor-faq-page.png",
                    "caption": "Doctor FAQ page",
                    "show": "A doctor FAQ page showing the selected page title, sections, and questions.",
                },
            },
            {
                "title": "Use the guided assistant when the exact page is unclear",
                "user_does": "Open the doctor support assistant and choose the system, flow, and screen that matches the issue.",
                "user_sees": "A guided, step-by-step support assistant that narrows the support context before showing answers.",
                "why": "This helps doctors who know the problem but not the exact FAQ page name.",
                "expected_result": "The doctor either resolves the issue from a matching answer or chooses “Other.”",
                "notes": "The assistant preserves the selected system, flow, and page context for escalation.",
                "screenshot": {
                    "filename": "03-doctor-assistant-question.png",
                    "caption": "Doctor support assistant",
                    "show": "The assistant after the doctor has chosen a system, flow, and screen and is selecting a question.",
                },
            },
            {
                "title": "Escalate an unresolved issue",
                "user_does": "Choose `Other` or use the landing-page form when the answer is missing or not resolved.",
                "user_sees": "A form that records the issue for PM review or direct support follow-up, depending on the entry path.",
                "why": "This ensures doctors can continue even when self-service content is incomplete.",
                "expected_result": "The issue is recorded and routed into the internal workflow.",
                "notes": "Use the assistant-based escalation when you want to demonstrate the richer PM-review context.",
                "screenshot": {
                    "filename": "04-doctor-widget.png",
                    "caption": "Doctor page-wise support widget",
                    "show": "The doctor support widget used for compact, embedded support on a single page.",
                },
            },
        ],
        "success_criteria": [
            "A doctor can find the correct support page or assistant path without internal help.",
            "A doctor can recognize when to escalate through the assistant or support form.",
        ],
        "related_documents": [
            "README.md",
            "docs/support-widget-integration.md",
        ],
        "trainer_tips": [
            "Show both the page-wise FAQ experience and the assistant so doctors understand when each is more efficient.",
            "Use the widget screenshot to explain how the same content can be embedded elsewhere.",
        ],
        "status": "Live-verified against the doctor landing page, FAQ page, assistant, and widget on 2026-04-11.",
    },
    {
        "order": 8,
        "slug": "clinic-staff-self-service-support",
        "section": "Self-Service Support",
        "title": "Clinic Staff Self-Service Support",
        "purpose": "Document the clinic-staff self-service path for shared support topics and escalation into the internal queue.",
        "primary_user": "Clinic Staff",
        "entry_point": f"{BASE_URL}/support/clinic_staff/",
        "summary": [
            "Clinic staff use a lighter support catalog focused on shared operational topics such as support activation and reports.",
            "They can open page-wise FAQs or submit a free-text request from the landing page.",
            "This workflow is intentionally smaller than the doctor or field-rep flows in the current implementation.",
        ],
        "steps": [
            {
                "title": "Open the Clinic Staff support center",
                "user_does": "Navigate to `/support/clinic_staff/`.",
                "user_sees": "A clinic-staff support landing page with a short page-wise FAQ catalog and a free-text request form.",
                "why": "This is the implemented entry point for clinic-staff support needs.",
                "expected_result": "Clinic staff can quickly identify the relevant shared support topic.",
                "notes": "Explain that the clinic-staff support surface is intentionally narrower than the doctor catalog in the live app.",
                "screenshot": {
                    "filename": "01-clinic-staff-landing.png",
                    "caption": "Clinic Staff support landing page",
                    "show": "The clinic-staff role page with its smaller FAQ catalog and support form.",
                },
            },
            {
                "title": "Open a shared FAQ page",
                "user_does": "Choose a page such as `Sharing & Activation Page` or `Reports & Insights Page`.",
                "user_sees": "A page-level FAQ view with the selected operational topic and corresponding answers.",
                "why": "This is the main self-service path for clinic-staff users.",
                "expected_result": "Clinic staff can review the available answers before escalating.",
                "notes": "Use a short FAQ page for quick walkthroughs in training.",
                "screenshot": {
                    "filename": "02-clinic-staff-faq-page.png",
                    "caption": "Clinic Staff FAQ page",
                    "show": "A clinic-staff FAQ page for one of the shared operational support topics.",
                },
            },
            {
                "title": "Escalate when the answer is missing",
                "user_does": "Submit the free-text support request from the landing page if the FAQ does not resolve the issue.",
                "user_sees": "A form for requester details, subject, optional campaign, and issue description.",
                "why": "This provides a fallback path when the smaller clinic-staff catalog is not enough.",
                "expected_result": "The issue is recorded for internal handling.",
                "notes": "Point out that this route differs from the assistant-driven PM-review path used in other support flows.",
                "screenshot": {
                    "filename": "03-clinic-staff-free-text-form.png",
                    "caption": "Clinic Staff free-text support form",
                    "show": "The landing-page form used to capture a clinic-staff support request.",
                },
            },
        ],
        "success_criteria": [
            "Clinic staff can use the implemented role page to self-serve shared support topics.",
            "Clinic staff know how to escalate when the smaller catalog does not answer the question.",
        ],
        "related_documents": [
            "README.md",
        ],
        "trainer_tips": [
            "Set expectations that this role currently has a focused support catalog rather than a large guided experience.",
        ],
        "status": "Live-verified against the clinic-staff role page and page-wise FAQ flow on 2026-04-11.",
    },
    {
        "order": 9,
        "slug": "brand-manager-self-service-support",
        "section": "Self-Service Support",
        "title": "Brand Manager Self-Service Support",
        "purpose": "Document the implemented brand-manager support center and clarify how it differs from older portal-oriented notes.",
        "primary_user": "Brand Manager",
        "entry_point": f"{BASE_URL}/support/brand_manager/",
        "summary": [
            "The live product exposes brand-manager support as a role-specific support center rather than a separate authenticated portal.",
            "The available catalog focuses on customer support authentication, sharing, and reports.",
            "Brand managers can browse page-wise FAQs or escalate through the landing-page support form.",
        ],
        "steps": [
            {
                "title": "Open the Brand Manager support center",
                "user_does": "Navigate to `/support/brand_manager/`.",
                "user_sees": "A role-specific support landing page for brand-manager topics.",
                "why": "This is the actual implemented starting point for brand-manager support in the current product.",
                "expected_result": "The brand manager sees the available support pages and escalation form.",
                "notes": "Older extracted notes describe a richer brand-manager portal, but the live product currently implements a support center instead.",
                "screenshot": {
                    "filename": "01-brand-manager-landing.png",
                    "caption": "Brand Manager support landing page",
                    "show": "The brand-manager support center with the available page-wise support cards.",
                },
            },
            {
                "title": "Review an authentication or sharing FAQ page",
                "user_does": "Open the `Authentication Page` or `Sharing & Activation Page` from the role page.",
                "user_sees": "A page-wise FAQ view focused on the selected brand-manager support topic.",
                "why": "This reflects how brand managers self-serve in the live implementation.",
                "expected_result": "The brand manager can review the relevant answers before escalating.",
                "notes": "Use the authentication page for training because it most clearly differentiates brand-manager content from clinic-staff content.",
                "screenshot": {
                    "filename": "02-brand-manager-faq-page.png",
                    "caption": "Brand Manager FAQ page",
                    "show": "A brand-manager FAQ page for one of the available support topics.",
                },
            },
            {
                "title": "Submit a support request when needed",
                "user_does": "Use the free-text support form on the landing page if the available pages do not resolve the issue.",
                "user_sees": "A standard support request form that captures requester details and the issue summary.",
                "why": "This is the fallback when the support catalog does not cover the required action.",
                "expected_result": "The issue is recorded for internal handling.",
                "notes": "Call out the product/documentation mismatch here if trainees expect a dedicated brand-manager portal.",
                "screenshot": {
                    "filename": "03-brand-manager-free-text-form.png",
                    "caption": "Brand Manager support request form",
                    "show": "The landing-page form used to raise a brand-manager support request.",
                },
            },
        ],
        "success_criteria": [
            "Brand managers understand the implemented support center entry point.",
            "Trainers can clearly explain the difference between live behavior and older portal-oriented notes.",
        ],
        "related_documents": [
            "README.md",
            "docs/extracted/customer-support.txt",
        ],
        "trainer_tips": [
            "Be explicit about the mismatch between older notes and the live product to avoid confusion during onboarding.",
        ],
        "status": "Live-verified against the brand-manager support center on 2026-04-11. Known mismatch noted against older extracted documentation.",
    },
    {
        "order": 10,
        "slug": "field-rep-self-service-support",
        "section": "Self-Service Support",
        "title": "Field Rep Self-Service Support",
        "purpose": "Document how field reps use the role-specific support center for login, onboarding, sharing, and dashboard-menu issues.",
        "primary_user": "Field Rep",
        "entry_point": f"{BASE_URL}/support/field_rep/",
        "summary": [
            "Field reps have one of the richer public support catalogs in the current product, with In-clinic and Red Flag Alert flow pages.",
            "The role page exposes page-wise support pages and standalone widgets for field-rep workflows.",
            "If the content does not resolve the issue, field reps can escalate using the shared support form.",
        ],
        "steps": [
            {
                "title": "Open the Field Rep support center",
                "user_does": "Navigate to `/support/field_rep/`.",
                "user_sees": "A field-rep support page with page-wise cards for login, sharing, onboarding, dashboard menu, and shared support topics.",
                "why": "This is the live field-rep support entry point.",
                "expected_result": "The field rep can identify the closest page or screen name to the current issue.",
                "notes": "Use the role page to explain how multiple subsystems are combined into a single support experience.",
                "screenshot": {
                    "filename": "01-field-rep-landing.png",
                    "caption": "Field Rep support landing page",
                    "show": "The field-rep support center with its richer catalog of page-wise support cards.",
                },
            },
            {
                "title": "Open a field-rep-specific FAQ page",
                "user_does": "Choose a field-rep page such as `Field Rep Sharing Page` or `Field Rep Dashboard/Menu Page`.",
                "user_sees": "A page-level FAQ screen with the selected field-rep questions and answers.",
                "why": "This is the primary self-service experience for field-rep issues.",
                "expected_result": "The field rep can review answers tied to the exact screen or flow they are using.",
                "notes": "The In-clinic sharing page works well for training because it is easy to describe visually.",
                "screenshot": {
                    "filename": "02-field-rep-faq-page.png",
                    "caption": "Field Rep FAQ page",
                    "show": "A field-rep page-wise FAQ view with section-level questions.",
                },
            },
            {
                "title": "Use the standalone widget when embedded support is needed",
                "user_does": "Open the standalone widget link for a field-rep page.",
                "user_sees": "A compact support bot experience that can be embedded into another property.",
                "why": "This shows how the same content can support embedded experiences for field reps.",
                "expected_result": "The field rep understands the smaller widget flow for quick support access.",
                "notes": "This is also a good lead-in to the technical widget-integration workflow deck.",
                "screenshot": {
                    "filename": "03-field-rep-widget.png",
                    "caption": "Field Rep support widget",
                    "show": "The compact widget version of a field-rep support page.",
                },
            },
            {
                "title": "Escalate unresolved issues",
                "user_does": "Submit the support form from the role page when the widget or page content is not enough.",
                "user_sees": "A standard support request form that captures the user’s issue and optional campaign context.",
                "why": "This keeps field-rep issues moving even when a FAQ gap exists.",
                "expected_result": "The issue is handed off to the internal support workflow.",
                "notes": "Explain that the live product does not currently implement a separate authenticated field-rep portal beyond support and ticketing context.",
                "screenshot": {
                    "filename": "04-field-rep-free-text-form.png",
                    "caption": "Field Rep support request form",
                    "show": "The fallback field-rep support request form on the role page.",
                },
            },
        ],
        "success_criteria": [
            "Field reps can find the correct page-level support content for their flow.",
            "Field reps understand the difference between page, widget, and escalation paths.",
        ],
        "related_documents": [
            "README.md",
            "docs/support-widget-integration.md",
            "docs/extracted/customer-support.txt",
        ],
        "trainer_tips": [
            "Field-rep support is one of the best examples of page-wise support coverage across multiple systems, so use it when demonstrating breadth.",
        ],
        "status": "Live-verified against the field-rep support center, FAQ page, and widget on 2026-04-11.",
    },
    {
        "order": 11,
        "slug": "patient-self-service-support",
        "section": "Self-Service Support",
        "title": "Patient Self-Service Support",
        "purpose": "Document how patients reach patient-facing support pages and widgets for Patient Education and Red Flag Alert issues.",
        "primary_user": "Patient",
        "entry_point": f"{BASE_URL}/support/patient/",
        "summary": [
            "Patients use a dedicated support center with Patient Education and Red Flag Alert content.",
            "The support pages cover page-specific FAQs, while widgets provide a compact support-bot experience.",
            "Patients can escalate unresolved issues through the landing-page form or widget-driven support path.",
        ],
        "steps": [
            {
                "title": "Open the Patient support center",
                "user_does": "Navigate to `/support/patient/`.",
                "user_sees": "A patient-facing support landing page with page-wise cards for patient content and Red Flag Alert flows.",
                "why": "This is the starting point for patient self-service in the live app.",
                "expected_result": "The patient can identify the relevant page or journey without internal help.",
                "notes": "The patient role page is intentionally simpler than the doctor and field-rep catalogs.",
                "screenshot": {
                    "filename": "01-patient-landing.png",
                    "caption": "Patient support landing page",
                    "show": "The patient role page with Patient Education and Red Flag Alert support cards.",
                },
            },
            {
                "title": "Open a patient-facing FAQ page",
                "user_does": "Choose a page such as the patient page or Red Flag Alert result screen page.",
                "user_sees": "A page-wise FAQ experience tailored to patient issues.",
                "why": "This is the main content view for patient self-service.",
                "expected_result": "The patient can review the available guidance before escalating.",
                "notes": "Choose a page with recognizably patient-friendly wording when presenting to client teams.",
                "screenshot": {
                    "filename": "02-patient-faq-page.png",
                    "caption": "Patient FAQ page",
                    "show": "A patient-facing FAQ page with page-level support content.",
                },
            },
            {
                "title": "Use the widget for embedded support",
                "user_does": "Open a standalone patient widget for one of the patient pages.",
                "user_sees": "A compact support bot that can guide the patient through the page’s FAQs.",
                "why": "The widget is the most portable patient-facing support surface in the product.",
                "expected_result": "The patient can access the same content in a smaller guided format.",
                "notes": "This is a useful example when explaining how support content can be embedded in other patient journeys.",
                "screenshot": {
                    "filename": "03-patient-widget.png",
                    "caption": "Patient support widget",
                    "show": "The patient widget experience for a page-level support topic.",
                },
            },
            {
                "title": "Escalate when self-service does not resolve the issue",
                "user_does": "Use the support form or unresolved-issue path if a patient answer is missing.",
                "user_sees": "A capture form that routes the issue into the internal support workflow.",
                "why": "This prevents patient issues from stalling when FAQ coverage is incomplete.",
                "expected_result": "The unresolved issue is recorded for internal review.",
                "notes": "Keep the language client-friendly during training, since this role is often shown to external audiences.",
                "screenshot": {
                    "filename": "04-patient-free-text-form.png",
                    "caption": "Patient support request form",
                    "show": "The patient role page’s support request form used for escalation.",
                },
            },
        ],
        "success_criteria": [
            "Patients can navigate the role page, page-wise FAQs, and widgets without help.",
            "Patients know there is still an escalation path if the FAQ does not resolve the issue.",
        ],
        "related_documents": [
            "README.md",
            "docs/support-widget-integration.md",
        ],
        "trainer_tips": [
            "Use the patient workflow when you need an example of the smallest, most client-shareable support surface.",
        ],
        "status": "Live-verified against the patient support center, page view, and widget on 2026-04-11.",
    },
    {
        "order": 12,
        "slug": "support-widget-integration",
        "section": "Technical Enablement",
        "title": "Support Widget Integration",
        "purpose": "Document how an implementation partner or trainer discovers the available support links and uses the embeddable widget endpoints.",
        "primary_user": "Implementation partner, trainer, or technical owner embedding support content into another property.",
        "entry_point": f"{BASE_URL}/support/api/doctor/faq-links/",
        "summary": [
            "The application exposes JSON link catalogs and embeddable page-wise or combination widgets for role-specific support content.",
            "Partners can use the FAQ links API to discover available pages and then embed a widget URL in another product surface.",
            "Unresolved issues raised from widgets still flow back into the PM review queue, preserving the support context.",
        ],
        "steps": [
            {
                "title": "Inspect the FAQ links API",
                "user_does": "Open a FAQ links API endpoint such as `/support/api/doctor/faq-links/`.",
                "user_sees": "A JSON payload listing the supported pages, URLs, and counts for the selected role.",
                "why": "This is the discovery layer for downstream integration and link export.",
                "expected_result": "The implementation owner can identify which page or widget URL to embed.",
                "notes": "The repo also includes exported link files in `docs/` for quick reference.",
                "screenshot": {
                    "filename": "01-faq-links-api.png",
                    "caption": "FAQ links API response",
                    "show": "The JSON response from a FAQ links API endpoint used to discover support pages.",
                },
            },
            {
                "title": "Open a page-wise widget",
                "user_does": "Use one of the returned widget URLs and open it in standalone mode or with `?embed=1`.",
                "user_sees": "A compact support bot with section selection, question selection, and unresolved issue capture.",
                "why": "This is the embeddable support surface that partner systems can consume directly.",
                "expected_result": "The widget is ready to embed into another system or training environment.",
                "notes": "The widget is intentionally iframe-friendly and optimized for compact support access.",
                "screenshot": {
                    "filename": "02-page-wise-widget.png",
                    "caption": "Page-wise support widget",
                    "show": "A standalone page-wise widget showing the compact support bot experience.",
                },
            },
            {
                "title": "Open a combination widget",
                "user_does": "Use a category-level widget endpoint for a role and open it in standalone mode.",
                "user_sees": "A category-specific widget showing questions for a narrower support slice.",
                "why": "Combination widgets support more targeted embed scenarios than full page-wise widgets.",
                "expected_result": "The implementation owner understands when to use page-wise versus category-level widgets.",
                "notes": "This distinction is helpful when integrating into screen-specific help drawers or microsites.",
                "screenshot": {
                    "filename": "03-combination-widget.png",
                    "caption": "Combination support widget",
                    "show": "A category-specific widget for a narrower support context.",
                },
            },
            {
                "title": "Understand the escalation handoff",
                "user_does": "Review how unresolved widget issues move into the PM review queue.",
                "user_sees": "A consistent escalation path that preserves widget context and PM-review routing.",
                "why": "Partners need to know that embedded support still feeds the internal operations workflow.",
                "expected_result": "The integration owner can explain how widget-originated support issues are handled downstream.",
                "notes": "Reference the PM review workflow deck when teaching the full end-to-end escalation path.",
                "screenshot": {
                    "filename": "04-widget-escalation-context.png",
                    "caption": "Widget escalation context",
                    "show": "A widget view or PM queue screenshot that demonstrates the preserved support context.",
                },
            },
        ],
        "success_criteria": [
            "A partner can find the available support pages and widgets for a role.",
            "A partner understands how embedded support escalations continue into PM review.",
        ],
        "related_documents": [
            "README.md",
            "docs/support-widget-integration.md",
            "docs/support-widget-links.md",
            "docs/support-widget-page-links.md",
        ],
        "trainer_tips": [
            "Show both the API discovery response and the rendered widget so the integration path feels concrete.",
        ],
        "status": "Live-verified against the FAQ links API and rendered widgets on 2026-04-11.",
    },
]


def manual_filename(workflow: dict) -> str:
    return f"{workflow['order']:02d}-{workflow['slug']}.md"


def deck_filename(workflow: dict) -> str:
    return f"{workflow['order']:02d}-{workflow['slug']}.pptx"


def asset_relative_path(workflow: dict, filename: str) -> str:
    return f"assets/{workflow['slug']}/{filename}"


def workflow_by_slug(slug: str) -> dict:
    return next(workflow for workflow in WORKFLOWS if workflow["slug"] == slug)

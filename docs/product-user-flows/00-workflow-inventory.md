# Workflow Inventory

        This inventory is the top-level guide to the user-flow training pack generated from the live application and repository source of truth.

        ## Scope

        - Verification date: `2026-04-11`
        - Source of truth order:
          1. live application behavior
          2. application code and templates
          3. project handoff and extracted documents
          4. older manual text
        - Demo base URL used for capture: `http://127.0.0.1:8002`

        ## Role Map

        ```mermaid
flowchart LR
    Doctor["Doctor"] --> Support["Role-based support centers"]
    Clinic["Clinic Staff"] --> Support
    Brand["Brand Manager"] --> Support
    Rep["Field Rep"] --> Support
    Patient["Patient"] --> Support
    Support --> PM["Project Manager dashboard"]
    PM --> Ticketing["Ticket queue"]
    Ticketing --> Owner["Department owner / support lead"]
    PM --> Performance["Campaign performance"]
```

        ## Roles

        - **Project Manager**: Runs the PM dashboard, reviews unresolved support issues, creates tickets, and monitors campaign performance.
- **Department Owner / Support Lead**: Works the scoped ticket queue, changes status, delegates work, and records notes.
- **Doctor**: Uses page-wise FAQs, widgets, and the guided assistant to self-serve or escalate issues.
- **Clinic Staff**: Uses the clinic-staff support center for operational FAQs and escalation into the PM queue.
- **Brand Manager**: Uses the brand-manager support center for authentication, sharing, and reporting support questions.
- **Field Rep**: Uses the field-rep support center for activation, login, onboarding, and sharing issues.
- **Patient**: Uses the patient support center for patient-education and Red Flag Alert access issues.
- **Integration Partner / Trainer**: Uses the FAQ links API and embeddable widgets to publish support flows into other properties.

        ## Workflow Inventory Table

        | ID | Workflow | Section | Primary User | Entry Point | Status |
| --- | --- | --- | --- | --- | --- |
| 01 | Platform Overview and Role Map | Platform Overview | Internal trainer, implementation lead, or any new team member onboarding to the platform. | `http://127.0.0.1:8002/` | Live-verified against the application on 2026-04-11. Older extracted notes mention richer role-specific portals, but the implemented product surface is primarily role-specific support centers plus PM and ticketing dashboards. |
| 02 | Project Manager Dashboard and Triage | Project Management & Operations | Project Manager | `http://127.0.0.1:8002/accounts/dev-login/` | Live-verified against the seeded demo environment on 2026-04-11. |
| 03 | Project Manager Review of “Other” Support Submissions | Project Management & Operations | Project Manager | `http://127.0.0.1:8002/support/doctor/assistant/` | Live-verified against the assistant, PM dashboard, and ticket-creation flow on 2026-04-11. |
| 04 | Project Manager Manual Ticket Creation and Routing | Project Management & Operations | Project Manager | `http://127.0.0.1:8002/ticketing/new/` | Live-verified against the ticket-create form and queue on 2026-04-11. |
| 05 | Department Owner Ticket Execution | Project Management & Operations | Department Owner / Support Lead | `http://127.0.0.1:8002/admin/login/ then http://127.0.0.1:8002/ticketing/` | Live-verified using a staff department-owner account and scoped ticket queue on 2026-04-11. |
| 06 | Project Manager Campaign Performance and Reporting | Project Management & Operations | Project Manager | `http://127.0.0.1:8002/app/performance/` | Live-verified using the performance dashboard and reporting contract page on 2026-04-11. |
| 07 | Doctor Self-Service Support | Self-Service Support | Doctor | `http://127.0.0.1:8002/support/doctor/` | Live-verified against the doctor landing page, FAQ page, assistant, and widget on 2026-04-11. |
| 08 | Clinic Staff Self-Service Support | Self-Service Support | Clinic Staff | `http://127.0.0.1:8002/support/clinic_staff/` | Live-verified against the clinic-staff role page and page-wise FAQ flow on 2026-04-11. |
| 09 | Brand Manager Self-Service Support | Self-Service Support | Brand Manager | `http://127.0.0.1:8002/support/brand_manager/` | Live-verified against the brand-manager support center on 2026-04-11. Known mismatch noted against older extracted documentation. |
| 10 | Field Rep Self-Service Support | Self-Service Support | Field Rep | `http://127.0.0.1:8002/support/field_rep/` | Live-verified against the field-rep support center, FAQ page, and widget on 2026-04-11. |
| 11 | Patient Self-Service Support | Self-Service Support | Patient | `http://127.0.0.1:8002/support/patient/` | Live-verified against the patient support center, page view, and widget on 2026-04-11. |
| 12 | Support Widget Integration | Technical Enablement | Implementation partner, trainer, or technical owner embedding support content into another property. | `http://127.0.0.1:8002/support/api/doctor/faq-links/` | Live-verified against the FAQ links API and rendered widgets on 2026-04-11. |

        ## Platform Overview
- `01` [Platform Overview and Role Map](01-platform-overview-and-role-map.md) | Primary user: Internal trainer, implementation lead, or any new team member onboarding to the platform.

## Project Management & Operations
- `02` [Project Manager Dashboard and Triage](02-project-manager-dashboard-and-triage.md) | Primary user: Project Manager
- `03` [Project Manager Review of “Other” Support Submissions](03-project-manager-review-other-submissions.md) | Primary user: Project Manager
- `04` [Project Manager Manual Ticket Creation and Routing](04-project-manager-manual-ticket-creation.md) | Primary user: Project Manager
- `05` [Department Owner Ticket Execution](05-department-owner-ticket-execution.md) | Primary user: Department Owner / Support Lead
- `06` [Project Manager Campaign Performance and Reporting](06-project-manager-campaign-performance-and-reporting.md) | Primary user: Project Manager

## Self-Service Support
- `07` [Doctor Self-Service Support](07-doctor-self-service-support.md) | Primary user: Doctor
- `08` [Clinic Staff Self-Service Support](08-clinic-staff-self-service-support.md) | Primary user: Clinic Staff
- `09` [Brand Manager Self-Service Support](09-brand-manager-self-service-support.md) | Primary user: Brand Manager
- `10` [Field Rep Self-Service Support](10-field-rep-self-service-support.md) | Primary user: Field Rep
- `11` [Patient Self-Service Support](11-patient-self-service-support.md) | Primary user: Patient

## Technical Enablement
- `12` [Support Widget Integration](12-support-widget-integration.md) | Primary user: Implementation partner, trainer, or technical owner embedding support content into another property.

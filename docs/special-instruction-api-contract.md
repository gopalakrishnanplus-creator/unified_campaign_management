# Special Instruction API Contract

This is an analysis-only contract for the RFA Special Instruction approval workflow. It is intentionally separate from `apps/reporting/contracts.py` because Special Instruction approval creates operational PM review tickets; it is not a campaign-performance reporting feed.

## Subsystem Contract Definitions

| Contract | Direction | Method | Endpoint | Purpose |
| --- | --- | --- | --- | --- |
| PM webhook intake | RFA -> PM | POST | `/app/special-instructions/webhook/` | Create or update the PM review ticket automatically when RFA receives a doctor upload |
| RFA ticket payload | PM -> RFA | GET | `/internal/special-instructions/<doctor_id>/ticket/` | Fetch full review context for manual reload or retry recovery |
| RFA document download | PM -> RFA | GET | `/internal/special-instructions/<doctor_id>/download/` | Download the uploaded document through the PM proxy action |
| RFA document approve | PM -> RFA | POST | `/internal/special-instructions/<doctor_id>/approve/` | Approve the document and update the RFA Special Instruction status |

## Runtime Hosts

| System | Base URL |
| --- | --- |
| RFA production API | `https://red-flag-alerts.co.in` |
| PM dashboard webhook | Use the active PM dashboard domain with path `/app/special-instructions/webhook/` |

Both `/app/special-instructions/webhook/` and `/app/special-instructions/webhook` are accepted on the PM side.

## Auth

Use this header for all RFA-facing calls and RFA-to-PM webhook calls:

```http
Authorization: Bearer <SPECIAL_INSTRUCTION_PM_API_TOKEN>
```

Fallback header, only when `Authorization` cannot be sent:

```http
X-Special-Instruction-Token: <SPECIAL_INSTRUCTION_PM_API_TOKEN>
```

## PM Webhook Intake

```http
POST /app/special-instructions/webhook/
Content-Type: application/json
Authorization: Bearer <SPECIAL_INSTRUCTION_PM_API_TOKEN>
```

Preferred request body is the full RFA ticket payload:

```json
{
  "ok": true,
  "ticket": {
    "doctor": {
      "id": "DOC401",
      "name": "Dr. Portal Doctor",
      "email": "portal@example.com"
    },
    "clinic": {
      "name": "Clinic Portal",
      "phone": "9876543210"
    },
    "associated_campaign": {
      "campaign_id": "campaign-uuid",
      "campaign_name": "Growth Campaign",
      "brand_name": "Pedia",
      "field_rep": {
        "id": "FR001",
        "internal_id": 12,
        "name": "Rep One"
      }
    },
    "assigned_field_rep": {
      "id": "FR001",
      "internal_id": 12,
      "name": "Rep One"
    },
    "special_instruction": {
      "current_status": "Document in process",
      "status_code": "in_process",
      "uploaded_at": "2026-05-06T10:30:00+00:00",
      "download_url": "https://red-flag-alerts.co.in/internal/special-instructions/DOC401/download/",
      "approve_url": "https://red-flag-alerts.co.in/internal/special-instructions/DOC401/approve/"
    }
  }
}
```

Accepted retry/recovery shapes:

| Shape | Notes |
| --- | --- |
| Full payload under `ticket` | Preferred; avoids an additional PM-to-RFA fetch |
| Full payload under `data`, `payload`, `request`, `ticket_payload`, `ticketPayload`, or `body` | Useful when webhook providers wrap the body |
| JSON body with `doctor_id` and optional `campaign_id` | PM fetches the full payload from RFA |
| Form-encoded `doctor_id` and optional `campaign_id` | Supported for delivery retries |

Successful PM response:

```json
{
  "success": true,
  "review_id": 123,
  "ticket_number": "TKT-12345678",
  "ticket_url": "https://<pm-domain>/ticketing/123/",
  "doctor_id": "DOC401",
  "status": "in_process",
  "assignee_email": "product-owner@example.com"
}
```

PM side effects:

| Side effect | Rule |
| --- | --- |
| Idempotency key | `doctor_id:campaign_id`; if `campaign_id` is absent, `doctor_id:` |
| Ticket type | `Special Instruction Approval` |
| Source system | `red_flag_alert` |
| Department | `PRODUCT` by default, configurable with `SPECIAL_INSTRUCTION_REVIEW_DEPARTMENT_CODE` |
| Assignee | Department default recipient from PM database |
| Email | Sent immediately to the assigned reviewer with Download and Approve buttons |
| External mirroring | Disabled for Special Instruction tickets |

## PM Webhook Field Contract

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ticket.doctor.id` | string | Yes | RFA doctor identifier used as the primary review key |
| `ticket.doctor.name` | string | No | Doctor display name shown in PM and email |
| `ticket.doctor.email` | email | No | Doctor email copied into review metadata |
| `ticket.clinic.name` | string | No | Clinic display name shown in PM and email |
| `ticket.clinic.phone` | string | No | Clinic phone copied into ticket requester details |
| `ticket.associated_campaign.campaign_id` | string | No | RFA campaign UUID; combines with doctor id for idempotency |
| `ticket.associated_campaign.campaign_name` | string | No | Campaign name shown in PM and email |
| `ticket.associated_campaign.brand_name` | string | No | Brand name shown in PM and email |
| `ticket.associated_campaign.field_rep.id` | string | No | Campaign field representative external id |
| `ticket.associated_campaign.field_rep.internal_id` | integer | No | Campaign field representative internal RFA id |
| `ticket.associated_campaign.field_rep.name` | string | No | Campaign field representative display name |
| `ticket.assigned_field_rep.id` | string | No | Assigned field representative external id |
| `ticket.assigned_field_rep.internal_id` | integer | No | Assigned field representative internal RFA id |
| `ticket.assigned_field_rep.name` | string | No | Assigned field representative display name |
| `ticket.special_instruction.current_status` | string | No | Human-readable RFA status, for example `Document in process` |
| `ticket.special_instruction.status_code` | string | No | Machine status code, for example `in_process` or `uploaded` |
| `ticket.special_instruction.uploaded_at` | datetime | No | Upload timestamp from RFA, preferably ISO 8601 with timezone |
| `ticket.special_instruction.download_url` | URL | No | RFA download endpoint; host must match the configured RFA host |
| `ticket.special_instruction.approve_url` | URL | No | RFA approval endpoint; host must match the configured RFA host |

## RFA Ticket Payload API

```http
GET /internal/special-instructions/<doctor_id>/ticket/
GET /internal/special-instructions/<doctor_id>/ticket/?campaign_id=<campaign_uuid>
Authorization: Bearer <SPECIAL_INSTRUCTION_PM_API_TOKEN>
```

Response root:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ok` | boolean | Yes | True when RFA returned a usable ticket payload |
| `ticket` | object | Yes | Full Special Instruction ticket payload consumed by PM |

Known side effect: this RFA endpoint triggers Product Team email notification in RFA, so PM should prefer the webhook full payload for normal operation.

## RFA Download API

```http
GET /internal/special-instructions/<doctor_id>/download/
Authorization: Bearer <SPECIAL_INSTRUCTION_PM_API_TOKEN>
```

Expected response is a binary attachment. The S3 object URL must never be exposed to PM users; PM proxies this download through the local ticket action.

## RFA Approve API

```http
POST /internal/special-instructions/<doctor_id>/approve/
Authorization: Bearer <SPECIAL_INSTRUCTION_PM_API_TOKEN>
```

Expected side effects:

| System | Change |
| --- | --- |
| RFA | `special_instructions_present` changes from `N` to `Y` |
| RFA | Current status changes from `Document in process` to `Document uploaded` |
| PM | Local review stores `approved_at`, `approved_by`, and the RFA response |
| PM | Local ticket status changes to `Completed` |

Optional response fields consumed by PM:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ok` | boolean | No | RFA success flag |
| `ticket.special_instruction.current_status` | string | No | Updated human-readable RFA status |
| `ticket.special_instruction.status_code` | string | No | Updated machine status code |

## Workflow States

| State | Status code | Owner | Meaning |
| --- | --- | --- | --- |
| `Document in process` | `in_process` | RFA | Doctor uploaded a Special Instruction document and PM review is pending |
| `Assigned` | `pm_assigned` | PM | PM created or updated the review ticket and assigned it to the Product department default recipient |
| `Document uploaded` | `uploaded` | RFA | PM reviewer approved the document and RFA persisted the approved flag |

## Operational Constraints

- This contract is for analysis and validation only; it is not mounted into `/reporting/api/contracts/`.
- The PM runtime validates RFA action URLs against the configured RFA host.
- The PM webhook rejects requests without the shared token.
- PM tickets are keyed idempotently, so replaying a webhook updates the same review instead of creating duplicate tickets.
- The normal flow should not require PM users to type a doctor id. Manual reload exists only for missed webhook delivery or recovery.

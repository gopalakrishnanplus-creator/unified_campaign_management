# FAQ Support Widget Integration

Use these endpoints when another system needs to open page-specific FAQ support in a bottom-right chat widget.

## 1. Get all available links for a role

Call:

- `/support/api/doctor/faq-links/`
- `/support/api/clinic_staff/faq-links/`
- `/support/api/brand_manager/faq-links/`
- `/support/api/field_rep/faq-links/`
- `/support/api/patient/faq-links/`

Each response returns one record per `super category + category` combination. Every record includes:

- `page_url`: the FAQ page for the super category
- `widget_url`: the standalone widget page
- `embed_url`: the iframe-safe widget URL for bottom-right embedding
- `api_url`: the JSON payload for that exact combination

## 2. Embed a specific combination

For a single combination, use:

- `/support/<role>/faq/<super_slug>/<category_slug>/widget/?embed=1`

Example pattern:

- `/support/brand_manager/faq/access-login/authentication/widget/?embed=1`

This URL is safe to place inside an iframe and is intended for the support launcher in another system.

## 3. Fetch the JSON payload directly

For a single combination, use:

- `/support/api/<role>/<super_slug>/<category_slug>/`

Example pattern:

- `/support/api/brand_manager/access-login/authentication/`

The JSON contains only the FAQs for that combination and includes:

- `super_category`
- `category`
- `faq_count`
- `faqs`
- `page_url`
- `widget_url`
- `embed_url`
- `api_url`

## 4. Expected embedding behavior

The external system should:

1. identify the current `role`, `super_slug`, and `category_slug`
2. use the corresponding `embed_url`
3. open that URL in a fixed bottom-right iframe or chat drawer

The widget is FAQ-only right now. It shows radio-button questions for that exact combination, displays answers inline, and lets the user continue until they click `Issue Resolved`.

# Campaign Management Testing Guide

Use this checklist to verify the full system locally.

## 1. Start the app

```bash
cd /Users/inditech-tech/Documents/CampaignManagementSystem/unified_campaign_management
source .venv/bin/activate
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver 127.0.0.1:8001
```

Open `http://127.0.0.1:8001/`.

## 2. Verify public pages

Check that each page loads without an exception:

- `/`
- `/support/doctor/`
- `/support/clinic_staff/`
- `/support/brand_manager/`
- `/support/field_rep/`
- `/support/patient/`
- `/accounts/login/?next=/app/`

Expected result:

- each page returns `200`
- support landing pages show the FAQ super-category cards and the `FAQ links API` button
- login page renders normally without template errors

## 3. Verify local PM access

Open:

- `/accounts/dev-login/`

Expected result:

- you are logged in as `campaignpm@inditech.co.in`
- you are redirected to `/app/`

## 4. Verify the PM dashboard

Open:

- `/app/`

Check:

- support cards render
- screening or monitoring data renders
- patient education data renders
- adoption by clinics renders from live APIs
- in-clinic sharing renders
- external growth renders from the WordPress helper source
- source cards appear under Campaign Performance Data

Expected result:

- no 500 errors
- tables are populated or show graceful empty states
- warning notes appear only when a live source cannot provide an exact split or cannot be reached

## 5. Verify reporting contracts and live feeds

Open:

- `/reporting/contracts/`
- `/reporting/api/contracts/`
- `/reporting/api/red_flag_alert/`
- `/reporting/api/in_clinic/`
- `/reporting/api/patient_education/`

Expected result:

- contracts page shows live endpoint references
- JSON feeds return valid payloads
- payload includes `source`
- when campaign mapping is unavailable, the payload still returns gracefully with a notice instead of crashing

## 6. Verify FAQ super-category pages

From one support landing page, for example `/support/brand_manager/`:

- open one super category such as `Access Login`
- confirm the page URL changes to `/support/brand_manager/faq/<super_slug>/`
- review the category cards shown on that page

Expected result:

- each super category has its own page
- each category card shows a question count
- each category card shows `Open FAQ support`, `Standalone widget`, `Config API`, and `Embed URL`

## 7. Verify the page-specific FAQ widget

From a super-category page, for example:

- `/support/brand_manager/faq/access-login/`
- click `Open FAQ support` on one category card

Expected result:

- a support dock opens on the same page in the bottom-right corner
- the widget is FAQ-only
- the radio-button list includes only FAQs for that exact super-category and category combination
- the widget does not include unrelated questions from other combinations

Continue the flow:

- select one radio-button question
- click `Show Answer`
- select a different question
- click `Show Answer` again
- click `Issue Resolved`

Expected result:

- each selected question is appended into the transcript
- the corresponding answer is shown immediately
- the user can continue asking more FAQ questions without restarting
- `Issue Resolved` ends the session cleanly

## 8. Verify FAQ APIs for external embedding

Open:

- `/support/api/brand_manager/faq-links/`
- one returned `api_url` from that payload
- one returned `embed_url` from that payload in a browser tab

Expected result:

- the links API returns JSON with one entry per super-category and category combination
- every entry includes `page_url`, `widget_url`, `embed_url`, and `api_url`
- the combination API returns only the FAQ questions for that specific combination
- the embed URL loads without an `X-Frame-Options` block so it can be placed in another system as a bottom-right iframe

## 9. Verify free-text support request

From a landing page such as `/support/brand_manager/`:

- fill the free-text support form
- submit it

Expected result:

- the request is saved
- if a default department exists, a ticket is created
- the success page confirms the request was logged

## 10. Verify ticketing workflow

Open:

- `/ticketing/`

Pick a ticket and verify:

- add a note
- upload an attachment
- change status
- delegate to another user if available

Expected result:

- changes persist
- routing events appear
- status updates reflect immediately

## 11. Verify imported FAQs and ticket cases

In admin:

- open `/admin/support_center/supportitem/`

Check:

- imported rows exist for `Red Flag Alert`, `In-clinic`, and `Patient Education`
- `knowledge_type`, `source_flow`, and `ticket_required` values are populated

Expected result:

- FAQ and ticket-case imports are visible and searchable

## 12. Verify automated checks

Run:

```bash
cd /Users/inditech-tech/Documents/CampaignManagementSystem/unified_campaign_management
source .venv/bin/activate
python manage.py check
python manage.py test
```

Expected result:

- `System check identified no issues`
- test suite completes with `OK`

## 13. Verify live-source troubleshooting

If dashboard numbers look wrong:

1. Check `/reporting/api/red_flag_alert/`, `/reporting/api/in_clinic/`, and `/reporting/api/patient_education/` first.
2. Confirm `.env` has the expected `WORDPRESS_GROWTH_WEBINAR_FILTERS` and `WORDPRESS_CERTIFICATE_COURSE_IDS`.
3. Refresh `/app/` and look for any warning notice explaining a source mismatch or fallback.
4. If the source data itself does not expose doctor-level identity, the app will show the best available split and a warning instead of failing.

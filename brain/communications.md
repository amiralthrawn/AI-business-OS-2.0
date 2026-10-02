# Communications (V2 / V2.1)

Emails, website inquiries and appointments are `Communication` objects linked
to what they concern (customer, supplier, contact, quote, order, candidate,
compliance task) through the object graph.

## Assistance — prepares, never sends

```
Analyse (rules; LLM summary only if configured) → suggested links & actions
AI draft (deterministic template from the linked object's real data;
          LLM may only rephrase, never add facts)
→ human edits → submit → V1 HITL Task (pending_action = send_email)
→ approval by an allowed role (domain-scoped) → send through the EmailProvider
```

The configured provider is the **Mock** provider: "sent" means recorded, not
delivered; the UI says "envoi simulé". Sending a quote/PO moves the document
to `sent`; a follow-up reschedules `follow_up_at`; an interview invitation
moves the candidate to `interview_proposed`.

Purposes: reply, follow_up, send_quote, order_confirmation, rfq_price /
availability / lead_time / terms / documents, send_purchase_order, brochure,
nda, interview_invite, expert_request, generic.

## Follow-ups

Computed when read (`GET /follow-ups`): sent quotes past their follow-up date,
supplier quotes still awaited, inbound messages unanswered. **No scheduler
sends anything** (#33).

## V2.1 additions

- Intent "Candidature" → "Créer la fiche candidat" (see `brain/people.md`).
- "Site web & SEO" tab (see `brain/website_intelligence.md`).
- Simulated demo messages are labelled "message simulé".

## V2.2 purposes

`credit_note_offer` (propose a credit note: sending it marks the credit note
"submitted"), `supplier_claim` (claim / credit note request to a supplier),
`payment_reminder` (overdue invoice). Sending `order_confirmation` marks the
order "transmitted" -- never "acknowledged", which only the customer can do.
See `brain/billing.md`.

## Limits

No real Gmail/Outlook, no threading beyond `thread_key`, no attachments
upload, social networks are shown as "non configuré".

## Boîtes fonctionnelles (UX pass)

Tab "Boîtes" (default) — `GET /communications/mailboxes`, `/communications/mailboxes/{key}`
(`app/communications/mailboxes.py`, read-only).

- sales@ (Commercial), orders@ (Commandes), rfq@ (Achats), careers@
  (Recrutement), support@ (Support), contact@ (Général). **The address names
  a role; no real mailbox exists or is connected.**
- A message is *classified* by explicit rules, in order: linked candidate /
  "candidature" intent → careers; linked supplier → rfq; agency proposal →
  contact; incident words (whole words) → support; linked customer + order /
  delivery / invoice intent → orders; linked customer or quote request →
  sales; otherwise contact. Each row shows the rule that placed it
  ("Classé : …"). Calendar events and internal notes are not classified.
- Status per box: **Connectée** only with a non-mock email provider that
  delivered to the address (never today), **Démonstration** when its
  messages come from demo providers or seeds, **Non configurée** when empty.
- "Sans réponse" = inbound message with no *sent* answer on the same thread or
  from the same contact (a draft is not an answer). Opening a message reuses
  the existing pane: related objects, AI analysis, AI draft → edit → submit
  (HITL `send_email`).

## Performance des relances (UX pass)

`GET /communications/performance`, shown in "Relances & suivi". Stages are
counted separately: prepared (draft / pending validation / rejected),
validated (executed `send_email` approvals), sent, replies received (inbound
on the same thread/contact after the send), orders linked (customer or
purchase order `derived_from` a document the message concerns). Reply rate
and delays only from **3 sent messages**; otherwise "Données insuffisantes".

## Performance des campagnes (UX pass)

`GET /communications/campaigns`, shown in "Canaux & campagnes". Campaigns
exist only as messages (reports, agency proposals, team ideas); a campaign
is named from "Campagne X". The view separates **declared** (a figure written
in a report), **observed** (inbound requests counted in the base for the
campaign month vs the previous one) and **not available** (budget, attributed
prospects/opportunities/sales, ROI, cost per prospect — no budget recorded,
no link between requests and a campaign). Team feedback = messages and tasks
mentioning the campaign. Recommendations are explicit rules showing the data
used and the limit; any change goes through a draft or a task to validate —
nothing is launched or modified automatically. The email widget now says
"Démonstration" (it was "Gmail — Connecté (démonstration)").

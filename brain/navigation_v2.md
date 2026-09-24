# Navigation (V2 / V2.1)

## Rule

Top-level entries are **workspaces built around business objects**, not one
entry per object type. Everything else is reached by sub-tabs or, first of
all, by **contextual links** from related objects. Every object page answers:
where am I (breadcrumb), what is it (header), what is it linked to (related
objects), what can I do (actions, filtered by role), where next (every
related object is a link).

## Sidebar

| Group | Entry | Sub-tabs | Visible with |
|---|---|---|---|
| Accueil | Centre de contrôle | — (+ "Opérations en cours", "Vue dirigeant") | all |
| Opérations | Ventes | Vue d'ensemble · Affaires · Devis · Commandes · Relances · Clients | view:sales |
| | Achats | Vue d'ensemble · Demandes d'achat · Devis fournisseurs · Commandes & réceptions · Factures · Relances · Fournisseurs | view:procurement |
| | Catalogue & stock | Produits · Stock | view:catalog |
| | Communications | Réception · Envoyés · Brouillons & validation · Relances · Contacts · Canaux & campagnes · Site web & SEO | view:communications |
| | Équipe (V2.1) | Employés · Compétences & recrutement | view:people |
| Pilotage | Finance | (marges par commande, écritures) | view:finance |
| | Intelligence | Risques · Opportunités · Décisions | view:intelligence |
| | Direction (V2.1) | Trésorerie · Comptes · Capital & valorisation | view:treasury or view:ownership |
| Actions | Actions & validations | Tâches & validations · Activité · Conformité & juridique (V2.1) | view:actions |
| | Demander à l'IA | — | action:ask_ai |

## Why

- **Tabs** only for lists a user browses as a whole in a workspace (quotes, orders, inbox).
- **Contextual only**: a commercial document (`/documents/[id]`), a customer, a supplier, a product, an employee, a contact — reached from lists and related-object links.
- **Merged**: Risks/Opportunities/Decisions → "Intelligence"; Tasks/Activity (+ Compliance) → "Actions"; the V1 "Données" hub → removed (its lists moved to their workspaces; old URLs redirect).
- **Sections, not pages**: sourcing lives on the purchase request, the benchmark on the purchase request and product, the margin on sales documents, website SEO as a Communications tab, compliance as an Actions tab.
- **Only two new entries in V2.1** (Équipe, Direction), because people and director finance are real object families with their own lists; everything else is a section or tab.

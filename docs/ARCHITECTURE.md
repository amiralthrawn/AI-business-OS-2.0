# AI Business OS — Architecture validée

Référence courte des décisions prises avant implémentation. Ne remplace pas la discussion complète, sert de rappel pendant le développement.

## Principe général

Modular monolith en couches, connectées par un bus d'événements interne plutôt que par des appels en cascade :

```
DATA CORE
   ↓
HISTORICAL CONTEXT + BUSINESS CONFIGURATION → BUSINESS CONTEXT
   ↓
BUSINESS → INTELLIGENCE (monitoring) → ACTIONS → HOME
                ↕ Business Events (Event Bus)
AI : accès transversal en lecture, organisée par Capabilities, cross-domaine, pas par domaine unique
```

Home n'a pas de stockage propre : c'est un agrégateur en lecture (modèle hybride, pas de CQRS complet) qui interroge directement les services internes de Business/Intelligence/Actions.

**Business Context** est la couche de configuration qui permet à l'OS de raisonner sur *cette* entreprise plutôt qu'une entreprise générique (secteur, taille, pays, modèle économique, domaines surveillés, objectifs déclarés, baselines déclarées) — éditable via `GET`/`PATCH /business-context`. `suggest_configuration_changes` détecte des tendances dans les décisions humaines (Event Log) et **propose** des changements de configuration (`GET /business-context/suggestions`) sans jamais les appliquer automatiquement.

**Baseline → Significance → Business State Snapshot** forment la couche qui permet à l'IA de savoir ce qui compte sans charger toute la Data Core dans le LLM :
- `app/core/baseline.py` : ce qu'est "la normale" pour une métrique — observée (historique réel), déclarée (objectif de l'entreprise, toujours prioritaire sur l'observé) ou générique (repli, faible confiance). Les trois ne sont jamais confondus.
- `app/core/significance.py` : évalue une déviation via plusieurs dimensions indépendantes (deviation, impact, urgency, persistence, recurrence, correlation, strategic_relevance, confidence) — jamais réduit à un score unique.
- `app/snapshot/service.py` : vue dérivée compacte de l'état actuel (pas une seconde Data Core, pas de cache persistant), annotant les Risks/Opportunities déjà détectés avec Baseline+Significance.
- Câblage Orchestrator : une question ciblée utilise les capabilities directement (inchangé) ; une question large ("qu'est-ce qui mérite mon attention ?") consulte d'abord le Snapshot puis appelle automatiquement les capabilities ciblées sur la zone la plus significative.

Voir `brain/business_context.md` et `brain/business_state.md` pour le détail et les limites assumées (seuils de sévérité pas encore unifiés, pas de baseline calculée persistée, pas de scan proactif de toutes les entités).

**Business Observation Engine** est la première couche générique de découverte transverse — elle ne remplace pas les règles Intelligence existantes, elle les précède :
```
DATA CORE → OBSERVABLE REGISTRY → OBSERVATION ENGINE → BUSINESS EVENTS (ObservationDetected) → SIGNIFICANCE + BUSINESS CONTEXT → BUSINESS STATE SNAPSHOT
```
- `app/observation/registry.py` : `Observable` = un signal nommé, pluggable (métrique + type d'entité + fonction de Baseline réutilisée + seuils d'impact) — ajouter un Observable n'exige jamais de modifier le moteur.
- `app/observation/engine.py` : calcule chaque Observable pour chaque entité, compare via Baseline/Significance (réutilisés, jamais dupliqués), corrèle les anomalies liées entre domaines (ex. Produit ↔ son propre Supplier), publie un `BusinessEvent` par phénomène détecté. Idempotent : un sweep répété ne republie jamais un même (observable, entité).
- Distinction stricte maintenue : Observable (ce qu'on mesure) ≠ Observation (ce qu'on constate) ≠ Business Event (phénomène significatif) ≠ Risk/Opportunity/Insight (interprétation métier, étape non construite ici).
- Le Snapshot (`app/snapshot/service.py`) intègre désormais aussi les `ObservationDetected` du Event Log pour les entités non déjà couvertes par un Risk/Opportunity ouvert — le mécanisme par lequel le Snapshot devient progressivement alimenté par ce moteur plutôt que uniquement par les règles historiques.
- Déclenchement manuel : `POST /observation/sweep` (pas de scheduler, même choix que `app.intelligence.monitoring`).

Voir `brain/observation_engine.md` pour le détail et les limites assumées (pas de promotion Business Event → Risk/Opportunity, corrélation limitée à un seul lien réel, pas de LLM dans la détection).

**Business Event Interpretation Layer** répond à « qu'est-ce que cet événement signifie pour cette entreprise ? », juste au-dessus de l'Observation Engine :
```
BUSINESS EVENT → CONTEXT ASSEMBLY (Business Context + Baseline/Significance + Snapshot + capabilities ciblées) → LLM → INTERPRETATION (risk|opportunity|insight|observation)
```
- `app/interpretation/context.py` : assemble un contexte compact (jamais toute la Data Core) en réutilisant `AIOrchestrator._dispatch_targeted_capabilities` pour consulter, si besoin, les mêmes capabilities qu'une question humaine ciblée utiliserait.
- `app/interpretation/engine.py` : la classification (risk/opportunity/insight/observation) est une règle déterministe basée sur la confidence du Baseline et la direction de la déviation (jamais décidée par le LLM, jamais une règle par type d'événement) — le LLM ne produit que l'explication en langage naturel. `Ne force jamais un événement à devenir Risk/Opportunity` : confidence `insufficient`→`observation`, `low`→`insight`, `medium`/`high`→`risk`/`opportunity` selon la direction.
- Depuis le Step 17, cette couche ne propose plus de Task elle-même (voir Decision Intelligence ci-dessous) : elle publie uniquement `EventInterpreted`.
- Déclenchement manuel : `POST /interpretation/sweep`.

Voir `brain/interpretation_engine.md` pour le détail, la démonstration (Risk/Opportunity/Insight sur les données seed) et les limites assumées (pas de ré-évaluation automatique d'un Insight dans le temps, une seule Interpretation par cluster corrélé, pas de nouvelle UI frontend).

**Decision Intelligence** répond à « quelles décisions sont envisageables ? », juste au-dessus de l'Interpretation Layer :
```
INTERPRETATION → DECISION (options + trade-offs + recommendation + confidence) → ACTION PROPOSAL (si pertinent) → HUMAN VALIDATION
```
- `app/decision/engine.py` : `build_decision` réutilise `app.interpretation.context.assemble_context` (même contexte que l'Interpretation, enrichi du résultat de l'Interpretation elle-même) — aucune deuxième assemblée de contexte parallèle. Les options sont un petit catalogue générique par (type, domaine) — finance/procurement/sales, 3 options chacun (2 proactives + 1 passive) — pas un nouvel agent, pas une règle par événement spécifique.
- La recommandation combine déterministiquement les deux options proactives (jamais un choix du LLM, même raison que `classify()` dans l'Interpretation Layer) ; le LLM ne produit que le raisonnement (`reasoning`) expliquant ce choix, jamais une classification ni une exécution.
- Contexte insuffisant (Interpretation `insight`/`observation`) → `options=[]`, `recommendation.chosen_option=None`, mais l'IA explique quand même pourquoi elle ne recommande rien — "Ne force jamais".
- Action Proposal : réutilise tel quel `ActionsService.propose_task` (Human-in-the-Loop existant) uniquement quand `chosen_option` n'est pas `None`, et seulement si l'entité n'est pas déjà couverte par un Risk/Opportunity ouvert existant — jamais de duplication, jamais d'exécution automatique. Une Decision peut exister sans Action ; une Recommendation peut exister sans qu'une Action soit proposée.
- Le Snapshot (`app/snapshot/service.py`) intègre les `DecisionProposed` : une zone "decision" (la plus riche : options, trade-offs, recommandation) remplace la zone "interpretation" pour une même entité, sans jamais dupliquer une zone risk/opportunity déjà existante — intégration additive et rétrocompatible, même mécanisme que la couche précédente.
- Déclenchement manuel : `POST /decision/sweep`.

Voir `brain/decision_intelligence.md` pour le détail, la démonstration (Risk/Opportunity/contexte insuffisant sur les données seed) et les limites assumées (pas de moteur quantitatif, catalogue d'options limité à 3 domaines, pas de nouvelle UI frontend).

**AI Orchestrator — raisonnement cross-domaine sans entité nommée (Step 18)** : le comportement cross-domaine existait déjà depuis l'étape 12 pour une question nommant une entité (« marge » → finance+procurement+sales, capabilities agrégées) ; ce step comble le cas où la question ne nomme aucune entité du tout :
```
Question ciblée (entité nommée)            → capabilities ciblées de(s) agent(s) → réponse (inchangé, step 12)
Question cross-domaine (aucune entité)     → Business State Snapshot → zones significatives dans le(s) domaine(s) concerné(s) → capabilities ciblées par zone → réponse synthétique
Question large ("qu'est-ce qui mérite mon attention ?") → Snapshot d'abord → zone la plus significative → capabilities ciblées → synthèse (inchangé, step 14)
```
- `app/ai/orchestrator/service.py` : `_handle_cross_domain_request` (nouveau) — appelé uniquement quand aucun Supplier/Product/Customer n'a pu être résolu depuis la question. Consulte `get_business_state_snapshot`, filtre `material_areas` par domaine(s) matché(s) par les mots-clés de la question, puis appelle `_dispatch_targeted_capabilities` (réutilisé tel quel) pour chaque zone significative trouvée.
- Jamais de scan de toute la Data Core : seules les entités déjà signalées comme significatives par le Snapshot sont consultées. Aucune zone significative dans le(s) domaine(s) concerné(s) → `OrchestratorError` explicite (contexte insuffisant), jamais une réponse devinée.
- Chaque zone reçoit son propre dict de contexte (évite qu'un même nom de capability appelé pour deux entités différentes n'écrase le résultat de la première) puis est fusionnée sous une clé namespacée (`"{domaine}: {titre}"`) dans le contexte final — `_call`/`_dispatch_targeted_capabilities` eux-mêmes restent inchangés.
- Aucun nouvel agent par domaine, aucune nouvelle capability : uniquement une nouvelle façon de choisir QUELLES capabilities appeler quand la question ne fournit pas d'entité explicite.

Voir `brain/ai_orchestrator_cross_domain.md` pour le détail et un exemple réel (« Pourquoi notre marge baisse ? » sur les données seed, agrégeant finance/procurement/sales en une seule réponse).

**Home / Command Center (Step 19)** : Home devient la couche de synthèse réelle du Business OS — elle ne recalcule jamais rien, elle relit ce que les couches précédentes ont déjà produit :
```
DATA / EVENTS → OBSERVATION/INTERPRETATION/DECISION/RISK/OPPORTUNITY → BUSINESS STATE SNAPSHOT → HOME / COMMAND CENTER
```
- `GET /home` **est** l'endpoint Command Center (la méthode s'appelait déjà `get_command_center_view`) — pas de route parallèle `/home/command-center` créée.
- `app/home/service.py` : `get_ai_priorities(company_id)` (nouveau) réutilise `build_snapshot(...).material_areas` tel quel — kind, domain, title, impact/urgency/confidence, et pour les zones interpretation/decision : explanation, recommendation, decision_options. Aucune deuxième logique de scoring. Lien vers le détail existant (`detail_kind`/`detail_id`) construit par recoupement avec les Risk/Opportunity déjà ouverts, sans ajouter de champ à `SnapshotArea`.
- `get_decisions()` (nouveau) relit directement les `DecisionProposed` du Event Log, sans recalcul — même principe que `get_recent_events()` existant.
- Coexiste avec l'ancienne `get_priorities()` (sévérité seule, Risk/Opportunity uniquement), toujours utilisée telle quelle par la capability `list_priorities` — les deux servent des consommateurs différents avec des formes différentes, volontairement non unifiées (voir `brain/decisions.md`).
- Aucune exécution automatique : Home ne possède aucune méthode d'approbation/exécution ; le frontend réutilise le composant `TaskActionButtons` existant (Human-in-the-Loop inchangé) pour les Tasks `PENDING_VALIDATION`.
- Frontend (`frontend/app/page.tsx`) restructuré en 7 sections (AI Priorities, Risks/Opportunities, Decisions, Actions, Business overview, Ask AI, Recent activity) réutilisant les composants existants ; `components/HomeAskAI.tsx` (nouveau) est une version compacte de la page `/ai/ask-ai` existante, appelant le même endpoint `/ai/ask` — pas un second système de chat.

Voir `brain/home_command_center.md` pour le détail, le contenu réel du Command Center sur les données seed et les limites assumées (pas d'unification des deux méthodes de priorités, pas de detail page pour decision/observation, pas d'état "résolu" pour une Decision).

## Data Core

Entités : Company, Contact, Supplier, Customer, Product, Transaction, Document, Communication, Task, Risk, Opportunity, Event (log).

Relations transversales (Document, Communication, Task, Risk, Opportunity) via `related_entity_type` + `related_entity_id` — compromis de prototype assumé : pas de FK native multi-table, intégrité au niveau applicatif. Évolution future si nécessaire : table `entities` registre unique ou tables de jointure dédiées. Un Supplier/Customer/Product/Transaction n'existe qu'une fois, jamais dupliqué par domaine.

SQLite pour le MVP, SQLAlchemy 2.x + Alembic pour rester migrable vers PostgreSQL. Différences à traiter lors de la migration : mode batch Alembic pour les `ALTER TABLE`, activation des FK (`PRAGMA foreign_keys`), pas de `JSONB`/`TIMESTAMPTZ` natifs, verrou mono-écrivain SQLite vs MVCC Postgres.

**Audit et renforcement du Data Core (Step 20)** : audit complet des relations avant toute modification (voir `brain/data_core.md`) — Supplier↔Product, Supplier↔Transaction, Customer↔Transaction déjà corrects ; seule lacune trouvée : `Product` n'avait pas la relation ORM `transactions` (la colonne FK existait, seule la relationship() manquait, aucune migration nécessaire) — corrigée. Le Event Log reste sans lien structuré vers une entité (chaque type d'événement nomme son sujet avec son propre champ de payload) : lacune réelle mais non bloquante, documentée plutôt que corrigée par une nouvelle colonne qui aurait exigé de toucher chaque publisher existant.
```
Company → Supplier/Customer/Product → Transactions/Documents/Communications → Business Events → Risk/Opportunity/Interpretation/Decision → Actions
```
- `app/core/entity_context.py` : `get_entity_context(session, entity_type, entity_id)` (nouveau) — lecture transverse structurelle uniquement (pas de Baseline/Significance/LLM) reconstituant le contexte direct d'une entité (attributs propres, entités liées, Risks/Opportunities/Tasks ouverts, Documents/Communications, Business Events associés). Ne remplace aucun chemin existant (`_resolve_entity_by_ref`, `assemble_context`, `build_snapshot` restent inchangés) ; disponible pour un futur appelant qui en aurait besoin sans passer par le registre de capabilities IA.
- Aucune modification d'Observation/Interpretation/Decision/Orchestrator/Home — tous re-testés end-to-end contre le Data Core corrigé et produisent exactement les mêmes résultats (`tests/test_data_core_pipeline_regression.py`).

## External Connectivity Layer (Step 21)

Première architecture de connecteurs externes — **Mock Providers uniquement**, aucun service réel connecté (pas d'OAuth, pas de Gmail/Outlook/Google Calendar réels, aucune donnée personnelle) :
```
EXTERNAL SYSTEM → CONNECTOR (Provider) → NORMALIZED EXTERNAL OBJECT → INGESTION/MAPPING → DATA CORE (Communication/Document/Contact) → Business/Intelligence/AI (inchangé, ne lit pas encore ces données)
```
- `app/connectors/{email,calendar,website}/base.py` : une interface ABC par type de connecteur (`EmailProvider`/`CalendarProvider`/`WebsiteProvider`), `mock.py` : l'implémentation Mock réaliste correspondante. Un futur `GmailProvider`/`GoogleCalendarProvider` implémente la même interface — remplacement en un seul appel `registry.register(...)`, aucune couche supérieure à modifier.
- `app/connectors/models.py` : objets normalisés (`ExternalEmail`, `ExternalCalendarEvent`, `WebsiteInquiry`) — jamais les structures propriétaires d'un provider écrites directement dans le Data Core.
- `app/connectors/ingestion.py` : la seule couche qui touche le Data Core — déterministe, idempotente (contrainte unique `(source, external_id)` sur `Communication`/`Document`), sans intelligence métier (ne classe, ne priorise, ne décide rien). Résolution d'identité conservatrice : un email/une demande ne se lie à un Supplier/Customer existant que si le domaine (ou le nom d'entreprise déclaré) matche de façon fiable un nom déjà connu — sinon `Contact` reste `unresolved` (`related_entity_type`/`id` à `None`). Ne crée jamais de Supplier/Customer/Opportunity.
- Nouveaux champs Data Core (migration `6baa8061c9ed`) : `Contact.company_id` (Contact devient enfin utilisé) ; `Communication.source`/`external_id` et `Document.source`/`external_id` (provenance, index unique) — additifs, aucune table existante cassée.
- `app/connectors/registry.py` : `get_connector("email"|"calendar"|"website")`, même pattern que `CapabilityRegistry`.
- Endpoints : `GET /connectors`, `GET /connectors/{type}/status`, `POST /connectors/{type}/sync` (provider → fetch → normalize → ingest → résumé `{fetched, created, updated, skipped}`).
- Au moment du Step 21 : aucune modification d'Observation/Interpretation/Decision/Orchestrator/Home — aucun ne lisait `Communication`/`Contact` ; vérifié par un test dédié tournant la chaîne complète après ingestion des 3 connecteurs sur les données seed, résultats identiques. (Le Step 22 ci-dessous connecte enfin ces données aux moteurs existants.)

Voir `brain/connectors.md` pour le détail, la démonstration réelle (résolution de contacts contre les Supplier/Customer seedés, non-duplication) et les limites assumées (pas de provider réel — l'interprétation IA de ces données arrive au Step 22).

Voir `brain/data_core.md` pour le détail de l'audit, ce qui constitue la source de vérité, ce qui n'est pas stocké dans le Data Core, et les limites assumées.

## External Data Intelligence (Step 22)

Connecte enfin les données externes (Step 21) aux moteurs Intelligence existants — sans en créer de nouveau :
```
External Data (Communication/Document/Contact) → Observation (2 nouveaux Observables génériques) → Business Event (ObservationDetected, inchangé) → Interpretation (inchangée, voit maintenant le contenu du message) → Decision (inchangée) → Action Proposal (2 branches connecteur, basées sur le domaine) → Human Validation → Mock Calendar/Email
```
- Seulement 2 Observables ajoutés (pas les 6 suggérés) : `supplier_unanswered_message_age_days` (SUPPLIER, procurement) et `customer_unanswered_message_age_days` (CUSTOMER, sales) — l'âge en jours du plus ancien message entrant encore sans réponse, via `compute_unanswered_message_age` (nouveau, `app/core/analytics.py`) réutilisant Baseline/Significance à l'identique. Les 4 autres (comptages, conflits calendrier) ne correspondent pas naturellement à la forme "un Observable par entité" et n'ont pas été construits — voir `brain/decisions.md`.
- `Observable` gagne un champ optionnel `extra_context` (callback, `None` par défaut) permettant à un Observable d'attacher un enregistrement concret (le sujet/extrait du message) — surfacé dans `assemble_context` sous `business_event.related_message`. Additif : aucun changement pour les 3 Observables existants.
- **Aucun changement à la classification** (`classify()`), **aucun changement aux catalogues d'options de Decision** (procurement/sales existaient déjà depuis le Step 17) — les 2 nouveaux Observables s'intègrent sans toucher cette logique.
- Une seule vraie extension : `_pending_action_for(decision)` (`app/decision/engine.py`) — quand le signal primaire vient d'un des 2 nouveaux Observables, propose `connector_followup_meeting` (procurement) ou `connector_followup_email` (sales) au lieu du générique `create_task`. `ActionExecutor._run` gagne 2 branches (son propre point d'extension documenté) ; `ActionsService.finalize_connector_followup` (nouveau) réexécute l'action via `app.connectors` après validation humaine, en retrouvant le Contact via le `related_entity_type`/`id` déjà posé sur la Task — aucun nouveau champ, aucun second système d'actions.
- Corrélation cross-domaine (Step 15, inchangée) : le vrai email de renégociation de Northline Steel se corrèle automatiquement avec la dégradation de marge de Steel Frame Assembly (son propre produit) — démontré en conditions réelles, zéro nouveau code de corrélation.
- Cas B (prospect inconnu) : aucune Observation n'est produite pour un contact non résolu — absence correcte, pas un bug (pas de ligne Supplier/Customer à laquelle rattacher une Significance).
- Cas C (calendar) : aucun nouveau code — `get_entity_context` (Step 20) exposait déjà les Communications d'origine calendrier.

Voir `brain/external_data_intelligence.md` pour le détail complet, la démonstration réelle (boucle complète Coastal Metal Supply → Decision → Task PENDING_VALIDATION → approbation → vrai événement Mock Calendar créé) et les limites assumées.

## Business Domains (Step 23B)

L'audit Step 23 avait constaté que Finance/Procurement/Sales n'avaient aucun frontend fonctionnel alors que le backend contenait déjà tout le nécessaire. Step 23B rend ces domaines réels, entièrement par composition — aucune nouvelle intelligence, aucune base par domaine :
```
DATA CORE → app/data/service.py (Supplier/Customer/Product/Transaction, list + detail)
          → app/domains/{finance,procurement,sales}/service.py (overview par domaine)
          → Frontend (/data/*, /business/*)
```
- **Read APIs génériques** (`GET /suppliers(/{id})`, `/customers(/{id})`, `/products(/{id})`, `/transactions(/{id})`) : `app/data/service.py` compose `get_entity_context` (Step 20), les fonctions de `app.core.analytics` (delivery performance, revenue trend, margin trend, unanswered message age) et `HomeService.get_ai_priorities` — aucun de ces trois n'est recalculé, seulement réexposé par entité.
- **Overviews par domaine** (`GET /finance/overview`, `/procurement/overview`, `/sales/overview`) réutilisent directement `app/data/service.py` (`list_suppliers`, `list_customers`, `list_transactions`) plutôt que de requêter l'ORM une seconde fois. Le seul calcul réellement nouveau est `compute_company_financials` (`app/core/analytics.py`) : les totaux globaux de revenu/coût/marge de l'entreprise — une granularité différente de `compute_margin_trend` (qui reste par produit), partagée entre Finance et Procurement (le "total spend" de Procurement est exactement le `total_costs` de cette même fonction) pour que les deux domaines ne puissent jamais diverger sur ce que l'entreprise a dépensé.
- Le endpoint Procurement a été ajouté au router existant (`app/domains/procurement/router.py`, déjà présent depuis Step 12 pour `POST /supplier-cost-changes`) plutôt que dans un router parallèle. Finance et Sales remplissent les modules `app/domains/{finance,sales}/` qui n'étaient que des placeholders vides depuis Step 12 — aucune nouvelle limite de module.
- **Frontend** : pages `/data/{suppliers,customers,products,transactions}` (liste + détail, sauf transactions qui n'a qu'une liste) et `/business/{finance,procurement,sales}` (vue d'ensemble + intelligence + activité récente), toutes construites sur le même patron (carte de liste → lien vers détail, `IntelligenceCard` partagé). CRM/Marketing/HR/Supply Chain restent des placeholders non fonctionnels, tel que décidé au Step 12.
- **Fix corollaire de l'audit** : `WebsiteInquiry.source` était perdu à l'ingestion — `Communication` gagne un champ additif `channel_detail` (migration `4ba6953c0de3`), rempli par `ingest_website`.
- Sidebar restructurée en groupes HOME / BUSINESS (Finance, Procurement, Sales) / DATA (Suppliers, Customers, Products, Transactions) / INTELLIGENCE (Risks, Opportunities, Decision Intelligence) / ACTIONS (Tasks) / AI (Ask AI) — les domaines non fonctionnels n'y figurent pas.

Voir `brain/business_domains.md` pour le détail complet et `brain/decisions.md` (#24) pour la justification de chaque choix de réutilisation.

## Events — quatre concepts distincts

- **Business Event** : objet immuable (`event_type`, `payload`, `source`, `timestamp`, `correlation_id`, `event_id`).
- **Event Bus** : interface `publish()`/`subscribe()`. Implémentation MVP : in-process, synchrone. Le code métier dépend de l'interface, jamais de l'implémentation.
- **Event Handler / Consumer** : fonction abonnée à un type d'événement, exécute un effet de bord.
- **Event Log** : persistance append-only, réalisée par un handler générique abonné à tous les événements — un consommateur parmi d'autres, pas une fonctionnalité intégrée au bus.

## Business / Intelligence / Actions

Chaque domaine Business publie des événements sur les faits métier significatifs. Intelligence s'abonne, applique des règles déterministes, produit Risk/Opportunity. Actions s'abonne aux événements d'Intelligence, matérialise des Tasks avec une porte de validation humaine (`pending_validation`) au-delà d'un seuil de sévérité.

## AI / Agents / Capabilities / Orchestrator

Agent ≠ domaine de navigation : un agent est un regroupement de capabilities. Capability = unité typée (lecture ou action), certaines déterministes, d'autres enveloppant un appel LLM. Depuis l'étape 12, l'Orchestrator peut sélectionner **plusieurs agents à la fois** (routage par topic, ex. "margin" → finance+procurement+sales) plutôt qu'un seul agent par question — un agent ne verrouille jamais l'accès aux capabilities des autres. Human-in-the-loop (étapes 10-11) : `create_task` ne fait que proposer (`PENDING_VALIDATION`) ; seule une approbation humaine explicite déclenche l'exécution réelle via `ActionExecutor`, jamais l'Orchestrator directement.

## Human-in-the-loop (Actions)

```
AI Orchestrator → propose (Task PENDING_VALIDATION, pending_action déclaré)
Human → POST /actions/tasks/{id}/approve|reject
   approve → ActionExecutor → Service métier → Task EXECUTED (+ événement métier, ex. TaskCreated)
   reject  → Task REJECTED, rien n'est exécuté
```

`Task.pending_action` distingue une proposition IA exécutable d'une Task créée directement par le flux réactif Intelligence (Risk → Task), qui n'a pas de `pending_action` et n'est pas éligible à ce cycle.

## Vertical slice prioritaire

Seed → Supplier/Product/Transaction → Procurement → Business Event → Intelligence → Risk/Opportunity → Action/Task → Home → Ask AI → Capability → Action éventuelle.

## Frontend build-out (Steps 24-29)

Les sections ci-dessus couvrent le backend jusqu'au Step 23B ; il n'a pas changé d'architecture depuis. Les steps suivants ont porté sur le frontend (devenu la référence visuelle réelle du produit, plus un prototype) et quelques ajouts additifs, minimaux et justifiés côté backend :

- **Company / Business Context / Onboarding (Step 24)** : `GET/PATCH /company` (nom, secteur) et `GET/PATCH /business-context` exposés en frontend via un assistant d'onboarding en 4 étapes (`frontend/app/onboarding/`) et une page `/settings` — aucune nouvelle table, uniquement l'exposition de ce que `app/company/` et `app/business_context/` savaient déjà faire.
- **Design system V2 (Step 26)** : un seul langage visuel (Fraunces/Plus Jakarta Sans/IBM Plex Mono, thème clair) appliqué à toutes les pages, navigation restructurée en groupes (Accueil, Entreprise, Données, Intelligence, Actions, IA), Command Center comme page phare avec la chaîne Observation → Interprétation → Décision rendue visuellement.
- **« Vie de l'entreprise » et élimination du bruit technique (Step 27)** : couche MACRO/MICRO/NANO explicite ; toute sortie technique brute (JSON, `payload`, `event_type`, réponses `deterministic answer` sans LLM configuré) a été remplacée à la source (jamais par un `.replace()` dans un composant) par des phrases françaises composées depuis les données déjà structurées — voir `app/core/observable_labels.py` et les branches `isinstance(llm, DeterministicLLMClient)` dans `interpretation/engine.py`, `decision/engine.py`, `ai/orchestrator/service.py`. `HomeService.get_os_activity`/`get_company_narrative` (nouveau) exposent l'activité IA et les événements narratifs réels (Communications) sans jamais inventer qu'un agent a agi s'il ne l'a pas fait.
- **Passe UX interactive (Step 28)** : chaque widget qui ressemble à un bouton doit réellement faire quelque chose (Decision Intelligence, sector pills, cartes d'activité) ; `/data` regroupe Fournisseurs/Clients/Produits/Transactions en 4 widgets ; `/data/contacts` devient un vrai centre de communication (`GET /contacts`, nouveau, compose les tables `Contact`/`Communication` existantes) avec état honnête « Connexion non configurée » pour tout canal sans connecteur réel ; sélecteur FR/EN (`frontend/lib/i18n.tsx`) limité à l'interface elle-même, jamais au contenu généré par le backend.
- **Courbes 12 mois et Tasks comme centre d'action (Step 29)** : `compute_monthly_series` (nouveau, `app/core/analytics.py`) alimente un vrai graphique animé par domaine (Achats, Ventes) et un recoupement Achats/Ventes sur Finance — jamais d'estimation, un mois sans transaction vaut `0`, pas une omission. `Task` gagne deux colonnes additives (`domain`, `requires_decision`) et deux endpoints (`POST /actions/tasks/{id}/status`, `POST /actions/tasks/{id}/submit` — ce dernier réutilise la branche d'exécution `create_task` existante, aucun nouveau branchement dans `ActionExecutor`) pour que le frontend puisse offrir une vraie bibliothèque d'actions métier par secteur sans construire un second système de tâches.

Voir `brain/decisions.md` (#25 et suivants) pour le détail de chaque choix.

## État d'avancement

Backend : étapes 1 à 23B implémentées et validées (scaffolding, Data Core, Events, Procurement, Intelligence réactive + monitoring proactif multi-domaines, Actions + Human-in-the-loop complet, Home/Command Center, AI cross-domaine, Business Context, External Connectivity Layer, External Data Intelligence, Business Domains). Frontend : étapes 24 à 29 (onboarding, design system V2, "vie de l'entreprise", passe UX interactive, graphiques 12 mois et Tasks comme centre d'action) — voir la section précédente. Voir `README.md` pour les commandes et `brain/` pour les décisions et le dataset de démonstration détaillés.

## V2 / V2.1

The V2 (business objects, relationships, transactions, roles, navigation) and
V2.1 (custom access, people, director finance, compliance, sourcing, website
intelligence) architecture is documented in `brain/architecture.md`, with
`brain/business_object_model.md`, `brain/transactional_model.md`,
`brain/navigation_v2.md`, `brain/permissions.md`, `brain/communications.md`,
`brain/people.md`, `brain/director_finance.md`, `brain/compliance.md`,
`brain/sourcing.md`, `brain/website_intelligence.md`, `brain/design.md` and
decisions #30–#45 in `brain/decisions.md`.

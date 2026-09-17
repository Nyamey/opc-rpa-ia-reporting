# Automatisation des opérations bancaires : sélection et réconciliation

## Case study

**Before automating anything, prove the process actually deserves it.**

The working language of the detailed documentation below is French; this section is the case study for an English-speaking reviewer.

### The problem

A bank's operations division loses several hours a day reconciling front-office and back-office records by hand, then justifying every discrepancy line by line — tedious, repetitive, and exactly the kind of work automation should absorb. But in a regulated bank, reaching for RPA on the wrong process is a common and expensive mistake: automating a process that already has an API, or one whose inputs are unstructured, hard-codes a bad design instead of fixing it.

### The decision: prove the candidate before building anything

This repository covers the two moments of an automation programme, in that order — select the right process, then industrialise one end to end. Twenty candidate processes across five operational sectors (Capital Markets Operations, Global Referential Management, Financing and Trade Operations, Cash Management Services, Supply Chain Services) are scored on two axes: value (FTE workload, regulatory exposure, current error rate) and feasibility (share of rule-based handling, process stability, input structure, number of systems touched).

Three criteria are treated as knock-outs rather than weighted factors, because a strong score elsewhere must never compensate for them:

- **An API already exists.** Driving a screen with a robot when the system exposes an interface is an engineering mistake — more brittle and more expensive to maintain than a direct integration. The process leaves RPA scope entirely.
- **Input data is unstructured.** A robot cannot read a document; the process needs a hybrid design with document recognition ahead of the robot, never a classic automation.
- **Rule-based handling falls below 60%.** Automating a process where four cases out of ten fall outside the standard path would hard-code the workarounds teams invented to compensate for a poorly designed process, rather than fix the process.

Eleven of twenty processes are retained, representing 37 FTE of addressable workload out of 45 assessed. The trade-off worth surfacing in a steering committee: the two largest opportunities both need document recognition, so the programme cannot hit its savings target with classic RPA alone — a conclusion the scoring grid forces out before a single line of automation code is written.

### The build: the winning process, end to end

The process the grid ranked first — daily front-office/back-office reconciliation in Capital Markets Operations — is industrialised in full. Transactions are matched on five keys, amounts compared within tolerance, and every discrepancy qualified with a probable cause, a recommended action and a confidence score: a language model performs that qualification when configured, with a deterministic rule engine taking over on any failure, so the service degrades instead of stopping.

Outputs: an Excel workbook, a management summary, an error log, and six Power BI tables with a fixed schema. Two of those tables accumulate over time — what makes trend curves and break-ageing possible, since a break outstanding for eight days calls for different treatment than one raised this morning.

### The outcome

92 automated tests cover matching logic, indicator computation, schema stability, file parsing and security, backed by 24 tooled acceptance datasets. A security review I ran found and fixed a spreadsheet formula-injection vulnerability before it shipped: a counterparty named `=cmd|'/c calc.exe'!A0` was being written into the workbook as an executable dynamic-data-exchange formula, not as text.

Built with Python and pandas, reported through Excel, Power BI and an interactive Streamlit view (`streamlit run streamlit_app.py`). The design stays deliberately tool-agnostic: the same logical model would transfer to UiPath, Power Automate or Automation Anywhere in a production environment.

---

## Vue interactive

```bash
streamlit run streamlit_app.py
```

L'application ouvre les deux volets dans le navigateur, sur `http://localhost:8501`. Elle n'implémente aucune règle métier : elle appelle les mêmes modules que les traitements en ligne de commande, ce qui rend impossible une divergence entre l'écran et le rapport produit.

Le premier volet affiche la matrice de sélection, où chaque processus est situé par rapport aux deux seuils, l'aire du point étant proportionnelle à la charge en équivalents temps plein. Le second affiche les indicateurs de réconciliation, l'exposition par nature d'écart, la courbe de tendance dès la deuxième journée traitée et le détail des écarts avec leur ancienneté.

### Traiter ses propres fichiers

Chaque volet comporte une zone de dépôt. Une fois les fichiers déposés, la totalité du traitement s'enchaîne sans autre action : contrôle des fichiers, rapprochement ou notation, qualification, calcul des indicateurs, puis mise à disposition des livrables au téléchargement.

Le format d'entrée est reconnu automatiquement. Un export de tableur français, en point-virgule et en page de code Windows, est accepté sans conversion, de même qu'un fichier en UTF-8 avec marque d'ordre des octets ou un export tabulé. Les espaces résiduels dans les noms de colonnes sont absorbés, car ils sont invisibles à l'œil et produiraient sinon un diagnostic incompréhensible.

Un modèle est téléchargeable dans chaque zone de dépôt, ce qui évite d'avoir à deviner les colonnes attendues. Lorsqu'un fichier est refusé, le message nomme la cause : fichier vide, colonne absente avec la liste de celles qui ont été trouvées, ou lignes de longueur inégale.

Trois points de fonctionnement méritent d'être connus.

Les fichiers déposés sont écrits dans un répertoire temporaire propre à la session, jamais dans `data/input`. Le jeu de démonstration du dépôt reste donc intact.

Une exécution issue d'un dépôt n'alimente pas les historiques du projet. C'est délibéré : un essai ne doit pas s'inscrire dans la courbe de tendance ni dans le calcul d'ancienneté. En contrepartie, la tendance et l'ancienneté ne sont pas affichées pour un fichier déposé, puisqu'elles se construisent au fil des exécutions quotidiennes de `python src/main.py`.

Les livrables produits à partir d'un fichier déposé passent par les mêmes protections que les autres. Une contrepartie hostile déposée par un tiers ressort neutralisée dans le classeur téléchargé.

Deux choix méritent d'être signalés. Les six orientations sont regroupées en trois familles de couleur dans la matrice : un nuage de points impose de valider la lisibilité sur toutes les paires de couleurs, et au-delà de trois teintes certaines paires deviennent indistinguables pour un lecteur daltonien. L'orientation précise reste accessible au survol et dans le tableau. Par ailleurs, l'écoute est restreinte au poste local dans `.streamlit/config.toml` : Streamlit se lie par défaut à toutes les interfaces, ce qui exposerait l'application au réseau sans authentification.

## Présentation

Ce dépôt couvre les deux moments d'un programme d'automatisation en direction des opérations : choisir les bons processus, puis en industrialiser un.

**En amont, la grille de sélection.** Vingt processus candidats des secteurs CMO, GRM, FTO et TBS sont notés sur deux axes, valeur et faisabilité, puis orientés vers l'automatisation classique, le projet hybride avec IA, l'intégration applicative, l'optimisation préalable ou l'abandon. C'est l'étape qui décide de la réussite d'un programme, bien avant le développement.

**En aval, un processus automatisé de bout en bout.** La réconciliation quotidienne entre front office et back office, retenue par la grille comme premier candidat du secteur CMO, avec sa qualification des écarts, ses indicateurs, ses livrables et son rapport décisionnel.

Le projet reproduit un besoin courant des centres de traitement bancaires : chaque jour, les équipes comparent ce qu'a enregistré le front office avec ce qu'a comptabilisé le back office, puis justifient ligne à ligne les divergences. Fait à la main, ce travail occupe plusieurs heures et laisse passer des erreurs. Automatisé, il se ramène à quelques secondes et à un rapport exploitable directement.

---

## Volet 1 : sélection des processus

```bash
python src/evaluer_processus.py
```

Chaque candidat est décrit par treize attributs recueillis auprès du secteur concerné, puis noté. La valeur pèse la charge en équivalents temps plein, la criticité réglementaire et le taux d'erreur actuel. La faisabilité pèse le taux de règles, la stabilité, la structuration des données et le nombre d'applications traversées.

Trois critères sont éliminatoires et ne se compensent pas, ce qu'une simple moyenne pondérée manquerait :

- **Une interface applicative existe.** Faire piloter un écran par un robot quand une API est disponible est un contresens technique, plus fragile et plus coûteux qu'une intégration. Le processus sort du périmètre RPA.
- **Les données sont non structurées.** Un robot ne lit pas un document. Le processus relève d'un projet hybride avec reconnaissance documentaire, jamais d'une automatisation classique.
- **Le taux de règles est inférieur à 60 %.** Automatiser un processus dont quatre dossiers sur dix sortent du cas nominal revient à figer les contournements existants.

Sur le portefeuille livré, onze processus sont retenus pour trente-sept ETP de charge adressable. Les deux plus gros gisements sont des projets hybrides, ce qui signifie que le programme ne peut pas atteindre ses objectifs avec la seule RPA.

La méthode complète, les pondérations et la lecture des résultats figurent dans [docs/GRILLE_SELECTION.md](docs/GRILLE_SELECTION.md).

---

## Volet 2 : le processus automatisé

## Ce que fait la chaîne

Le traitement se déroule en six étapes successives.

1. **Chargement.** Les deux fichiers CSV sont lus et contrôlés. Un fichier vide, illisible ou amputé d'une colonne obligatoire interrompt le traitement avec un message qui nomme précisément le problème.
2. **Rapprochement.** Les transactions sont appariées sur cinq clés : identifiant, contrepartie, produit, date de négociation et devise. Le montant est ensuite comparé à part, avec une tolérance d'un centime.
3. **Classification.** Chaque écart reçoit un motif probable, une action recommandée et un indice de confiance. Un modèle de langage est sollicité s'il a été configuré, sinon un jeu de règles déterministe prend le relais.
4. **Calcul des indicateurs.** Volumes, taux de rapprochement, exposition financière et répartitions par motif, contrepartie, produit et nature.
5. **Restitution.** Un classeur Excel, une synthèse texte et un relevé d'erreurs.
6. **Export décisionnel.** Cinq tables au schéma constant, destinées au rapport Power BI, dont l'historique des exécutions qui permet les courbes de tendance.

## Natures d'écart détectées

| Nature | Signification | Action type |
|---|---|---|
| `amount` | La transaction existe des deux côtés mais les montants diffèrent au-delà de la tolérance | Vérifier la saisie avec le middle office |
| `amount_invalid` | La transaction existe des deux côtés mais un montant est absent ou illisible | Contrôler la qualité de l'extraction |
| `missing_B` | La transaction n'existe que dans le Système A | Relancer le back office pour comptabilisation |
| `missing_A` | La transaction n'existe que dans le Système B | Relancer le front office pour enregistrement |

Un point mérite d'être compris avant de lire les rapports. La date et la devise font partie des clés de rapprochement. Une transaction correctement saisie de part et d'autre mais portant deux dates différentes n'est donc pas vue comme une transaction unique en écart de date : elle apparaît comme deux lignes, `missing_A` et `missing_B`, portant le même identifiant. C'est un choix assumé, car il évite d'inventer un appariement là où deux systèmes ne s'accordent pas sur un attribut structurant. Le rapprochement de ces couples reste à la main de l'analyste.

## Installation

Le projet demande Python 3.9 ou une version plus récente.

```bash
python -m venv venv
venv\Scripts\activate          # sous Windows
source venv/bin/activate       # sous Linux ou macOS
pip install -r requirements.txt
```

## Exécution

```bash
python src/main.py
```

Les répertoires par défaut peuvent être remplacés.

```bash
python src/main.py --input-dir data/input --output-dir data/output --log-level DEBUG
```

Le traitement rend un code de sortie 0 en cas de succès et 1 en cas d'échec, ce qui permet de l'enchaîner dans un ordonnanceur sans avoir à analyser les journaux.

## Fichiers d'entrée

Les deux fichiers doivent être déposés dans `data/input` sous les noms `transactions_systemA.csv` et `transactions_systemB.csv`, et comporter six colonnes.

| Colonne | Contenu | Exemple |
|---|---|---|
| `trade_id` | Identifiant de la transaction | `TRD-1001` |
| `counterparty` | Contrepartie | `BNP Paribas` |
| `product` | Type d'instrument | `IRS` |
| `trade_date` | Date de négociation au format ISO | `2026-08-03` |
| `amount` | Montant notionnel | `1250000.00` |
| `currency` | Devise sur trois lettres | `EUR` |

Le jeu de données livré contient trente transactions par système et couvre volontairement les quatre natures d'écart, ainsi qu'un cas de divergence de date et un cas de divergence de devise. Il s'agit de données synthétiques, sans lien avec un client ou un établissement réel.

## Livrables produits

Tous les livrables sont déposés dans `data/output` et écrasés à chaque exécution.

**`kpi_report.xlsx`** rassemble six feuilles : la synthèse des indicateurs, le détail ligne à ligne des écarts avec leur classification, puis les répartitions par nature, par motif, par contrepartie et par produit.

**`summary.txt`** condense l'essentiel sur une trentaine de lignes, dans un format prêt à être collé dans un courriel de reporting.

**`errors_summary.csv`** relève les erreurs survenues pendant le traitement. Ce fichier est écrit même quand tout s'est bien passé, auquel cas il ne contient que son en-tête. Cette présence systématique permet à un outil de supervision de s'appuyer dessus sans traiter le cas du fichier absent.

Chaque exécution dépose par ailleurs un journal horodaté dans `logs/`.

## Rapport Power BI

Le répertoire `data/powerbi` reçoit cinq tables organisées en modèle en étoile, distinctes des livrables destinés à la lecture humaine. La raison de cette séparation est simple : le classeur Excel fait disparaître ses feuilles vides, ce qui ferait échouer un rafraîchissement Power BI le jour où aucun écart n'est détecté. Les tables décisionnelles conservent au contraire toujours les mêmes colonnes.

| Table | Grain | Renouvellement |
| --- | --- | --- |
| `fact_breaks.csv` | Un écart | Remplacée |
| `fact_matched.csv` | Une transaction rapprochée | Remplacée |
| `fact_breaks_history.csv` | Un écart et une journée | Enrichie |
| `kpi_history.csv` | Une exécution | Enrichie |
| `dim_break_type.csv` | Une nature d'écart | Remplacée |
| `dim_date.csv` | Un jour du calendrier | Remplacée |

Deux tables s'accumulent, sans quoi le rapport ne montrerait jamais que la photographie du jour.

`kpi_history.csv` conserve toutes les exécutions, la colonne `est_derniere_du_jour` désignant celle qui fait référence pour la journée. Toute mesure agrégeant cette table doit appliquer ce filtre, faute de quoi une journée relancée trois fois serait comptée trois fois.

`fact_breaks_history.csv` conserve une ligne par écart et par journée où il était encore ouvert. C'est elle qui alimente les colonnes `first_seen_date` et `days_open` de `fact_breaks.csv`, autrement dit le suivi du vieillissement. Un écart ouvert depuis huit jours et un écart apparu le matin même n'appellent pas le même traitement.

La durée de conservation des deux historiques se règle par `HISTORY_RETENTION_DAYS`, à deux ans par défaut.

Le fichier `powerbi/modele_powerbi.pq` contient les requêtes Power Query prêtes à coller, et `powerbi/mesures_dax.md` les mesures. La procédure de montage complète figure dans [docs/POWERBI.md](docs/POWERBI.md).

Le fichier `powerbi/reportings.pbix` livré dans le dépôt fait zéro octet et ne s'ouvre pas. Le rapport est à construire une fois depuis un document vierge, puis à enregistrer sous ce nom.

## Classification par modèle de langage

Le raccordement à un modèle de langage est facultatif. Sans configuration, la classification s'appuie sur des règles déterministes, ce qui constitue un mode de fonctionnement complet.

Pour activer le modèle, copiez `.env.example` en `.env` et renseignez au minimum `LLM_API_URL` et `LLM_API_KEY`. Les appels sont émis transaction par transaction. Si l'un d'eux échoue, expire ou renvoie une réponse inexploitable, l'écart concerné bascule sur sa règle déterministe et le traitement se poursuit. Une indisponibilité du service ne peut donc pas faire échouer la production du rapport.

## Tests

```bash
pytest tests/ -v
```

La suite compte quatre-vingt-dix scénarios.

Onze portent sur la lecture des fichiers : export de tableur français en point-virgule et page de code Windows, UTF-8 avec marque d'ordre des octets, export tabulé, espaces résiduels dans les en-têtes, valeur contenant le séparateur, et les quatre cas de rejet avec leur message.

Dix-neuf portent sur la grille de sélection : conversion de la charge en équivalents temps plein, bornage des notes, tolérance aux données manquantes, et surtout la doctrine d'arbitrage. Chaque critère éliminatoire a son test, et deux d'entre eux ont été ajoutés à la grille précisément parce qu'un test a montré qu'un processus sur données non structurées pouvait être classé en automatisation directe.

Quinze portent sur le traitement : rapprochement parfait, écart de montant au-dessus et en dessous de la tolérance, transaction absente de chaque système, divergence de devise, montant illisible, montant saisi sous forme de texte, clés comportant des espaces superflus, calcul des indicateurs avec et sans écart, classification par règles, et les trois cas de rejet d'un fichier d'entrée invalide.

Dix-neuf portent sur l'export décisionnel : présence des six tables, stabilité du schéma sans écart et sans rapprochement, calcul de l'exposition, conservation de chaque exécution, marquage de l'exécution de référence, ancienneté d'un écart nouveau puis persistant, absence de collision entre clés d'écart, non-duplication lors d'un rejeu, persistance d'un écart résolu dans l'historique, reconstruction des deux historiques corrompus, continuité et couverture du calendrier, complétude du référentiel et restitution des accents.

Vingt-six portent sur la sécurité : neutralisation des charges utiles d'injection de formule, absence de toute formule dans le classeur produit, assainissement des CSV et du relevé d'erreurs, masquage des identifiants dans les journaux, refus des adresses non chiffrées, isolement des données non fiables dans la consigne au modèle et bornage de ses réponses.

## Sécurité

Les fichiers d'entrée viennent de systèmes tiers et leur contenu se retrouve dans des classeurs ouverts par des analystes. Cette chaîne est donc traitée comme une frontière de confiance, et les défenses sont regroupées dans [src/security.py](src/security.py).

La protection principale concerne l'injection de formule. Une contrepartie nommée `=cmd|'/c calc.exe'!A0` était écrite dans le classeur non pas comme du texte mais comme une véritable formule d'échange dynamique de données, exécutable sur le poste qui ouvre le rapport. Toute valeur commençant par `=`, `+`, `-`, `@`, une tabulation ou un retour chariot est désormais préfixée d'une apostrophe à l'écriture, ce qui force le mode texte. Les valeurs légitimes ne commencent jamais par ces caractères et restent intactes.

Les autres défenses portent sur le raccordement au modèle de langage : refus des adresses non chiffrées, masquage des identifiants dans les messages d'erreur journalisés, isolement des données non fiables dans la consigne, et bornage de la taille des réponses. Le texte renvoyé par le service est traité avec la même défiance que les fichiers d'entrée.

Le détail figure au chapitre 6 de [docs/SDD_SolutionDesign.md](docs/SDD_SolutionDesign.md).

## Structure du dépôt

```
data/
  input/     Transactions des deux systèmes et référentiel des candidats
  output/    Livrables régénérés à chaque exécution
  powerbi/   Tables décisionnelles au schéma constant
docs/
  GRILLE_SELECTION.md            Méthode de sélection des processus
  PDD_ProcessReconciliation.md   Description métier du processus
  SDD_SolutionDesign.md          Conception technique de la solution
  UAT_scenarios.md               Scénarios de recette
  RUNBOOK.md                     Procédure d'exploitation courante
  POWERBI.md                     Montage et exploitation du rapport
logs/        Journaux horodatés
.streamlit/
  config.toml                    Thème et écoute de la vue interactive
streamlit_app.py                 Vue interactive des deux volets
powerbi/
  modele_powerbi.pq              Requêtes Power Query prêtes à coller
  mesures_dax.md                 Mesures du modèle
  reportings.pbix                Emplacement du rapport, à créer
src/
  config.py                  Paramètres centralisés
  csv_reader.py              Lecture tolérante des CSV hétérogènes
  evaluer_processus.py       Point d'entrée de la grille de sélection
  process_assessment.py      Notation et arbitrage des candidats
  main.py                    Point d'entrée de la réconciliation
  reconciliation_engine.py   Chargement, contrôle et rapprochement
  llm_classifier.py          Qualification des écarts
  kpi_calculator.py          Calcul des indicateurs
  report_generator.py        Production des livrables
  powerbi_export.py          Tables décisionnelles et historisation
  security.py                Défenses appliquées aux données non fiables
tests/
  test_csv_reader.py         Formats, encodages et séparateurs
  test_process_assessment.py Notation et doctrine d'arbitrage
  test_reconciliation.py     Rapprochement, indicateurs, classification
  test_powerbi_export.py     Schéma des tables et historisation
  test_security.py           Injection de formule, secrets, transport
```

## Paramétrage

Les valeurs modifiables sont regroupées dans `src/config.py`.

`MATCH_KEYS` définit les colonnes qui identifient une transaction. Retirer une colonne de cette liste rend le rapprochement plus permissif, l'ajout d'une colonne le rend plus strict.

`AMOUNT_TOLERANCE` fixe l'écart de montant toléré, à un centime par défaut. Cette tolérance absorbe les imprécisions d'arrondi entre systèmes sans masquer une véritable erreur de saisie.

`REQUIRED_COLUMNS` liste les colonnes exigées dans les fichiers d'entrée.

## Limites connues

Le rapprochement charge l'intégralité des deux fichiers en mémoire et parcourt le résultat ligne à ligne. Cette approche convient jusqu'à quelques dizaines de milliers de transactions. Au-delà, il faudrait vectoriser la comparaison ou traiter par lots.

Les doublons de clés ne sont pas bloquants mais signalés par un avertissement dans le journal. Deux lignes partageant les mêmes clés produisent un produit cartésien lors de la fusion, ce qui gonfle artificiellement le nombre de lignes examinées. Il est préférable de dédoublonner les fichiers en amont.

Enfin, la solution ne gère pas encore les rapprochements partiels, par exemple une transaction du Système A soldée par deux lignes du Système B.

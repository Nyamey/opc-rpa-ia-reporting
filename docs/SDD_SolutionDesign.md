# Document de conception de la solution

**Solution :** Réconciliation des transactions et production des indicateurs de pilotage
**Version :** 2.0
**Date :** 2 septembre 2026
**Document métier associé :** [PDD_ProcessReconciliation.md](PDD_ProcessReconciliation.md)

---

## 1. Principes de conception

Quatre principes ont guidé la construction de la chaîne.

**Échouer tôt et clairement.** Un fichier d'entrée invalide arrête le traitement avant tout calcul, avec un message qui nomme le fichier et la colonne fautive. Produire un rapport à partir de données douteuses serait plus dangereux que ne rien produire du tout, car personne ne saurait qu'il faut s'en méfier.

**Ne jamais rapprocher par défaut.** Face à une donnée ambiguë, la chaîne classe en écart plutôt qu'en rapprochement. Un faux écart coûte quelques minutes d'analyse ; un faux rapprochement laisse passer une erreur en production.

**Dégrader plutôt qu'interrompre.** La qualification par modèle de langage est un enrichissement, pas une dépendance. Son indisponibilité fait basculer la chaîne sur les règles déterministes sans interrompre la production des livrables.

**Séparer le calcul de la restitution.** Le moteur de rapprochement ne connaît ni Excel ni la mise en forme des rapports. Le générateur de rapports ne sait pas rapprocher. Cette séparation permet de tester chaque partie isolément et d'ajouter un format de sortie sans toucher à la logique métier.

## 2. Architecture

```text
data/input/*.csv
        |
        v
  [ main.py ]  orchestration, journalisation, gestion des erreurs
        |
        +--> reconciliation_engine.py   chargement, contrôle, rapprochement
        |          |
        |          v
        |    transactions rapprochées + écarts bruts
        |          |
        +--> llm_classifier.py          motif, action, confiance
        |          |
        |          v
        |    écarts qualifiés
        |          |
        +--> kpi_calculator.py          synthèse et répartitions
        |          |
        |          v
        +--> report_generator.py        Excel, synthèse texte, relevé d'erreurs
        |          |
        |          v
        |    data/output/ + logs/
        |
        +--> powerbi_export.py          tables décisionnelles, historisation
                   |
                   v
            data/powerbi/
```

Le flux est linéaire et sans état partagé. Chaque module reçoit des tableaux en entrée et rend des tableaux en sortie, ce qui rend chaque étape testable isolément.

## 3. Description des modules

### 3.1 `config.py`

Regroupe l'ensemble des valeurs modifiables : chemins, noms de fichiers, colonnes obligatoires, clés de rapprochement, tolérance sur les montants et paramètres du modèle de langage.

Le module charge un fichier `.env` s'il est présent à la racine, ce qui permet de fournir les identifiants du modèle sans les écrire dans le code ni les exposer dans le dépôt. Il crée également les répertoires de travail à l'import, afin qu'une première exécution sur un poste vierge ne bute pas sur un répertoire absent.

Le drapeau `USE_LLM` est déduit de la présence d'une URL. Il n'existe donc aucun moyen d'activer le modèle sans l'avoir configuré, ce qui écarte une classe entière d'erreurs de paramétrage.

### 3.2 `reconciliation_engine.py`

Ce module porte le cœur métier.

**Lecture et contrôle.** Chaque fichier est contrôlé en trois temps : existence, taille non nulle, présence des colonnes obligatoires. Le contrôle de taille précède la lecture, car un fichier de zéro octet produit sinon un message de bibliothèque peu explicite pour un exploitant.

**Normalisation.** Avant rapprochement, les clés sont converties en texte épuré et les montants convertis en nombres. Un montant illisible devient une valeur indéterminée plutôt que de faire échouer le traitement, et sera signalé comme écart à l'étape suivante.

Un tableau totalement vide est reconstruit avec le schéma attendu. C'est ce qui permet de rapprocher un Système A garni contre un Système B vide, situation qui se produit réellement lorsqu'une extraction échoue en amont.

Les doublons de clés sont détectés et signalés par un avertissement. Ils ne bloquent pas le traitement, mais l'exploitant est prévenu que la fusion produira un produit cartésien et que les volumes seront gonflés.

**Rapprochement.** Une fusion externe sur les cinq clés produit un tableau unique portant un indicateur d'origine. Chaque ligne est ensuite examinée pour déterminer sa nature.

L'ordre des contrôles est significatif. La disponibilité des montants est vérifiée avant leur comparaison, car une différence impliquant une valeur indéterminée s'évalue à faux pour tout opérateur de comparaison. Sans ce contrôle explicite, une transaction dont le montant manque des deux côtés tomberait dans la branche « rapprochée », ce qui reviendrait à valider une donnée inexistante. Ce comportement existait dans la première version de la solution et a été corrigé.

### 3.3 `llm_classifier.py`

Deux voies de qualification coexistent derrière une interface unique.

La voie déterministe s'appuie sur un dictionnaire de règles associant à chaque nature d'écart un motif, un gabarit d'action et un indice de confiance. Le gabarit d'action est complété par le nom de la contrepartie, ce qui rend l'action directement actionnable par l'analyste.

La voie par modèle de langage émet un appel par écart. Ce découpage est délibéré : une réponse inexploitable n'invalide alors que l'écart concerné, qui retombe sur sa règle déterministe, au lieu de compromettre le lot entier. Une session HTTP unique est réutilisée pour l'ensemble des appels afin de ne pas rétablir une connexion à chaque transaction.

La réponse du modèle est validée avant utilisation : le contenu doit être un objet JSON, et l'indice de confiance est ramené dans l'intervalle de zéro à un. Un modèle qui renverrait une confiance de 1,4 ou du texte libre ne peut donc pas corrompre les indicateurs en aval.

### 3.4 `kpi_calculator.py`

Produit cinq tableaux : la synthèse et quatre répartitions.

Les répartitions passent par une fonction unique de comptage qui rend un tableau vide lorsque la colonne demandée est absente. Cette tolérance permet de calculer des indicateurs sur des écarts non encore qualifiés, ce dont les tests tirent parti.

L'exposition des écarts additionne les différences de montant en valeur absolue, les valeurs indéterminées étant traitées comme nulles. Une transaction absente d'un système compte donc pour son montant entier, ce qui correspond bien au risque porté.

### 3.5 `report_generator.py`

Produit les trois livrables.

Le classeur Excel est assemblé à partir d'une liste ordonnée de feuilles, les feuilles vides étant écartées. La largeur des colonnes est ajustée au contenu, plafonnée pour éviter les colonnes démesurées, et calculée sur les deux cents premières lignes seulement afin que le coût reste constant quel que soit le volume.

Un garde-fou insère une feuille d'information si toutes les feuilles se révélaient vides, car un classeur sans aucune feuille visible est rejeté par Excel.

Le relevé d'erreurs est écrit avec un encodage portant une marque d'ordre des octets, de sorte qu'Excel affiche correctement les accents lors d'un double-clic sur le fichier.

### 3.6 `powerbi_export.py`

Produit le jeu de tables consommé par le rapport décisionnel.

Ce module existe parce que les livrables destinés à la lecture humaine et ceux
destinés à un outil décisionnel obéissent à des contraintes opposées. Le
classeur Excel écarte ses feuilles vides pour ne pas encombrer le lecteur ; un
modèle Power BI, à l'inverse, échoue au rafraîchissement dès qu'une colonne
attendue disparaît. Brancher le rapport sur le classeur reviendrait donc à le
casser le premier jour où le rapprochement serait parfait.

Toute table est écrite au travers d'une fonction unique qui garantit le schéma :
les colonnes absentes sont créées vides, les colonnes surnuméraires écartées, et
l'ordre est imposé. Une table sans aucune ligne conserve ainsi son en-tête
complet.

Quatre tables sont remplacées à chaque exécution. Deux s'enrichissent, et ce
sont elles qui donnent au rapport sa profondeur temporelle.

L'historique des indicateurs conserve toutes les exécutions. Une première
version n'en gardait qu'une par journée, en considérant que le grain du
reporting était la journée. Ce raisonnement était juste sur le fond mais faux
en pratique : pendant la mise au point, le traitement est relancé plusieurs
fois par jour, et l'historique semblait donc s'effacer à chaque exécution. La
colonne `est_derniere_du_jour` résout la tension : toutes les exécutions sont
tracées, et le rapport sait laquelle fait référence pour la journée.

La contrepartie de ce choix doit être connue de qui écrit les mesures. Agréger
l'historique sans filtrer sur cette colonne compte une journée autant de fois
qu'elle a été relancée. Toutes les mesures livrées appliquent le filtre.

L'historique des écarts conserve une ligne par écart et par journée où il était
encore ouvert. Son grain est en revanche bien la journée, car son volume est
sans commune mesure avec celui des indicateurs : plusieurs exécutions le même
jour mettent à jour les lignes du jour. Sans cette règle, dix essais successifs
produiraient dix lignes et feraient croire à dix journées d'ancienneté.

De cet historique découlent les deux colonnes de vieillissement portées par la
table des écarts du jour. L'identité d'un écart repose sur la transaction, ses
attributs et la nature de la divergence, à l'exclusion du montant : un écart
dont le montant bouge légèrement reste le même écart tant que la transaction et
la nature de la divergence ne changent pas.

La durée de conservation est commune aux deux historiques et paramétrable. La
purge s'applique après ajout, ce qui garantit que l'exécution courante est
toujours conservée quelle que soit la valeur retenue.

Un historique devenu illisible est reconstruit à neuf avec un avertissement,
plutôt que d'interrompre la production du jour. Perdre la profondeur historique
est regrettable ; ne pas produire le rapport quotidien le serait davantage.

La table de dates est continue et couvre à la fois les dates de négociation de
l'exécution courante et l'ensemble des dates d'exécution déjà historisées. Cette
seconde condition est facile à manquer : une table de dates construite sur les
seules données du jour laisserait les points de tendance anciens hors de la
plage du calendrier, et leur relation avec la table de dates serait rompue.

L'encodage retenu porte une marque d'ordre des octets, sans laquelle Power BI
et Excel interprètent les accents en page de code locale.

### 3.7 `main.py`

Orchestre les cinq étapes, met en place la journalisation et gère les erreurs.

La journalisation retire les gestionnaires existants avant d'installer les siens. Sans cette précaution, un second appel dans le même processus dupliquerait chaque message.

Deux familles d'erreurs sont distinguées. Les erreurs attendues, fichier absent ou données invalides, portent déjà un message destiné à un exploitant et sont restituées telles quelles. Les erreurs inattendues sont journalisées avec leur pile d'appels complète, destinée au support technique. Dans les deux cas, l'erreur est consignée dans le relevé et le processus rend un code de sortie 1.

## 4. Modèle de données

### 4.1 Entrée

| Colonne | Type | Obligatoire | Rôle |
| --- | --- | --- | --- |
| `trade_id` | Texte | Oui | Clé de rapprochement |
| `counterparty` | Texte | Oui | Clé de rapprochement |
| `product` | Texte | Oui | Clé de rapprochement |
| `trade_date` | Date ISO | Oui | Clé de rapprochement |
| `amount` | Décimal | Oui | Comparé avec tolérance |
| `currency` | Texte | Oui | Clé de rapprochement |

### 4.2 Tableau des écarts

| Colonne | Origine | Contenu |
| --- | --- | --- |
| `trade_id` à `currency` | Rapprochement | Attributs de la transaction |
| `amount_a` | Rapprochement | Montant côté Système A |
| `amount_b` | Rapprochement | Montant côté Système B |
| `break_type` | Rapprochement | Nature de l'écart |
| `break_details` | Rapprochement | Description lisible |
| `suggested_reason` | Qualification | Motif probable |
| `suggested_action` | Qualification | Action recommandée |
| `confidence` | Qualification | Indice entre zéro et un |

### 4.3 Synthèse des indicateurs

| Colonne | Contenu |
| --- | --- |
| `total_transactions` | Transactions distinctes présentes dans au moins un système |
| `matched_count` | Transactions rapprochées sans écart |
| `breaks_count` | Écarts détectés |
| `match_rate` | Taux de rapprochement en pourcentage |
| `total_break_amount` | Exposition cumulée des écarts |
| `calculation_timestamp` | Horodatage du calcul |

## 5. Gestion des erreurs

| Situation | Comportement | Code de sortie |
| --- | --- | --- |
| Fichier d'entrée absent | Message nommant le chemin attendu | 1 |
| Fichier de zéro octet | Message rappelant les colonnes attendues | 1 |
| Colonne obligatoire manquante | Message nommant la colonne | 1 |
| Montant illisible | Avertissement, écart `amount_invalid` | 0 |
| Doublons de clés | Avertissement, traitement poursuivi | 0 |
| Modèle de langage injoignable | Bascule sur les règles déterministes | 0 |
| Réponse du modèle inexploitable | Bascule sur la règle de l'écart concerné | 0 |
| Erreur non prévue | Journalisation avec pile d'appels | 1 |

La ligne de partage est la suivante : ce qui met en cause l'intégrité des données arrête le traitement, ce qui ne concerne qu'un enrichissement le laisse se poursuivre en mode dégradé.

## 6. Sécurité

Les défenses sont regroupées dans `security.py` et appliquées aux points de sortie plutôt qu'à la lecture. Assainir à l'entrée altérerait les données métier ; assainir à l'écriture ne modifie que ce qui serait dangereux dans le contexte de destination.

### 6.1 Injection de formule dans les livrables

C'est le risque principal de cette chaîne, et il était réalisé.

Les libellés de contrepartie et de produit proviennent de systèmes tiers. Une valeur commençant par un signe égal était écrite par openpyxl non pas comme du texte mais comme une formule, dans un élément `<f>` du classeur. Une contrepartie nommée `=cmd|'/c calc.exe'!A0` devenait ainsi une formule d'échange dynamique de données, exécutée sur le poste de l'analyste ouvrant le rapport et acceptant l'invite d'Excel. Le même mécanisme s'appliquait aux fichiers CSV, que la procédure d'exploitation invite explicitement à ouvrir d'un double-clic.

Toute valeur textuelle commençant par `=`, `+`, `-`, `@`, une tabulation ou un retour chariot est désormais préfixée d'une apostrophe avant écriture, ce qui force le mode texte. Les valeurs légitimes ne commencent jamais par ces caractères et ne sont donc pas touchées. L'apostrophe reste visible, ce qui signale à l'analyste que la donnée reçue était anormale.

La détection des colonnes à traiter mérite une mention. Une première version sélectionnait les colonnes de type `object`. Or les versions récentes de pandas emploient un type `str` dédié pour les chaînes, et la protection était donc silencieusement inopérante : elle ne levait aucune erreur et ne traitait rien. Le test porte désormais sur ce qu'une colonne ne peut pas contenir, à savoir un type numérique, booléen ou de date, plutôt que sur le type des chaînes.

### 6.2 Secrets

Aucun identifiant ne figure dans le code. Les paramètres du modèle de langage proviennent de variables d'environnement ou d'un fichier `.env` exclu du dépôt par `.gitignore`.

Les messages d'exception des bibliothèques réseau reprennent volontiers l'adresse appelée. Si un jeton figure dans cette adresse, il se retrouverait en clair dans les journaux, qui sont conservés et transmis au support en cas d'incident. Tout message d'erreur réseau est donc filtré avant journalisation, les valeurs suivant `api_key`, `token`, `secret`, `password`, `authorization` ou `Bearer` étant remplacées par un marqueur.

### 6.3 Transport

Une adresse de modèle non chiffrée ferait circuler le jeton en clair sur le réseau. L'adresse est validée avant tout appel : seul `https` est accepté, à l'exception des adresses locales qui restent utilisables pour les essais. Les schémas autres que `http` et `https`, tel `file`, sont refusés.

### 6.4 Consigne envoyée au modèle

La consigne interpole des données non fiables. Une contrepartie contenant un retour à la ligne suivi d'un texte impératif pourrait se faire passer pour une instruction. Les valeurs sont donc débarrassées de leurs retours à la ligne, bornées en longueur et isolées dans un bloc délimité, la consigne précisant que ce bloc est de la donnée et non des instructions.

Cette protection réduit le risque sans l'annuler : aucune délimitation textuelle n'est infaillible face à un modèle de langage. C'est pourquoi le texte renvoyé par le service est lui-même traité comme non fiable, borné en longueur et assaini avant écriture dans les livrables.

### 6.5 Consommation de ressources

La réponse du service est lue en flux et interrompue au-delà de deux cent mille octets, un service compromis ou défaillant ne pouvant ainsi pas saturer la mémoire. Le délai d'attente de chaque appel est borné. Les valeurs textuelles excédant deux mille caractères sont tronquées avant écriture.

La taille des fichiers d'entrée n'est en revanche pas bornée. Le traitement s'exécutant sur des extractions internes et non sur des dépôts ouverts, ce point est accepté en l'état et documenté comme limite.

### 6.6 Portée

Les données manipulées sont synthétiques. En production, les extractions et les livrables contiendraient des données de marché soumises à des restrictions d'accès, et devraient résider dans un espace dont les droits sont gérés au niveau du système de fichiers.

## 7. Tests

La suite compte soixante scénarios répartis en trois fichiers.

Le rapprochement est vérifié sur le cas nominal, l'écart de montant au-dessus et en dessous de la tolérance, l'absence de transaction dans chacun des deux systèmes, la divergence de devise, le montant illisible, le montant saisi sous forme de texte et les clés comportant des espaces superflus. Le calcul des indicateurs est vérifié avec et sans écart, y compris sur l'exposition cumulée. Les contrôles d'entrée sont vérifiés sur le fichier absent, le fichier vide et la colonne manquante, en utilisant un répertoire temporaire pour ne pas dépendre des fichiers du dépôt.

L'export décisionnel est vérifié sur la stabilité du schéma, la conservation de chaque exécution, le calcul de l'ancienneté, l'absence de collision entre clés d'écart, la reconstruction des historiques corrompus et la continuité du calendrier.

Les tests de sécurité constituent le troisième ensemble. Ils rejouent les charges utiles d'injection de formule sur la chaîne complète et vérifient qu'aucune cellule du classeur produit n'est stockée comme formule, contrôle qui échouait avant correction. Ils couvrent également le masquage des identifiants dans les journaux, le refus des adresses non chiffrées, l'isolement des données non fiables dans la consigne et le bornage des réponses du modèle.

Ces tests ne sont pas décoratifs : c'est l'un d'eux qui a révélé que la première version de la neutralisation ne s'appliquait à aucune colonne.

```bash
pytest tests/ -v
```

## 8. Performance et évolutivité

Le traitement charge les deux fichiers en mémoire et parcourt le résultat de la fusion ligne par ligne. Sur le jeu de données de référence, l'exécution complète prend moins d'une seconde.

Ce parcours ligne par ligne est le facteur limitant. Il a été conservé parce que la logique de décision y reste lisible, ce qui compte davantage qu'une optimisation prématurée à ce volume. Au-delà d'environ cinquante mille transactions, la comparaison des montants devrait être vectorisée : le calcul de la différence et le classement des natures peuvent s'exprimer en opérations sur colonnes entières, la construction du tableau des écarts se faisant ensuite en une seule passe.

Pour des volumes très supérieurs, la lecture par blocs et le traitement par lots de dates seraient à envisager.

## 9. Dépendances

| Bibliothèque | Rôle |
| --- | --- |
| pandas | Manipulation des tableaux et fusion |
| numpy | Support numérique de pandas |
| openpyxl | Écriture du classeur Excel |
| xlsxwriter | Moteur Excel alternatif |
| requests | Appels au modèle de langage |
| python-dotenv | Chargement du fichier `.env` |
| pytest | Suite de tests |
| python-json-logger | Journalisation structurée |

## 10. Évolutions envisagées

Le rapprochement partiel, permettant qu'une transaction d'un système soit soldée par plusieurs lignes de l'autre, est la demande fonctionnelle la plus attendue.

Le rapprochement des couples symétriques de type divergence de date pourrait être proposé automatiquement, en signalant à l'analyste les paires portant le même identifiant sans les rapprocher d'office.

L'historisation des exécutions dans une base permettrait de suivre l'évolution du taux de rapprochement dans le temps, aujourd'hui limitée à la comparaison manuelle des livrables successifs.

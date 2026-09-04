# Grille de sélection des processus candidats

**Version :** 1.0
**Date :** 2 septembre 2026
**Objet :** Méthode d'identification, de notation et d'arbitrage des processus candidats à l'automatisation

---

## 1. Pourquoi une grille

Un programme d'automatisation échoue rarement pour des raisons techniques. Il échoue parce qu'on a automatisé le mauvais processus.

Trois échecs reviennent constamment. Le robot construit sur un processus trop peu volumineux, dont le coût de développement et de maintenance dépasse le gain. Le robot construit sur un processus instable, qui tombe à la première évolution de l'application sous-jacente et mobilise plus de temps de maintenance qu'il n'en fait économiser. Et le robot construit sur un processus reposant sur le jugement humain, qui automatise en réalité les contournements que les équipes avaient inventés pour compenser un processus mal conçu.

Ces trois échecs se décident au cadrage, pas au développement. D'où cette grille : elle rend le raisonnement explicite, comparable d'un processus à l'autre, et opposable en comité.

La grille ne décide pas à la place du comité. Elle instruit le dossier.

## 2. Les données collectées

Chaque processus candidat est décrit par treize attributs, recueillis auprès du secteur opérationnel concerné.

| Attribut | Nature | Rôle |
| --- | --- | --- |
| `process_id` | Identifiant | Référence du processus |
| `nom` | Libellé | Désignation métier |
| `secteur` | CMO, GRM, FTO, TBS-CMS, TBS-SCS | Rattachement organisationnel |
| `perimetre` | France ou International | Portée géographique |
| `volumetrie_annuelle` | Nombre | Occurrences traitées par an |
| `temps_unitaire_min` | Minutes | Durée moyenne d'un traitement |
| `taux_regles` | Pourcentage | Part du traitement suivant des règles explicites |
| `stabilite` | 1 à 5 | Stabilité du processus dans le temps |
| `structuration_donnees` | structuré, semi-structuré, non structuré | Nature des données d'entrée |
| `nb_applications` | Nombre | Applications traversées |
| `api_disponible` | oui ou non | Existence d'une interface applicative |
| `criticite_reglementaire` | 1 à 5 | Exposition réglementaire |
| `taux_erreur_actuel` | Pourcentage | Taux d'erreur constaté aujourd'hui |

Les deux attributs les plus difficiles à obtenir sont aussi les plus déterminants. La volumétrie réelle est souvent surestimée par les équipes, qui raisonnent sur les pics et non sur la moyenne. Le taux de règles est presque toujours surestimé lui aussi : il faut demander explicitement quelle proportion des dossiers sort du cas nominal, et non se contenter d'une description du cas nominal.

## 3. Les deux axes de notation

### 3.1 Axe valeur

Il répond à la question : que gagne-t-on à automatiser ce processus.

| Critère | Poids | Calcul |
| --- | --- | --- |
| Charge | 55 % | Volumétrie multipliée par le temps unitaire, convertie en équivalents temps plein, plafonnée à cinq ETP |
| Criticité réglementaire | 25 % | Note sur cinq ramenée sur cent |
| Taux d'erreur actuel | 20 % | Plafonné à cinq pour cent |

La charge domine parce qu'elle détermine le gain. Les deux autres critères modulent la priorité : à gain équivalent, un processus exposé réglementairement ou générant beaucoup d'erreurs passe devant.

Le plafonnement de la charge à cinq ETP est délibéré. Au-delà, un processus est de toute façon prioritaire, et distinguer huit ETP de douze n'apporte rien à l'arbitrage tout en écrasant les autres critères.

### 3.2 Axe faisabilité

Il répond à la question : sait-on automatiser ce processus de façon durable.

| Critère | Poids | Calcul |
| --- | --- | --- |
| Taux de règles | 40 % | Pourcentage repris tel quel |
| Stabilité | 25 % | Note sur cinq ramenée sur cent |
| Structuration des données | 20 % | Structuré 100, semi-structuré 60, non structuré 20 |
| Nombre d'applications | 15 % | Cent vingt moins vingt par application, borné |

Le taux de règles domine parce qu'un processus reposant sur le jugement humain ne s'automatise pas, quelle que soit la qualité des autres critères.

Le nombre d'applications est pénalisant car chaque application supplémentaire ajoute une interface à maintenir et un point de rupture. Au-delà de cinq, la fragilité du robot devient la première cause d'indisponibilité du service rendu.

## 4. Les critères éliminatoires

C'est le point le plus important de la méthode, et celui qu'une notation par moyenne pondérée manque systématiquement.

Une moyenne permet à un bon score de compenser un mauvais. Or trois critères ne se compensent pas : ils ferment une option, quelle que soit la qualité du reste du dossier.

**L'existence d'une interface applicative.** Lorsqu'un système expose une API, faire piloter son écran par un robot est un contresens technique. L'intégration directe est plus rapide, plus fiable et moins coûteuse à maintenir. Ce contrôle passe donc avant tous les autres, y compris pour un processus par ailleurs excellent candidat. C'est aussi le contrôle qui protège le programme du reproche le plus fréquemment adressé à la RPA : masquer une dette d'intégration au lieu de la traiter.

**La structuration des données.** Un robot ne sait pas lire un document. Un processus alimenté par des documents non structurés ne peut jamais partir en automatisation classique, même s'il est volumineux, stable et traverse peu d'applications. Il relève d'un projet hybride, où une brique de reconnaissance documentaire précède le robot.

**Le taux de règles.** En dessous de soixante pour cent, l'automatisation directe est exclue. Automatiser un processus dont quatre dossiers sur dix sortent du cas nominal revient à figer les contournements existants et à créer un robot qui échoue en permanence. Le processus doit d'abord être simplifié.

Ces trois règles ont été ajoutées après coup. La première version de la grille reposait uniquement sur les moyennes pondérées, et classait en automatisation directe un processus sur données non structurées dont la stabilité compensait le handicap. C'est un test qui l'a révélé.

## 5. Les six orientations

| Orientation | Priorité | Condition |
| --- | --- | --- |
| Automatiser en RPA | 1 | Valeur et faisabilité au-dessus des seuils, données structurées ou semi-structurées, taux de règles suffisant |
| Projet hybride RPA et IA | 2 | Valeur suffisante, données non structurées, taux de règles au moins de quarante pour cent |
| Intégration applicative | 3 | Une interface applicative existe |
| Optimiser avant d'automatiser | 4 | Valeur suffisante mais processus instable, trop dispersé ou trop dépendant du jugement humain |
| Backlog opportuniste | 5 | Faisabilité bonne mais gain limité |
| Écarter | 6 | Charge insuffisante, ou ni gain ni faisabilité |

Le classement applique la priorité avant la charge. Un projet hybride passe donc après une automatisation classique même lorsque son gisement est supérieur.

Ce choix se discute et doit être assumé devant le comité. Il repose sur le fait qu'un projet hybride est plus long, plus coûteux et plus incertain qu'une automatisation classique, et qu'un programme a intérêt à sécuriser ses premiers gains avant d'engager ses chantiers complexes. Un comité qui privilégierait le gisement maximal inverserait cet ordre, ce que la grille permet en modifiant les priorités dans la configuration.

## 6. Seuils appliqués

| Paramètre | Valeur | Justification |
| --- | --- | --- |
| Seuil de valeur | 50 sur 100 | En deçà, le gain ne justifie pas la mobilisation d'une équipe projet |
| Seuil de faisabilité | 60 sur 100 | En deçà, le risque d'échec en production devient supérieur au gain attendu |
| Charge minimale | 0,5 ETP | En deçà, le coût de construction et de maintenance dépasse le gain |
| Taux de règles minimal | 60 % | Critère éliminatoire pour l'automatisation directe |
| Taux de règles pour un projet hybride | 40 % | En deçà, même assistée, la chaîne resterait manuelle |
| Heures annuelles par ETP | 1 600 | Base de conversion de la charge |

Tous ces seuils sont regroupés dans `src/config.py` et doivent être revus après les premiers déploiements, à la lumière des gains réellement constatés.

## 7. Utilisation

Le référentiel des candidats se trouve dans `data/input/processus_candidats.csv`.

```bash
python src/evaluer_processus.py
```

Le traitement produit un classeur `data/output/evaluation_processus.xlsx` comportant quatre feuilles : le classement arbitré, une synthèse par orientation, une synthèse par secteur et le détail de la notation critère par critère. La table `data/powerbi/dim_processus.csv` alimente le rapport décisionnel.

La feuille de détail existe pour une raison précise : lorsqu'un responsable de secteur conteste l'orientation de son processus, la discussion doit porter sur les données collectées et non sur la note finale. Le détail permet de reprendre chaque critère et, le cas échéant, de corriger une donnée mal recueillie.

## 8. Lecture des résultats sur le portefeuille livré

Le référentiel d'exemple comporte vingt processus répartis sur les cinq secteurs, représentant quarante-cinq ETP de charge manuelle.

Onze processus sont retenus, soit trente-sept ETP de charge adressable. Sept relèvent d'une automatisation classique et quatre d'un projet hybride.

Trois enseignements méritent d'être portés en comité.

Les deux plus gros gisements, le traitement des factures fournisseurs en affacturage et le contrôle documentaire des crédits documentaires, sont tous deux des projets hybrides. Le programme ne peut donc pas atteindre ses objectifs de gain avec la seule RPA : la brique de reconnaissance documentaire est une condition, pas une option. C'est exactement le sens des projets hybrides mentionnés dans la feuille de route.

Trois processus sortent du périmètre RPA parce qu'une interface applicative existe. Ils sont à réorienter vers les équipes d'intégration. Leur charge cumulée est faible, ce qui confirme que la question relève de la doctrine et non du volume.

Le secteur GRM présente le plus faible taux de conversion : quatre processus recensés pour un seul retenu. Ce n'est pas un mauvais résultat, c'est un signal. Les processus de gestion de référentiel sont volumineux mais fortement dépendants du contrôle humain, et leur gisement se situe davantage dans la qualité des données amont que dans l'automatisation du geste.

## 9. Limites

La grille note ce qu'on lui déclare. Une volumétrie surestimée produit une priorité surestimée, et aucun contrôle automatique ne peut le détecter. La qualité du recueil reste le premier facteur de fiabilité, ce qui justifie de faire valider chaque fiche par le responsable du secteur concerné.

La grille n'évalue pas le coût de construction. Elle mesure le gain potentiel et la faisabilité, pas le retour sur investissement. Deux processus de faisabilité identique peuvent demander des charges de développement très différentes, et l'arbitrage final doit intégrer une estimation de charge projet que la grille ne fournit pas.

Enfin, elle traite chaque processus isolément. Deux processus voisins partageant les mêmes applications se construisent bien plus vite ensemble que séparément, effet de série que le classement ne reflète pas.

# Scénarios de recette

**Solution :** Réconciliation des transactions et production des indicateurs de pilotage
**Version :** 2.0
**Date :** 2 septembre 2026

---

## Préparation

Avant de dérouler les scénarios, installez l'environnement et vérifiez que la suite automatisée passe intégralement.

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pytest tests/ -v
```

Les quinze tests doivent passer. Un échec à ce stade rend inutile la suite de la recette.

Chaque scénario s'exécute dans un répertoire d'entrée dédié afin de ne pas altérer le jeu de données de référence.

```bash
python src/main.py --input-dir <repertoire_du_scenario> --output-dir <repertoire_de_sortie>
```

La colonne « code retour » indique la valeur attendue de `%ERRORLEVEL%` sous Windows ou de `$?` sous Linux.

---

## Famille 1, cas nominaux

### TC01, rapprochement parfait

**Objectif** Vérifier qu'aucun écart n'est signalé lorsque les deux systèmes concordent.

**Données** Deux fichiers strictement identiques comportant dix transactions.

**Résultat attendu** Dix transactions rapprochées, aucun écart, taux de rapprochement de cent pour cent, exposition nulle. Le classeur ne contient pas de feuille de détail des écarts. Code retour 0.

### TC02, jeu de données de référence

**Objectif** Vérifier le comportement d'ensemble sur le jeu livré.

**Données** Les fichiers présents dans `data/input`.

**Résultat attendu** Trente transactions chargées de chaque côté, vingt-deux rapprochées, douze écarts, taux de rapprochement de 64,71 pour cent. Le classeur comporte six feuilles. Code retour 0.

**Vérification complémentaire** Ouvrir le classeur et contrôler que la répartition par nature affiche quatre écarts de montant, quatre transactions absentes du Système A et quatre absentes du Système B.

---

## Famille 2, détection des écarts

### TC03, écart de montant

**Objectif** Vérifier qu'une divergence de montant est détectée et qualifiée.

**Données** Une transaction identique de part et d'autre, sauf le montant : 500 000,00 contre 500 000,50.

**Résultat attendu** Aucun rapprochement, un écart de nature `amount`. Le motif indique une erreur de saisie du montant et l'action nomme la contrepartie concernée. Confiance de 0,8. Code retour 0.

### TC04, écart inférieur à la tolérance

**Objectif** Vérifier que la tolérance absorbe bien les écarts d'arrondi.

**Données** Une transaction identique de part et d'autre, sauf le montant : 500 000,000 contre 500 000,005.

**Résultat attendu** Une transaction rapprochée, aucun écart. La différence de un demi-centime reste sous la tolérance. Code retour 0.

### TC05, transaction absente du Système B

**Objectif** Vérifier la détection d'une transaction non comptabilisée.

**Données** Une transaction présente uniquement dans le Système A.

**Résultat attendu** Un écart de nature `missing_B`, motif indiquant l'absence dans le Système B, action orientant vers le back office. Confiance de 0,9. Code retour 0.

### TC06, transaction absente du Système A

**Objectif** Vérifier la détection symétrique.

**Données** Une transaction présente uniquement dans le Système B.

**Résultat attendu** Un écart de nature `missing_A`, action orientant vers le front office. Code retour 0.

### TC07, divergence de devise

**Objectif** Vérifier qu'une divergence sur une clé de rapprochement ne produit pas de faux rapprochement.

**Données** Une transaction identique de part et d'autre, sauf la devise : EUR contre USD.

**Résultat attendu** Aucun rapprochement, deux écarts symétriques portant le même identifiant, l'un `missing_A` et l'autre `missing_B`. Code retour 0.

**Point d'attention** Ce comportement est volontaire et doit être expliqué aux utilisateurs pendant la recette, faute de quoi il sera pris pour un défaut. La règle RG01 du document métier en donne la justification.

### TC08, divergence de date

**Objectif** Vérifier le comportement sur un décalage de date de négociation.

**Données** Une transaction identique de part et d'autre, sauf la date : 10 août contre 11 août.

**Résultat attendu** Deux écarts symétriques portant le même identifiant, comme au scénario TC07. Code retour 0.

---

## Famille 3, robustesse des données

### TC09, montant absent des deux côtés

**Objectif** Vérifier qu'une donnée manquante n'est jamais validée par défaut.

**Données** Une transaction identique de part et d'autre, la colonne montant étant vide dans les deux fichiers.

**Résultat attendu** Aucun rapprochement, un écart de nature `amount_invalid`. Le journal porte un avertissement signalant le montant illisible. Code retour 0.

**Point d'attention** Ce scénario couvre une anomalie corrigée en version 2.0. Auparavant, la comparaison de deux valeurs indéterminées s'évaluait à faux et la transaction était comptée comme correctement rapprochée.

### TC10, montant saisi sous forme de texte

**Objectif** Vérifier la conversion des types.

**Données** Un montant écrit `"1000000.00"` avec guillemets d'un côté, sous forme numérique de l'autre.

**Résultat attendu** Une transaction rapprochée, aucun écart. Code retour 0.

### TC11, espaces superflus dans les clés

**Objectif** Vérifier la normalisation des clés.

**Données** Un identifiant saisi ` TR001 ` d'un côté et `TR001` de l'autre.

**Résultat attendu** Une transaction rapprochée, aucun écart. Code retour 0.

### TC12, doublons de clés

**Objectif** Vérifier que l'exploitant est prévenu du risque.

**Données** Un fichier contenant deux fois la même combinaison de clés.

**Résultat attendu** Le traitement se poursuit et produit les livrables. Le journal porte un avertissement recommandant de dédoublonner le fichier source. Code retour 0.

### TC13, Système B totalement vide

**Objectif** Vérifier le comportement quand une extraction amont a échoué.

**Données** Un Système A garni de dix transactions, un Système B ne contenant que sa ligne d'en-tête.

**Résultat attendu** Dix écarts de nature `missing_B`, taux de rapprochement de zéro pour cent. Code retour 0.

**Point d'attention** Un taux de rapprochement nul signale presque toujours un incident technique en amont plutôt qu'une véritable dégradation de la qualité des saisies.

---

## Famille 4, gestion des erreurs

### TC14, fichier d'entrée absent

**Objectif** Vérifier la clarté du message d'erreur.

**Données** Un répertoire d'entrée ne contenant aucun fichier.

**Résultat attendu** Le traitement s'arrête. Le message nomme le chemin complet du fichier attendu. Le relevé d'erreurs contient une ligne de type `FileNotFoundError`. Code retour 1.

### TC15, fichier de zéro octet

**Objectif** Vérifier que le message reste exploitable par un non-technicien.

**Données** Un fichier `transactions_systemA.csv` totalement vide.

**Résultat attendu** Le traitement s'arrête sur un message précisant que le fichier est vide et rappelant la liste des colonnes attendues. Code retour 1.

**Point d'attention** Sans ce contrôle, la bibliothèque de lecture renvoie un message obscur pour un exploitant.

### TC16, colonne obligatoire manquante

**Objectif** Vérifier l'identification de la colonne fautive.

**Données** Un fichier privé de sa colonne `currency`.

**Résultat attendu** Le traitement s'arrête sur un message nommant explicitement la colonne `currency` et le système concerné. Code retour 1.

### TC17, répertoire de sortie inexistant

**Objectif** Vérifier que le répertoire est créé automatiquement.

**Données** Un chemin de sortie pointant vers un répertoire absent.

**Résultat attendu** Le répertoire est créé et les trois livrables y sont déposés. Code retour 0.

---

## Famille 5, qualification par modèle de langage

### TC18, absence de configuration

**Objectif** Vérifier le mode de fonctionnement par défaut.

**Données** Aucune variable `LLM_API_URL` définie.

**Résultat attendu** Le journal indique qu'aucun modèle n'est configuré et que la classification s'appuie sur les règles. Tous les écarts sont qualifiés. Code retour 0.

### TC19, modèle configuré mais injoignable

**Objectif** Vérifier la continuité de service.

**Données** Une variable `LLM_API_URL` pointant vers une adresse inaccessible.

**Résultat attendu** Le journal porte un avertissement par écart, puis la classification par règles s'applique. Les trois livrables sont produits normalement. Code retour 0.

**Point d'attention** C'est le scénario le plus important de cette famille. Une indisponibilité du modèle ne doit jamais empêcher la production du rapport quotidien.

---

## Famille 6, contrôle des livrables

### TC20, structure du classeur Excel

**Objectif** Vérifier la conformité du livrable principal.

**Résultat attendu** Le classeur comporte les feuilles `Synthese_KPI`, `Detail_ecarts`, `Ecarts_par_nature`, `Ecarts_par_motif`, `Ecarts_par_contrepartie` et `Ecarts_par_produit`. Les colonnes sont ajustées au contenu. Les accents s'affichent correctement.

### TC21, synthèse texte

**Objectif** Vérifier la lisibilité du livrable de reporting.

**Résultat attendu** Le fichier `summary.txt` présente les cinq indicateurs clés puis les trois premières valeurs de chaque répartition. Les accents s'affichent correctement à l'ouverture dans un éditeur de texte.

### TC22, relevé d'erreurs en cas de succès

**Objectif** Vérifier la présence systématique du fichier.

**Résultat attendu** Le fichier `errors_summary.csv` existe et ne contient que sa ligne d'en-tête.

### TC23, journal d'exécution

**Objectif** Vérifier la traçabilité.

**Résultat attendu** Un fichier horodaté est créé dans `logs/`. Il retrace les cinq étapes, les volumes chargés et les résultats. Les accents s'y affichent correctement.

---

## Grille de dépouillement

| Scénario | Objet | Résultat | Observations |
| --- | --- | --- | --- |
| TC01 | Rapprochement parfait | | |
| TC02 | Jeu de référence | | |
| TC03 | Écart de montant | | |
| TC04 | Écart sous tolérance | | |
| TC05 | Absente du Système B | | |
| TC06 | Absente du Système A | | |
| TC07 | Divergence de devise | | |
| TC08 | Divergence de date | | |
| TC09 | Montant absent | | |
| TC10 | Montant textuel | | |
| TC11 | Espaces superflus | | |
| TC12 | Doublons de clés | | |
| TC13 | Système B vide | | |
| TC14 | Fichier absent | | |
| TC15 | Fichier vide | | |
| TC16 | Colonne manquante | | |
| TC17 | Répertoire de sortie absent | | |
| TC18 | Sans modèle configuré | | |
| TC19 | Modèle injoignable | | |
| TC20 | Structure du classeur | | |
| TC21 | Synthèse texte | | |
| TC22 | Relevé d'erreurs | | |
| TC23 | Journal d'exécution | | |

## Critères de prononcé de la recette

La recette est prononcée lorsque les vingt-trois scénarios sont conformes et que la suite automatisée passe intégralement.

Un écart constaté sur un scénario des familles 1 à 4 est bloquant, car il met en cause l'exactitude du rapprochement ou la clarté du diagnostic en cas d'incident. Un écart sur les familles 5 et 6 est à arbitrer selon son impact sur l'exploitation courante.

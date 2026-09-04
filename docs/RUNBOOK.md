# Procédure d'exploitation

**Traitement :** Réconciliation des transactions et production des indicateurs de pilotage
**Version :** 2.0
**Date :** 2 septembre 2026
**Destinataires :** Analystes des opérations et support informatique

---

## 1. Objet

Ce document décrit l'exploitation courante du traitement quotidien de rapprochement : préparation, lancement, contrôles de bonne fin et conduite à tenir en cas d'incident.

## 2. Prérequis

Python 3.9 ou une version plus récente, avec les dépendances installées.

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Les deux extractions doivent être déposées dans `data/input` sous les noms exacts `transactions_systemA.csv` et `transactions_systemB.csv`. Le traitement ne cherche pas d'autres noms et ne devine pas le format.

La configuration du modèle de langage est facultative. En son absence, la qualification des écarts s'appuie sur les règles déterministes, ce qui reste un mode de fonctionnement complet.

## 3. Lancement quotidien

```bash
python src/main.py
```

Pour un lancement sur des répertoires particuliers, par exemple lors d'un rejeu.

```bash
python src/main.py --input-dir data/input --output-dir data/output
```

Pour un diagnostic détaillé.

```bash
python src/main.py --log-level DEBUG
```

Le traitement dure quelques secondes sur un volume de l'ordre de la dizaine de milliers de transactions.

## 4. Contrôles de bonne fin

Quatre contrôles sont à effectuer après chaque exécution.

**Le code retour.** Il doit valoir 0. Sous Windows, `echo %ERRORLEVEL%` immédiatement après le lancement. Une valeur de 1 signale un arrêt sur erreur et impose de consulter le journal.

**La présence des livrables.** Les trois fichiers `kpi_report.xlsx`, `summary.txt` et `errors_summary.csv` doivent être présents dans `data/output` avec l'horodatage du jour.

**Le relevé d'erreurs.** Le fichier `errors_summary.csv` ne doit contenir que sa ligne d'en-tête. Toute ligne supplémentaire décrit une erreur survenue pendant le traitement.

**Le taux de rapprochement.** Il figure en tête de `summary.txt`. Une valeur très inférieure à celle de la veille appelle une vérification avant diffusion du rapport.

## 5. Interprétation du taux de rapprochement

Un taux nul ou proche de zéro traduit presque toujours un incident d'alimentation, une extraction ayant échoué ou porté sur la mauvaise date, plutôt qu'une dégradation réelle de la qualité des saisies. Vérifiez d'abord les volumes chargés dans le journal : deux volumes très déséquilibrés confirment l'hypothèse.

Une baisse marquée mais partielle, par exemple de quatre-vingt-quinze à soixante pour cent, oriente vers un changement de format sur une colonne servant de clé. Une modification du format de date ou du libellé d'une contrepartie dans un système suffit à empêcher le rapprochement de toutes les lignes concernées.

Une baisse progressive sur plusieurs jours relève en revanche d'une vraie dérive opérationnelle et doit être remontée au responsable des opérations.

## 6. Incidents courants

### Fichier d'entrée introuvable

**Message** `Fichier d'entrée introuvable : ...`

**Cause** L'extraction amont n'a pas été déposée, ou son nom ne correspond pas exactement à celui attendu.

**Conduite à tenir** Vérifier la présence et le nom des deux fichiers dans `data/input`. Relancer l'extraction amont si nécessaire, puis relancer le traitement.

### Fichier vide

**Message** `Le fichier du Système A est vide : ...`

**Cause** L'extraction s'est terminée sans écrire de contenu, généralement à la suite d'un échec de connexion au système source.

**Conduite à tenir** Relancer l'extraction. Ne pas tenter de contourner en fabriquant un fichier à la main.

### Colonne obligatoire manquante

**Message** `Colonnes obligatoires manquantes dans le Système B : currency`

**Cause** Le format de l'extraction a changé, le plus souvent après une mise à jour du système source.

**Conduite à tenir** Ouvrir une demande auprès de l'équipe responsable de l'extraction. Ce n'est pas un incident que l'exploitant peut résoudre seul.

### Avertissement sur des montants illisibles

**Message** `Système A : 3 montant(s) illisible(s) ou absent(s)`

**Cause** Des cellules de montant sont vides ou contiennent du texte.

**Conduite à tenir** Le traitement se poursuit et signale ces transactions en écart de nature `amount_invalid`. Les remonter à l'équipe responsable de la qualité des données.

### Avertissement sur des doublons de clés

**Message** `Système B : 5 ligne(s) partagent les mêmes clés de rapprochement`

**Cause** L'extraction contient des lignes en double, souvent parce qu'elle a été relancée sans purge préalable.

**Conduite à tenir** Le traitement se poursuit mais les volumes sont gonflés. Dédoublonner l'extraction et relancer avant de diffuser le rapport.

### Échec des appels au modèle de langage

**Message** `Échec de la classification par modèle de langage ..., bascule sur la classification par règles`

**Cause** Service indisponible, jeton expiré ou délai d'attente dépassé.

**Conduite à tenir** Aucune action urgente. Les livrables sont produits normalement avec la qualification par règles. Signaler l'indisponibilité au support pour rétablissement.

### Erreur inattendue

**Message** `Erreur inattendue : ...` suivi d'une pile d'appels.

**Conduite à tenir** Transmettre au support informatique le fichier de journal de `logs/` correspondant à l'exécution, ainsi que les deux fichiers d'entrée. La pile d'appels contient l'information nécessaire au diagnostic.

## 7. Rejeu d'une exécution

Les livrables étant écrasés à chaque exécution, un rejeu sur les mêmes données est sans effet de bord. Pour conserver une exécution précédente, dirigez la sortie vers un autre répertoire.

```bash
python src/main.py --output-dir data/output/2026-09-02
```

## 8. Archivage

Les journaux s'accumulent dans `logs/`, à raison d'un fichier par exécution. Une purge périodique des fichiers de plus de quatre-vingt-dix jours est recommandée, en tenant compte de la durée de conservation exigée par le contrôle interne.

Les livrables destinés à être conservés doivent être copiés hors de `data/output`, puisque ce répertoire est écrasé à chaque exécution.

## 9. Escalade

| Situation | Interlocuteur | Délai |
| --- | --- | --- |
| Extraction amont absente ou vide | Équipe d'extraction | Immédiat |
| Changement de format d'une extraction | Équipe d'extraction | Jour ouvré |
| Taux de rapprochement anormalement bas | Responsable des opérations | Immédiat |
| Erreur inattendue du traitement | Support informatique | Immédiat |
| Modèle de langage indisponible | Support informatique | Jour ouvré |

## 10. Documents liés

La description métier du processus figure dans [PDD_ProcessReconciliation.md](PDD_ProcessReconciliation.md).
La conception technique figure dans [SDD_SolutionDesign.md](SDD_SolutionDesign.md).
Les scénarios de recette figurent dans [UAT_scenarios.md](UAT_scenarios.md).

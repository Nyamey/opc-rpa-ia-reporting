# Rapport Power BI

**Version :** 1.0
**Date :** 2 septembre 2026

---

## 1. Ce que produit la chaîne

Le traitement écrit deux jeux de fichiers qui n'ont pas le même usage.

Le répertoire `data/output` contient les livrables destinés à la lecture
humaine : le classeur Excel, la synthèse texte et le relevé d'erreurs. Leur
structure s'adapte au contenu, les feuilles vides disparaissant du classeur.

Le répertoire `data/powerbi` contient les tables destinées au décisionnel.
Elles sont écrites à chaque exécution avec exactement les mêmes colonnes, dans
le même ordre, y compris lorsqu'elles ne contiennent aucune ligne.

Cette séparation est délibérée. Brancher Power BI directement sur le classeur
Excel exposerait le rapport à un échec de rafraîchissement le jour où aucun
écart n'est détecté, puisque la feuille de détail n'est alors pas créée. Un
rapport décisionnel exige un schéma constant.

## 2. Les six tables

| Table | Grain | Renouvellement |
| --- | --- | --- |
| `fact_breaks.csv` | Un écart | Remplacée à chaque exécution |
| `fact_matched.csv` | Une transaction rapprochée | Remplacée à chaque exécution |
| `fact_breaks_history.csv` | Un écart et une journée | Enrichie |
| `kpi_history.csv` | Une exécution | Enrichie |
| `dim_break_type.csv` | Une nature d'écart | Remplacée à chaque exécution |
| `dim_date.csv` | Un jour du calendrier | Remplacée à chaque exécution |

Deux tables s'accumulent. Sans elles, le rapport ne montrerait jamais que la
photographie du jour, puisque les tables de faits sont écrasées à chaque
exécution.

`kpi_history.csv` conserve **toutes** les exécutions, y compris plusieurs le
même jour. Une première version ne gardait qu'une ligne par journée, ce qui
donnait l'impression que l'historique s'effaçait dès qu'on relançait le
traitement. La colonne `est_derniere_du_jour` distingue désormais l'exécution
de référence de chaque journée, ce qui permet de tracer un point par jour tout
en conservant la trace des rejeux.

Ce choix a une conséquence directe sur les mesures : sommer l'historique sans
filtrer sur `est_derniere_du_jour` compterait une même journée autant de fois
qu'elle a été relancée. Toutes les mesures fournies appliquent ce filtre.

`fact_breaks_history.csv` conserve une ligne par écart et par journée où il
était encore ouvert. C'est cette table qui permet de calculer depuis combien de
temps un écart traîne. Son grain est la journée : plusieurs exécutions le même
jour mettent à jour les lignes du jour au lieu de les dupliquer, sans quoi dix
essais successifs feraient croire à dix journées d'ancienneté.

La durée de conservation des deux historiques est réglée par la variable
`HISTORY_RETENTION_DAYS`, à deux ans par défaut. Une valeur nulle ou négative
désactive toute purge.

`dim_date.csv` couvre en continu toutes les dates entre la plus ancienne et la
plus récente rencontrée, dates de négociation, dates d'exécution et dates de
l'historique des écarts comprises, y compris les journées sans transaction.
Cette continuité est nécessaire pour qu'une courbe affiche un creux à zéro au
lieu de sauter la journée.

## 2 bis. Vieillissement des écarts

La table `fact_breaks.csv` porte deux colonnes calculées à partir de
l'historique.

`first_seen_date` donne la journée où l'écart a été détecté pour la première
fois. `days_open` donne le nombre de jours écoulés depuis.

L'identité d'un écart repose sur la transaction, ses attributs et la nature de
la divergence. Le montant en est volontairement exclu : un écart dont le
montant bouge légèrement d'un jour sur l'autre reste le même écart tant que la
transaction et la nature de la divergence ne changent pas.

C'est l'information la plus utile au quotidien. Un écart apparu le matin même
et un écart ouvert depuis huit jours ne relèvent pas du même traitement, et
rien dans la photographie du jour ne permettait jusqu'ici de les distinguer.

## 3. Modèle en étoile

```text
                      dim_date
                          |
    +---------+-----------+-----------+---------------------+
    |         |           |           |                     |
fact_breaks  fact_matched  kpi_history  fact_breaks_history
    |                                            |
    +----------------- dim_break_type -----------+
```

Relations à créer, toutes de un vers plusieurs, à sens unique.

| Depuis | Vers | Cardinalité |
| --- | --- | --- |
| `dim_date[date]` | `fact_breaks[trade_date]` | Un vers plusieurs |
| `dim_date[date]` | `fact_matched[trade_date]` | Un vers plusieurs |
| `dim_date[date]` | `kpi_history[run_date]` | Un vers plusieurs |
| `dim_date[date]` | `fact_breaks_history[run_date]` | Un vers plusieurs |
| `dim_break_type[break_type]` | `fact_breaks[break_type]` | Un vers plusieurs |
| `dim_break_type[break_type]` | `fact_breaks_history[break_type]` | Un vers plusieurs |

Ne créez pas de relation entre `fact_breaks[break_key]` et
`fact_breaks_history[break_key]`. Les deux côtés comportent des doublons, une
relation directe serait donc plusieurs vers plusieurs et ouvrirait des chemins
de filtre ambigus. Le lien entre la photographie du jour et l'historique passe
par les colonnes `first_seen_date` et `days_open`, déjà calculées lors de
l'export.

Les deux relations partant de `dim_date` vers les tables de faits portent sur
la date de négociation, alors que celle vers l'historique porte sur la date
d'exécution. Un même filtre de date répond donc à deux questions différentes
selon le visuel : quelles transactions ont été négociées ce jour-là, et quel
était l'état du rapprochement ce jour-là. Ce point doit être expliqué aux
utilisateurs, faute de quoi il sera pris pour une incohérence.

## 4. Montage du rapport

Le fichier `powerbi/reportings.pbix` présent dans le dépôt fait zéro octet et
ne contient aucun modèle. Power BI Desktop refusera de l'ouvrir. Ne tentez donc
pas de partir de ce fichier : construisez le rapport à partir d'un document
vierge, puis enregistrez-le sous ce nom pour le remplacer.

Les étapes suivantes ne sont à faire qu'une seule fois.

**Créer le paramètre de chemin.** Ouvrez Power BI Desktop, puis Accueil,
Transformer les données, Gérer les paramètres, Nouveau. Nommez le paramètre
`DossierDonnees`, de type Texte, et donnez comme valeur le chemin complet du
répertoire `data/powerbi` du projet. C'est le seul point à modifier si le
projet est déplacé.

**Créer les six requêtes.** Le fichier `powerbi/modele_powerbi.pq` contient un
bloc par table. Pour chacun, créez une requête vide, ouvrez l'Éditeur avancé,
remplacez le contenu par le bloc, et nommez la requête comme indiqué dans son
titre. Fermez et appliquez.

**Marquer la table de dates.** Sélectionnez `dim_date` dans le volet des
données, puis Outils de table, Marquer comme table de dates, en désignant la
colonne `date`. Sans cette déclaration, les fonctions de décalage temporel des
mesures ne fonctionneront pas.

**Régler le tri des mois.** Sélectionnez la colonne `nom_mois`, puis Trier par
colonne, et choisissez `mois_tri`. Sans ce réglage, les visuels classeraient
les mois par ordre alphabétique.

**Créer les relations.** Vérifiez dans la vue Modèle celles que Power BI a
détectées automatiquement et complétez selon le tableau du chapitre 3. Power BI
crée parfois des relations non souhaitées entre colonnes de même nom, comme
`run_id`. Supprimez-les.

**Créer les mesures.** Ajoutez une table `Mesures` via Accueil, Entrer des
données, puis créez les mesures listées dans `powerbi/mesures_dax.md`.

**Enregistrer.** Enregistrez le fichier sous `powerbi/reportings.pbix`.

## 5. Pages suggérées

**Page de synthèse.** Quatre cartes en tête : taux de rapprochement, variation
par rapport à la veille, nombre d'écarts, exposition. En dessous, la courbe du
taux de rapprochement dans le temps, issue de `kpi_history`. À droite, la
répartition des écarts par nature, en utilisant le libellé de
`dim_break_type` et non le code technique.

**Page de détail.** Un tableau alimenté par `fact_breaks`, affichant
l'identifiant, la contrepartie, le produit, les deux montants, l'exposition,
l'ancienneté, le motif et l'action recommandée. Des segments sur la nature
d'écart, la contrepartie, la tranche d'ancienneté et le drapeau de revue
manuelle. Triez par ancienneté décroissante plutôt que par identifiant : ce
sont les écarts les plus anciens qui appellent une action. C'est la page de
travail quotidienne de l'analyste.

**Page de vieillissement.** Un histogramme des écarts par tranche d'ancienneté,
et une carte pour l'exposition des écarts de plus de cinq jours. Cette page
répond à la question que le rapport ne savait pas traiter jusqu'ici : qu'est-ce
qui traîne, et depuis combien de temps. Un montant important immobilisé depuis
plus d'une semaine signale un blocage dans la chaîne de traitement plutôt
qu'une erreur de saisie ordinaire.

**Page de concentration.** Deux graphiques en barres, l'un par contrepartie et
l'autre par produit, ordonnés par exposition plutôt que par nombre d'écarts.
Cinquante écarts de faible montant pèsent moins qu'un seul écart portant sur
plusieurs millions, et c'est l'exposition qui doit guider l'ordre de
traitement.

**Page de qualité.** La part de revue manuelle et la confiance moyenne dans le
temps, plus le compteur d'écarts sans montant exploitable. Cette page suit la
santé du dispositif lui-même plutôt que celle du processus métier.

## 6. Rafraîchissement

Après chaque exécution du traitement, ouvrez le rapport et cliquez sur
Actualiser. Les fichiers étant écrasés en place, aucun réglage n'est à revoir.

Pour un rafraîchissement automatique après publication sur le service Power BI,
les fichiers doivent être accessibles depuis une passerelle de données, ce qui
suppose de les déposer sur un partage réseau plutôt que sur un poste local. Le
paramètre `DossierDonnees` est alors à faire pointer vers ce partage.

## 7. Incidents courants

**Le rafraîchissement échoue en signalant un fichier introuvable.** Le
paramètre `DossierDonnees` pointe vers un chemin qui n'existe pas, ou le
traitement n'a jamais été exécuté. Lancez le traitement une fois, puis
vérifiez la valeur du paramètre.

**Les montants s'affichent comme des entiers à douze chiffres.** Le typage a
été fait sans préciser la culture. Reprenez l'étape de typage en conservant
l'argument `"en-US"` présent dans les requêtes fournies.

**Les accents s'affichent de travers.** L'encodage de la requête n'est pas
65001. Les fichiers sont écrits en UTF-8 avec marque d'ordre des octets.

**La courbe de tendance ne montre qu'un seul point.** C'est normal après une
première exécution. L'historique se remplit au fil des exécutions, et la courbe
prend forme à partir de la deuxième journée traitée.

**Les volumes semblent multipliés.** Une mesure agrège l'historique sans
filtrer sur `est_derniere_du_jour`, et compte donc chaque journée autant de
fois qu'elle a été relancée. Reprenez la définition de la mesure dans
`powerbi/mesures_dax.md`.

**Toutes les anciennetés valent zéro.** L'historique des écarts vient d'être
créé, ou a été supprimé. L'ancienneté se construit au fil des journées et ne
peut pas être reconstituée après coup.

**Le taux de rapprochement tombe à zéro.** Regardez d'abord les volumes chargés
dans le journal du traitement. Deux volumes très déséquilibrés confirment un
incident d'extraction en amont plutôt qu'une dégradation réelle.

## 8. Documents liés

La description métier du processus figure dans [PDD_ProcessReconciliation.md](PDD_ProcessReconciliation.md).
La conception technique figure dans [SDD_SolutionDesign.md](SDD_SolutionDesign.md).
La procédure d'exploitation figure dans [RUNBOOK.md](RUNBOOK.md).

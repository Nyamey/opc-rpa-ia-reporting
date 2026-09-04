# Mesures DAX du rapport

Ces mesures sont à créer dans une table dédiée, ce qui les regroupe au même
endroit plutôt que de les disperser dans les tables de faits. Dans Power BI
Desktop, choisissez Accueil puis Entrer des données, nommez la table `Mesures`,
validez, puis créez chaque mesure ci-dessous.

Les mesures marquées comme portant sur le jour se calculent sur l'exécution
courante. Celles portant sur la tendance s'appuient sur l'historique.

---

## Avertissement sur l'historique

`kpi_history` conserve **toutes** les exécutions, y compris plusieurs le même
jour. Sommer directement ses colonnes compterait donc la même journée autant de
fois qu'elle a été relancée, ce qui gonflerait silencieusement tous les
volumes.

Chaque mesure qui agrège l'historique doit se restreindre à la dernière
exécution de chaque journée. C'est le rôle du filtre commun ci-dessous, repris
dans toutes les mesures concernées.

```dax
Journées retenues =
CALCULATETABLE (
    kpi_history,
    kpi_history[est_derniere_du_jour] = 1
)
```

Cette table n'est pas une mesure à créer : elle décrit la restriction que les
mesures suivantes appliquent.

---

## Volumes

```dax
Transactions traitées =
CALCULATE (
    SUM ( kpi_history[total_transactions] ),
    kpi_history[est_derniere_du_jour] = 1
)
```

```dax
Transactions rapprochées =
CALCULATE (
    SUM ( kpi_history[matched_count] ),
    kpi_history[est_derniere_du_jour] = 1
)
```

```dax
Écarts =
CALCULATE (
    SUM ( kpi_history[breaks_count] ),
    kpi_history[est_derniere_du_jour] = 1
)
```

```dax
Écarts détail =
COUNTROWS ( fact_breaks )
```

```dax
Nombre d'exécutions =
COUNTROWS ( kpi_history )
```

```dax
Rejeux =
COUNTROWS ( kpi_history ) - DISTINCTCOUNT ( kpi_history[run_date] )
```

La mesure `Écarts` provient de l'historique et suit le filtre de date. La
mesure `Écarts détail` compte les lignes réellement présentes dans le détail,
c'est-à-dire celles de la dernière exécution. `Rejeux` indique combien
d'exécutions supplémentaires ont eu lieu, information utile en phase de mise au
point.

---

## Taux de rapprochement

```dax
Taux de rapprochement =
DIVIDE ( [Transactions rapprochées], [Transactions traitées] )
```

À formater en pourcentage avec deux décimales. La division par `DIVIDE` renvoie
un blanc plutôt qu'une erreur lorsque le dénominateur est nul, ce qui arrive le
jour où aucune transaction n'a été traitée.

```dax
Taux de rapprochement veille =
CALCULATE (
    [Taux de rapprochement],
    DATEADD ( dim_date[date], -1, DAY )
)
```

```dax
Variation du taux =
VAR Courant = [Taux de rapprochement]
VAR Veille = [Taux de rapprochement veille]
RETURN
    IF ( NOT ISBLANK ( Veille ), Courant - Veille )
```

Cette variation est l'indicateur à placer en tête du rapport. Une chute
brutale traduit presque toujours un incident d'alimentation en amont plutôt
qu'une dégradation réelle de la qualité des saisies.

---

## Exposition financière

```dax
Exposition des écarts =
SUM ( fact_breaks[break_amount] )
```

```dax
Exposition moyenne par écart =
DIVIDE ( [Exposition des écarts], [Écarts détail] )
```

```dax
Exposition des écarts historisée =
CALCULATE (
    SUM ( kpi_history[total_break_amount] ),
    kpi_history[est_derniere_du_jour] = 1
)
```

---

## Vieillissement des écarts

Ces mesures répondent à la question qui compte le plus au quotidien : cet écart
vient-il d'apparaître, ou traîne-t-il depuis une semaine sans que personne ne
l'ait traité.

```dax
Ancienneté moyenne =
AVERAGE ( fact_breaks[days_open] )
```

```dax
Ancienneté maximale =
MAX ( fact_breaks[days_open] )
```

```dax
Écarts de plus de 5 jours =
CALCULATE (
    COUNTROWS ( fact_breaks ),
    fact_breaks[days_open] > 5
)
```

```dax
Exposition des écarts anciens =
CALCULATE (
    SUM ( fact_breaks[break_amount] ),
    fact_breaks[days_open] > 5
)
```

```dax
Nouveaux écarts du jour =
CALCULATE (
    COUNTROWS ( fact_breaks ),
    fact_breaks[days_open] = 0
)
```

```dax
Écarts résolus depuis la veille =
VAR Veille =
    CALCULATE (
        DISTINCTCOUNT ( fact_breaks_history[break_key] ),
        DATEADD ( dim_date[date], -1, DAY )
    )
VAR Aujourdhui = DISTINCTCOUNT ( fact_breaks[break_key] )
VAR Nouveaux = [Nouveaux écarts du jour]
RETURN
    MAX ( Veille - ( Aujourdhui - Nouveaux ), 0 )
```

La mesure `Exposition des écarts anciens` mérite une carte dédiée. Un montant
important immobilisé depuis plus de cinq jours signale un blocage dans la
chaîne de traitement, pas une simple erreur de saisie.

---

## Qualité de la classification

```dax
Écarts en revue manuelle =
CALCULATE (
    COUNTROWS ( fact_breaks ),
    fact_breaks[revue_manuelle] = "Oui"
)
```

```dax
Part de revue manuelle =
DIVIDE ( [Écarts en revue manuelle], [Écarts détail] )
```

```dax
Confiance moyenne =
AVERAGE ( fact_breaks[confidence] )
```

Une part de revue manuelle qui augmente indique que le système rencontre des
situations qu'il ne sait plus expliquer, ce qui justifie de revoir les règles
de qualification.

---

## Indicateurs de pilotage

```dax
Contrepartie la plus exposée =
VAR Classement =
    TOPN (
        1,
        SUMMARIZE (
            fact_breaks,
            fact_breaks[counterparty],
            "@Exposition", SUM ( fact_breaks[break_amount] )
        ),
        [@Exposition], DESC
    )
RETURN
    MAXX ( Classement, fact_breaks[counterparty] )
```

```dax
Écarts sans montant exploitable =
CALCULATE (
    COUNTROWS ( fact_breaks ),
    fact_breaks[break_type] = "amount_invalid"
)
```

Cette dernière mesure mérite une carte visuelle dédiée. Une valeur non nulle
signale un problème de qualité dans les extractions amont, à traiter avec
l'équipe qui les produit.

---

## Mise en forme conditionnelle suggérée

Pour la carte du taux de rapprochement, appliquez trois seuils : rouge en
dessous de quatre-vingts pour cent, orange entre quatre-vingts et
quatre-vingt-quinze, vert au-dessus. Ces seuils sont à ajuster après quelques
semaines d'observation, une fois connu le niveau habituel du processus.

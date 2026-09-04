# Document de définition du processus

**Processus :** Réconciliation des transactions et production des indicateurs de pilotage
**Version :** 2.0
**Date :** 2 septembre 2026
**Périmètre :** Direction des opérations, activités de marché

---

## 1. Pourquoi ce processus existe

Une banque de financement enregistre une même transaction dans plusieurs systèmes. Le front office la saisit au moment de la négociation. Le back office la reprend pour la comptabiliser, la confirmer auprès de la contrepartie et déclencher le règlement. Entre ces deux enregistrements, tout peut diverger : un montant mal recopié, une date décalée d'un jour ouvré, une devise erronée, une transaction annulée d'un côté et pas de l'autre.

Chaque divergence non détectée porte un risque réel. Un montant faux fausse le calcul du risque de contrepartie. Une transaction absente du back office ne sera jamais réglée. Une erreur découverte trois semaines plus tard coûte beaucoup plus cher à corriger que la même erreur découverte le lendemain.

C'est la raison d'être du rapprochement quotidien : confronter les deux enregistrements, isoler ce qui diverge, et traiter les divergences tant qu'elles sont fraîches.

## 2. Situation actuelle

Aujourd'hui, un analyste ouvre chaque matin deux extractions dans un tableur. Il trie les deux fichiers sur l'identifiant de transaction, les met côte à côte, puis compare visuellement ligne par ligne. Les lignes qui ne correspondent pas sont recopiées dans un troisième onglet. Pour chacune, il cherche dans les systèmes sources ce qui explique l'écart, note un motif, et envoie un courriel à l'équipe concernée. En fin de matinée, il compile un décompte pour son responsable.

Cette organisation pose quatre difficultés.

**Le temps consommé.** Entre deux et trois heures par jour pour un volume de quelques milliers de transactions. Ce temps est pris sur l'analyse des cas complexes, qui est la vraie valeur ajoutée de l'analyste.

**Les erreurs de comparaison.** La comparaison visuelle sur plusieurs milliers de lignes fatigue. Des écarts passent, en particulier les petites différences de montant qui ne sautent pas aux yeux.

**L'hétérogénéité des motifs.** Chaque analyste formule les motifs à sa manière. Le décompte mensuel devient difficile à consolider et les tendances restent invisibles.

**L'absence de traçabilité.** Le fichier de travail est écrasé chaque jour. Six mois plus tard, plus personne ne peut expliquer pourquoi telle transaction avait été écartée.

## 3. Situation cible

Le rapprochement devient un traitement automatisé, déclenché par un ordonnanceur ou lancé manuellement. Il lit les deux extractions, produit le rapprochement, qualifie chaque écart et dépose trois livrables. L'analyste ne fait plus la comparaison. Il reprend le travail au moment où il devient intéressant : arbitrer les écarts qualifiés et traiter ceux que le système n'a pas su expliquer.

Le déroulement est le suivant.

**Étape 1, chargement.** Les deux extractions sont lues et contrôlées. Un fichier vide, illisible ou amputé d'une colonne obligatoire arrête le traitement immédiatement, avec un message qui nomme le fichier et la colonne en cause. Le principe est d'échouer tôt et clairement plutôt que de produire un rapport faux.

**Étape 2, rapprochement.** Deux lignes sont considérées comme la même transaction lorsque cinq attributs coïncident : identifiant, contrepartie, produit, date de négociation et devise. Le montant est comparé séparément, avec une tolérance d'un centime destinée à absorber les écarts d'arrondi entre systèmes.

**Étape 3, qualification.** Chaque écart reçoit un motif probable, une action recommandée et un indice de confiance. Cette qualification est produite soit par un modèle de langage, soit par un jeu de règles déterministe.

**Étape 4, indicateurs.** Volumes, taux de rapprochement, exposition financière des écarts et répartitions par nature, motif, contrepartie et produit.

**Étape 5, restitution.** Un classeur Excel détaillé, une synthèse texte pour le reporting managérial et un relevé des erreurs techniques.

## 4. Règles de gestion

### RG01, définition de l'identité d'une transaction

Une transaction est identifiée par la combinaison de son identifiant, de sa contrepartie, de son produit, de sa date de négociation et de sa devise. Les cinq attributs doivent coïncider.

La date et la devise sont volontairement incluses dans cette définition. Une transaction portant deux dates différentes dans les deux systèmes n'est pas rapprochée : elle ressort comme deux écarts symétriques portant le même identifiant. Ce choix évite d'affirmer que deux enregistrements représentent la même opération alors que les systèmes ne s'accordent pas sur un attribut structurant. L'analyste conserve la décision de les réunir.

### RG02, tolérance sur les montants

Deux montants sont considérés comme identiques si leur différence absolue est inférieure ou égale à un centime. Cette tolérance couvre les différences de convention d'arrondi entre systèmes. Elle est trop faible pour masquer une erreur de saisie réelle.

### RG03, montant indisponible

Lorsqu'un montant est absent ou illisible, la comparaison est impossible. La transaction est classée en écart de nature `amount_invalid` et non en rapprochement. Cette règle est importante : sans elle, une transaction dont le montant manque des deux côtés serait comptée comme correctement rapprochée, ce qui reviendrait à valider une donnée inexistante.

### RG04, normalisation des clés

Avant comparaison, les clés sont converties en texte et débarrassées des espaces de début et de fin. Un identifiant saisi sous forme numérique dans un système et sous forme textuelle dans l'autre est donc bien rapproché.

### RG05, natures d'écart

| Code | Situation | Équipe destinataire |
| --- | --- | --- |
| `amount` | Présente des deux côtés, montants divergents | Middle office |
| `amount_invalid` | Présente des deux côtés, montant inexploitable | Support des données |
| `missing_B` | Présente dans le Système A uniquement | Back office |
| `missing_A` | Présente dans le Système B uniquement | Front office |

### RG06, indice de confiance

Chaque qualification porte un indice compris entre zéro et un. Les écarts de confiance inférieure à 0,6 relèvent d'une revue manuelle prioritaire, car le système n'a pas su proposer d'explication solide.

### RG07, continuité de service

L'indisponibilité du modèle de langage ne doit jamais empêcher la production du rapport. En cas d'échec, d'expiration du délai ou de réponse inexploitable, l'écart concerné bascule sur sa règle déterministe et le traitement se poursuit.

## 5. Indicateurs produits

**Volume traité.** Nombre de transactions distinctes présentes dans au moins un des deux systèmes.

**Taux de rapprochement.** Part des transactions rapprochées sans écart dans le volume traité. C'est l'indicateur de tête, suivi quotidiennement. Une dégradation soudaine signale presque toujours un incident technique en amont plutôt qu'une vraie hausse des erreurs.

**Nombre d'écarts par nature.** Permet de distinguer un problème de saisie d'un problème d'alimentation d'un système.

**Exposition des écarts.** Somme des différences de montant, les transactions absentes d'un système comptant pour leur montant entier. Cet indicateur hiérarchise le traitement : cinquante écarts de faible montant pèsent moins qu'un seul écart portant sur plusieurs millions.

**Répartition par contrepartie et par produit.** Fait apparaître les concentrations. Une contrepartie systématiquement en écart révèle le plus souvent un problème de convention entre les deux établissements, pas une erreur de saisie.

## 6. Bénéfices attendus

Le gain principal porte sur le temps de traitement, qui passe de deux à trois heures de comparaison manuelle à quelques secondes de calcul. Le temps libéré est reporté sur l'analyse des écarts, qui reste manuelle et le restera.

Le second gain porte sur l'exhaustivité. La comparaison automatisée ne fatigue pas et détecte les écarts d'un centime aussi bien que ceux d'un million.

Le troisième gain porte sur la traçabilité. Chaque exécution laisse un journal horodaté et un jeu de livrables datés. La reconstitution d'une décision plusieurs mois après devient possible.

Le quatrième gain porte sur la standardisation. Les motifs proviennent d'un référentiel unique, ce qui rend les statistiques mensuelles réellement comparables d'un mois sur l'autre.

## 7. Ce que le processus ne couvre pas

Le rapprochement partiel n'est pas traité. Une transaction du Système A soldée par deux lignes du Système B ressort comme trois écarts, à charge de l'analyste de les rapprocher.

La correction automatique n'est pas prévue et ne le sera pas. Le traitement détecte et qualifie ; la décision de corriger reste humaine, ce qui est une exigence de contrôle interne.

Les volumes supérieurs à quelques dizaines de milliers de transactions demandent une adaptation technique, décrite dans le document de conception.

## 8. Rôles

| Rôle | Responsabilité |
| --- | --- |
| Analyste des opérations | Lance le traitement, arbitre les écarts, relance les équipes concernées |
| Responsable des opérations | Suit le taux de rapprochement et l'exposition, arbitre les cas sensibles |
| Support informatique | Maintient la chaîne, traite les incidents techniques |
| Contrôle interne | Consulte les journaux et les livrages archivés |

## 9. Documents liés

La conception technique est décrite dans [SDD_SolutionDesign.md](SDD_SolutionDesign.md).
Les scénarios de recette figurent dans [UAT_scenarios.md](UAT_scenarios.md).
La procédure d'exploitation courante figure dans [RUNBOOK.md](RUNBOOK.md).

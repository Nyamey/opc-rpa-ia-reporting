# Jeux de données de recette

Ces jeux servent à éprouver la chaîne, à la main dans l'application ou en ligne
de commande. Chaque cas isole un comportement et annonce le résultat attendu.

Les résultats de ce document ne sont pas déclaratifs : ils sont contrôlés
automatiquement.

```bash
python tools/verifier_jeux_test.py
```

Ce script passe chaque jeu dans la chaîne réelle et confronte le résultat à
l'attendu ci-dessous. Un guide de recette dont les attendus sont faux fait
douter du produit là où c'est la documentation qui se trompe.

Pour régénérer les fichiers après une évolution du format d'entrée :

```bash
python tools/generer_jeux_test.py
```

---

## Comment les utiliser

**Dans l'application.** Lancez `streamlit run streamlit_app.py`, ouvrez la zone
de dépôt du volet concerné et déposez les deux fichiers du cas.

**En ligne de commande.**

```bash
python src/main.py --input-dir data/samples/reconciliation/02-toutes-natures-decart
python src/evaluer_processus.py --input-dir data/samples/selection
```

Pour le volet sélection en ligne de commande, le fichier doit porter le nom
`processus_candidats.csv` ; copiez le cas voulu sous ce nom dans un répertoire
de travail.

---

## Réconciliation

### Cas nominaux

| Cas | Contenu | Résultat attendu |
| --- | --- | --- |
| `01-nominal-parfait` | Deux extractions identiques, 12 transactions | 12 rapprochées, aucun écart, taux de 100 % |
| `02-toutes-natures-decart` | Écarts de montant, de date, de devise, transactions absentes de part et d'autre | Les trois natures `amount`, `missing_A` et `missing_B` sont présentes |

Le cas 02 mérite une lecture attentive. La transaction dont la date diverge et
celle dont la devise diverge ne ressortent pas comme un écart unique mais comme
un couple `missing_A` et `missing_B` portant le même identifiant. C'est le
comportement voulu, expliqué par la règle RG01 du document métier : ces deux
attributs font partie des clés de rapprochement, et le programme refuse
d'affirmer que deux enregistrements représentent la même opération lorsque les
systèmes ne s'accordent pas sur un attribut structurant.

### Formats de fichier

| Cas | Particularité | Résultat attendu |
| --- | --- | --- |
| `03-format-tableur-francais` | Point-virgule et page de code Windows | 3 transactions lues, accents corrects |
| `04-format-tabulation` | Séparateur tabulation | 5 transactions rapprochées |
| `05-format-utf8-bom` | UTF-8 avec marque d'ordre des octets | 3 transactions lues, accents corrects |
| `06-entetes-avec-espaces` | Espaces résiduels autour des noms de colonnes | 5 transactions rapprochées |
| `07-valeurs-avec-separateur` | Contreparties du type `Bank A, Paris` entre guillemets | 2 transactions rapprochées |

Le cas 03 est le plus représentatif de la réalité : c'est ce que produit un
tableur français par défaut. Le cas 06 mérite d'être essayé parce que le défaut
y est invisible à l'œil dans un éditeur de texte.

### Cas limites de données

| Cas | Contenu | Résultat attendu |
| --- | --- | --- |
| `08-montants-illisibles` | Montant vide, montant valant `n/a` | 2 écarts `amount_invalid`, 1 transaction rapprochée |
| `09-montants-textuels` | Montants entre guillemets d'un côté | 3 rapprochées, aucun écart |
| `10-cles-avec-espaces` | Espaces autour des identifiants et contreparties | Aucun écart |
| `11-doublons-de-cles` | Une transaction répétée dans le Système A | Traitement poursuivi, avertissement au journal |
| `12-systeme-b-vide` | Extraction amont défaillante | 7 écarts `missing_B`, taux de 0 % |
| `18-entete-seule` | Deux fichiers réduits à leur en-tête | Traitement abouti, aucune transaction |

Le cas 08 couvre une anomalie corrigée en cours de projet. Auparavant, deux
montants absents donnaient une différence indéterminée que toute comparaison
évalue à faux, et la transaction était comptée comme correctement rapprochée.
Autrement dit, la chaîne validait une donnée inexistante.

Le cas 12 produit un taux de rapprochement nul. Ce n'est pas une dégradation de
la qualité des saisies mais un incident d'alimentation, et c'est ainsi qu'il
faut le lire.

Le cas 18 a lui aussi révélé un défaut : deux extractions vides faisaient
échouer la fusion sur une erreur interne de la bibliothèque, incompréhensible
pour un exploitant. Un jour sans activité est pourtant un cas légitime.

### Sécurité

| Cas | Contenu | Résultat attendu |
| --- | --- | --- |
| `13-libelles-hostiles` | Contreparties portant des formules de tableur | Aucune cellule de type formule dans le classeur produit |

C'est le cas le plus important à éprouver. Les contreparties portent des
charges utiles réelles, dont `=cmd|'/c calc.exe'!A0`. Avant correction, cette
valeur était écrite dans le classeur comme une véritable formule d'échange
dynamique de données, exécutable sur le poste de l'analyste ouvrant le rapport.

Pour le vérifier vous-même, déposez ce cas dans l'application, téléchargez le
classeur et ouvrez-le : les libellés doivent s'afficher précédés d'une
apostrophe, en texte, et aucune invite d'exécution ne doit apparaître.

### Volumétrie

| Cas | Contenu | Résultat attendu |
| --- | --- | --- |
| `14-volumetrie` | 20 000 transactions par système, environ 8 % d'écarts | Environ 18 400 rapprochées et 1 800 écarts, en 5 à 6 secondes |

Ce cas mesure le comportement à une échelle réaliste pour un secteur
opérationnel. Le temps de traitement est dominé par le parcours ligne à ligne
du résultat de la fusion, choix assumé au profit de la lisibilité de la logique
de décision et documenté comme limite dans le document de conception.

### Cas de rejet

| Cas | Contenu | Message attendu |
| --- | --- | --- |
| `15-rejet-fichier-vide` | Système A de zéro octet | Le fichier est vide, avec rappel des colonnes attendues |
| `16-rejet-colonne-manquante` | Système B privé de sa colonne `currency` | La colonne `currency` est nommée, avec la liste de celles trouvées |
| `17-rejet-lignes-malformees` | Une ligne comporte des champs surnuméraires | Le fichier est mal formé, avec mention du séparateur |

Ces trois cas rendent un code de sortie 1 en ligne de commande et inscrivent
l'erreur dans `errors_summary.csv`. Dans l'application, ils affichent un
message en rouge sans interrompre la session.

Le cas 17 mérite attention : le message d'origine de la bibliothèque parlait de
« 7 fields in line 4 », ce qui n'apprend rien à un exploitant. Il est réécrit
pour désigner la cause réelle, à savoir une valeur contenant le séparateur sans
être protégée par des guillemets.

---

## Sélection des processus

| Cas | Contenu | Résultat attendu |
| --- | --- | --- |
| `20-toutes-orientations.csv` | Un processus par orientation | Six orientations distinctes |
| `21-tout-automatisable.csv` | Cinq processus volumineux et déterministes | Tous en automatisation classique |
| `22-tout-ecarte.csv` | Cinq processus de charge marginale | Tous écartés |
| `23-valeurs-manquantes.csv` | Attributs non renseignés | Évaluation aboutie, valeurs par défaut appliquées |
| `24-rejet-colonne-manquante.csv` | Colonne `volumetrie_annuelle` absente | Rejet nommant la colonne |
| `25-format-tableur-francais.csv` | Même contenu que le cas 20, en point-virgule et page de code Windows | Six orientations distinctes |

Le cas 20 est le plus instructif : il permet de vérifier les trois critères
éliminatoires de la grille. Le processus `INTE-01` sort du périmètre parce
qu'une interface applicative existe, alors qu'il est par ailleurs un excellent
candidat. Le processus `HYBR-01` bascule en projet hybride parce que ses
données ne sont pas structurées, quelle que soit sa stabilité. Le processus
`OPTI-01` part en optimisation préalable parce que son taux de règles reste
sous le seuil.

Le cas 22 illustre le seuil de charge : ces processus sont techniquement
simples mais leur volume ne rentabilise pas la construction et la maintenance
d'un robot.

---

## Données

Toutes les données sont synthétiques. Les noms de contreparties sont ceux
d'établissements réels mais les transactions sont inventées et ne correspondent
à aucune opération, aucun client ni aucun établissement.

"""
Génère les jeux de données de recette.

Les fichiers produits couvrent le cas nominal, les quatre natures d'écart, les
formats de fichier rencontrés en pratique, les rejets attendus et les cas
limites. Ils sont écrits plutôt que rédigés à la main afin de rester
reproductibles : régénérer le jeu après une évolution du format d'entrée est
une commande, pas une reprise de vingt fichiers.

Utilisation :
    python tools/generer_jeux_test.py
"""

import random
import sys
from pathlib import Path

RACINE = Path(__file__).parent.parent
SAMPLES = RACINE / "data" / "samples"
RECONCILIATION = SAMPLES / "reconciliation"
SELECTION = SAMPLES / "selection"

ENTETE = ["trade_id", "counterparty", "product", "trade_date", "amount", "currency"]

CONTREPARTIES = [
    "BNP Paribas", "Societe Generale", "HSBC", "Deutsche Bank", "Barclays",
    "Credit Agricole", "JP Morgan", "Natixis", "UBS", "Santander",
]
PRODUITS = ["IRS", "FX Forward", "Equity Swap", "CDS", "Bond Future", "FX Spot"]
DEVISES = ["EUR", "USD", "GBP", "CHF"]


def ecrire(
    chemin: Path,
    lignes: list,
    separateur: str = ",",
    encodage: str = "utf-8",
    entete: list = None,
) -> None:
    """
    Écrit un fichier CSV dans le format demandé.

    Args:
        chemin: Fichier à produire.
        lignes: Lignes de données, chacune sous forme de liste de valeurs.
        separateur: Séparateur de colonnes.
        encodage: Encodage du fichier.
        entete: En-tête à employer, celui par défaut sinon.
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)

    colonnes = entete if entete is not None else ENTETE
    contenu = [separateur.join(colonnes)]
    contenu += [separateur.join(str(valeur) for valeur in ligne) for ligne in lignes]

    chemin.write_bytes(("\n".join(contenu) + "\n").encode(encodage))


def transaction(numero: int, montant: float = None, **remplacements) -> list:
    """
    Fabrique une transaction déterministe à partir de son numéro.

    Args:
        numero: Rang de la transaction, qui détermine ses attributs.
        montant: Montant imposé, calculé sinon.
        remplacements: Attributs à remplacer, par nom de colonne.

    Returns:
        La transaction sous forme de liste de valeurs.
    """
    valeurs = {
        "trade_id": f"TRD-{1000 + numero}",
        "counterparty": CONTREPARTIES[numero % len(CONTREPARTIES)],
        "product": PRODUITS[numero % len(PRODUITS)],
        "trade_date": f"2026-08-{3 + (numero % 10):02d}",
        "amount": f"{montant if montant is not None else 100000 + numero * 1250:.2f}",
        "currency": DEVISES[numero % len(DEVISES)],
    }
    valeurs.update(remplacements)
    return [valeurs[colonne] for colonne in ENTETE]


def cas(nom: str) -> Path:
    """Rend le répertoire d'un cas de réconciliation."""
    dossier = RECONCILIATION / nom
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def paire(nom: str, lignes_a: list, lignes_b: list, **options) -> None:
    """
    Écrit les deux fichiers d'un cas de réconciliation.

    Args:
        nom: Nom du cas, qui donne son nom au répertoire.
        lignes_a: Transactions du Système A.
        lignes_b: Transactions du Système B.
        options: Options de format transmises à l'écriture.
    """
    dossier = cas(nom)
    ecrire(dossier / "transactions_systemA.csv", lignes_a, **options)
    ecrire(dossier / "transactions_systemB.csv", lignes_b, **options)


# ---------------------------------------------------------------------------
# Cas nominaux
# ---------------------------------------------------------------------------

def cas_nominaux() -> None:
    """Rapprochement parfait et jeu couvrant les quatre natures d'écart."""
    base = [transaction(i) for i in range(1, 13)]
    paire("01-nominal-parfait", base, list(base))

    # Système A complet, Système B modifié pour produire chaque nature.
    a = [transaction(i) for i in range(1, 13)]
    b = []
    for i in range(1, 13):
        if i == 3:
            continue  # absente du Système B
        if i == 5:
            b.append(transaction(i, montant=100000 + i * 1250 + 500))  # montant divergent
        elif i == 7:
            b.append(transaction(i, trade_date="2026-09-30"))  # date divergente
        elif i == 9:
            b.append(transaction(i, currency="JPY"))  # devise divergente
        else:
            b.append(transaction(i))
    b.append(transaction(50))  # absente du Système A
    b.append(transaction(51))
    paire("02-toutes-natures-decart", a, b)


# ---------------------------------------------------------------------------
# Formats de fichier
# ---------------------------------------------------------------------------

def cas_formats() -> None:
    """Variantes de séparateur, d'encodage et d'en-tête rencontrées en pratique."""
    base = [transaction(i) for i in range(1, 6)]

    # Export de tableur français : point-virgule et page de code Windows.
    accentuees = [
        transaction(1, counterparty="Société Générale"),
        transaction(2, counterparty="Crédit Agricole"),
        transaction(3, counterparty="Natixis"),
    ]
    paire(
        "03-format-tableur-francais", accentuees, list(accentuees),
        separateur=";", encodage="cp1252",
    )

    paire("04-format-tabulation", base, list(base), separateur="\t")
    paire("05-format-utf8-bom", accentuees, list(accentuees), encodage="utf-8-sig")

    # En-têtes comportant des espaces résiduels, invisibles à l'œil.
    entete_espace = ["trade_id ", " counterparty", "product ", " trade_date",
                     "amount ", " currency"]
    dossier = cas("06-entetes-avec-espaces")
    ecrire(dossier / "transactions_systemA.csv", base, entete=entete_espace)
    ecrire(dossier / "transactions_systemB.csv", base, entete=entete_espace)

    # Valeurs contenant le séparateur, donc protégées par des guillemets.
    protegees = [
        transaction(1, counterparty='"Bank A, Paris"'),
        transaction(2, counterparty='"Bank B, London"'),
    ]
    paire("07-valeurs-avec-separateur", protegees, list(protegees))


# ---------------------------------------------------------------------------
# Cas limites de données
# ---------------------------------------------------------------------------

def cas_limites() -> None:
    """Données présentes mais inhabituelles, qui ne doivent pas faire échouer."""
    # Montants absents des deux côtés : la comparaison est impossible.
    illisibles = [
        transaction(1, amount=""),
        transaction(2, amount="n/a"),
        transaction(3),
    ]
    paire("08-montants-illisibles", illisibles, list(illisibles))

    # Montants sous forme textuelle d'un côté, numérique de l'autre.
    a = [transaction(i, amount=f'"{100000 + i * 1250:.2f}"') for i in range(1, 4)]
    b = [transaction(i) for i in range(1, 4)]
    paire("09-montants-textuels", a, b)

    # Espaces autour des clés de rapprochement.
    a = [transaction(i, trade_id=f" TRD-{1000 + i} ",
                     counterparty=f"{CONTREPARTIES[i % len(CONTREPARTIES)]} ")
         for i in range(1, 4)]
    b = [transaction(i) for i in range(1, 4)]
    paire("10-cles-avec-espaces", a, b)

    # Doublons de clés : le traitement se poursuit avec un avertissement.
    a = [transaction(1), transaction(1), transaction(2)]
    b = [transaction(1), transaction(2)]
    paire("11-doublons-de-cles", a, b)

    # Extraction amont défaillante : le Système B ne porte que son en-tête.
    paire("12-systeme-b-vide", [transaction(i) for i in range(1, 8)], [])

    # Libellés hostiles : formules de tableur déposées dans les données.
    charges = [
        transaction(1, counterparty="=cmd|'/c calc.exe'!A0"),
        transaction(2, counterparty="@SUM(1+1)"),
        transaction(3, counterparty="+HYPERLINK(\"http://exfil.example\")"),
        transaction(4, counterparty="-2+3"),
    ]
    paire("13-libelles-hostiles", charges, [])


def cas_volumetrie(lignes: int = 20000) -> None:
    """
    Produit un jeu volumineux pour observer le temps de traitement.

    Args:
        lignes: Nombre de transactions par système.
    """
    alea = random.Random(20260902)

    a, b = [], []
    for i in range(1, lignes + 1):
        montant = round(alea.uniform(10_000, 5_000_000), 2)
        a.append(transaction(i, montant=montant))

        tirage = alea.random()
        if tirage < 0.03:
            continue  # absente du Système B
        if tirage < 0.08:
            b.append(transaction(i, montant=round(montant + alea.uniform(1, 900), 2)))
        else:
            b.append(transaction(i, montant=montant))

    for i in range(lignes + 1, lignes + 200):
        b.append(transaction(i))  # absentes du Système A

    paire("14-volumetrie", a, b)


# ---------------------------------------------------------------------------
# Cas de rejet
# ---------------------------------------------------------------------------

def cas_rejets() -> None:
    """Fichiers qui doivent être refusés avec un message explicite."""
    base = [transaction(i) for i in range(1, 4)]

    # Fichier de zéro octet, tel que le produit une extraction interrompue.
    dossier = cas("15-rejet-fichier-vide")
    (dossier / "transactions_systemA.csv").write_bytes(b"")
    ecrire(dossier / "transactions_systemB.csv", base)

    # En-tête amputé d'une colonne obligatoire.
    dossier = cas("16-rejet-colonne-manquante")
    ecrire(dossier / "transactions_systemA.csv", base)
    entete_partiel = [c for c in ENTETE if c != "currency"]
    lignes_partielles = [ligne[:-1] for ligne in base]
    ecrire(dossier / "transactions_systemB.csv", lignes_partielles, entete=entete_partiel)

    # Lignes de longueur inégale.
    dossier = cas("17-rejet-lignes-malformees")
    contenu = ",".join(ENTETE) + "\n"
    contenu += "TRD-1001,BNP Paribas,IRS,2026-08-03,100000.00,EUR\n"
    contenu += "TRD-1002,Bank,X,IRS,2026-08-03,200000.00,EUR,surplus\n"
    (dossier / "transactions_systemA.csv").write_bytes(contenu.encode("utf-8"))
    ecrire(dossier / "transactions_systemB.csv", base)

    # En-tête seul : valide, mais sans aucune transaction.
    paire("18-entete-seule", [], [])


# ---------------------------------------------------------------------------
# Référentiels de processus
# ---------------------------------------------------------------------------

ENTETE_PROCESSUS = [
    "process_id", "nom", "secteur", "perimetre", "volumetrie_annuelle",
    "temps_unitaire_min", "taux_regles", "stabilite", "structuration_donnees",
    "nb_applications", "api_disponible", "criticite_reglementaire",
    "taux_erreur_actuel",
]


def processus(pid: str, nom: str, secteur: str, **valeurs) -> list:
    """
    Fabrique un processus candidat à partir d'un profil de référence.

    Args:
        pid: Identifiant du processus.
        nom: Libellé métier.
        secteur: Secteur de rattachement.
        valeurs: Attributs à remplacer.

    Returns:
        Le processus sous forme de liste de valeurs.
    """
    profil = {
        "process_id": pid, "nom": nom, "secteur": secteur, "perimetre": "France",
        "volumetrie_annuelle": 45000, "temps_unitaire_min": 8, "taux_regles": 95,
        "stabilite": 5, "structuration_donnees": "structuré", "nb_applications": 2,
        "api_disponible": "non", "criticite_reglementaire": 4,
        "taux_erreur_actuel": 3.2,
    }
    profil.update(valeurs)
    return [profil[colonne] for colonne in ENTETE_PROCESSUS]


def cas_selection() -> None:
    """Référentiels de processus couvrant les orientations et les rejets."""
    SELECTION.mkdir(parents=True, exist_ok=True)

    # Un processus par orientation, pour vérifier la doctrine d'arbitrage.
    toutes = [
        processus("AUTO-01", "Rapprochement des relevés", "TBS-CMS"),
        processus("HYBR-01", "Contrôle documentaire", "FTO",
                  structuration_donnees="non structuré", taux_regles=50,
                  volumetrie_annuelle=68000, temps_unitaire_min=9),
        processus("INTE-01", "Extraction des positions", "CMO", api_disponible="oui"),
        processus("OPTI-01", "Suivi des suspens", "CMO", taux_regles=55,
                  stabilite=3, nb_applications=4,
                  structuration_donnees="semi-structuré"),
        processus("BACK-01", "Mise à jour des données statiques", "GRM",
                  volumetrie_annuelle=32000, temps_unitaire_min=6,
                  criticite_reglementaire=3, taux_erreur_actuel=2.4, taux_regles=90),
        processus("ECAR-01", "Relance des débiteurs", "TBS-SCS",
                  volumetrie_annuelle=1800, temps_unitaire_min=2,
                  criticite_reglementaire=2, taux_erreur_actuel=2.2),
    ]
    ecrire(SELECTION / "20-toutes-orientations.csv", toutes, entete=ENTETE_PROCESSUS)

    # Portefeuille homogène favorable, puis homogène défavorable.
    favorables = [
        processus(f"AUTO-{i:02d}", f"Processus favorable {i}", "CMO",
                  volumetrie_annuelle=40000 + i * 1000)
        for i in range(1, 6)
    ]
    ecrire(SELECTION / "21-tout-automatisable.csv", favorables, entete=ENTETE_PROCESSUS)

    defavorables = [
        processus(f"ECAR-{i:02d}", f"Processus marginal {i}", "GRM",
                  volumetrie_annuelle=600, temps_unitaire_min=3,
                  criticite_reglementaire=1, taux_erreur_actuel=0.2)
        for i in range(1, 6)
    ]
    ecrire(SELECTION / "22-tout-ecarte.csv", defavorables, entete=ENTETE_PROCESSUS)

    # Valeurs manquantes : la notation doit se poursuivre avec des défauts.
    lacunaires = [
        processus("LACU-01", "Processus incomplet", "FTO",
                  criticite_reglementaire="", taux_erreur_actuel="",
                  nb_applications="", structuration_donnees=""),
        processus("LACU-02", "Processus partiel", "FTO", stabilite=""),
    ]
    ecrire(SELECTION / "23-valeurs-manquantes.csv", lacunaires, entete=ENTETE_PROCESSUS)

    # Colonne obligatoire absente.
    entete_partiel = [c for c in ENTETE_PROCESSUS if c != "volumetrie_annuelle"]
    index = ENTETE_PROCESSUS.index("volumetrie_annuelle")
    amputes = [
        [valeur for position, valeur in enumerate(processus("PART-01", "Incomplet", "CMO"))
         if position != index]
    ]
    ecrire(SELECTION / "24-rejet-colonne-manquante.csv", amputes, entete=entete_partiel)

    # Export de tableur français, pour le volet sélection également.
    ecrire(SELECTION / "25-format-tableur-francais.csv", toutes,
           separateur=";", encodage="cp1252", entete=ENTETE_PROCESSUS)


def main() -> None:
    """Génère l'ensemble des jeux de recette."""
    cas_nominaux()
    cas_formats()
    cas_limites()
    cas_volumetrie()
    cas_rejets()
    cas_selection()

    dossiers = sorted(p for p in RECONCILIATION.iterdir() if p.is_dir())
    fichiers = sorted(SELECTION.glob("*.csv"))

    print(f"Jeux de réconciliation : {len(dossiers)}")
    for dossier in dossiers:
        print(f"  {dossier.name}")

    print(f"\nRéférentiels de sélection : {len(fichiers)}")
    for fichier in fichiers:
        print(f"  {fichier.name}")

    print(f"\nDéposés dans {SAMPLES}")


if __name__ == "__main__":
    sys.exit(main())

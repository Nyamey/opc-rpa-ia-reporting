"""
Vérifie que chaque jeu de recette produit le résultat annoncé.

Un guide de test dont les résultats attendus sont faux est pire qu'absent :
il fait douter du produit là où c'est la documentation qui se trompe. Ce
script passe chaque jeu dans la chaîne réelle et confronte le résultat à
l'attendu déclaré.

Utilisation :
    python tools/verifier_jeux_test.py
"""

import io
import logging
import sys
import time
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

RACINE = Path(__file__).parent.parent
sys.path.insert(0, str(RACINE / "src"))

from kpi_calculator import compute_kpis  # noqa: E402
from llm_classifier import classify_breaks  # noqa: E402
from process_assessment import charger_candidats, evaluer  # noqa: E402
from reconciliation_engine import load_and_validate_files, reconcile  # noqa: E402
from report_generator import generate_excel_report  # noqa: E402

RECONCILIATION = RACINE / "data" / "samples" / "reconciliation"
SELECTION = RACINE / "data" / "samples" / "selection"

# Les avertissements attendus ne doivent pas polluer la sortie du contrôle.
logging.getLogger().setLevel(logging.ERROR)


def rapprocher(dossier: Path) -> dict:
    """
    Passe un jeu dans la chaîne de réconciliation.

    Args:
        dossier: Répertoire contenant les deux fichiers.

    Returns:
        Le résultat, ou l'erreur rencontrée.
    """
    debut = time.perf_counter()
    try:
        df_a, df_b = load_and_validate_files(dossier)
        matched, bruts = reconcile(df_a, df_b)
        breaks = classify_breaks(bruts)
        kpis = compute_kpis(matched, breaks)
    except Exception as exc:
        return {"erreur": type(exc).__name__, "message": str(exc)}

    return {
        "rapprochees": len(matched),
        "ecarts": len(breaks),
        "natures": sorted(breaks["break_type"].unique()) if not breaks.empty else [],
        "taux": float(kpis["kpi_summary"].iloc[0]["match_rate"]),
        "duree": time.perf_counter() - debut,
        "breaks": breaks,
        "kpis": kpis,
    }


def controle(intitule: str, obtenu, attendu) -> bool:
    """
    Compare un résultat à son attendu et rend compte.

    Args:
        intitule: Description du contrôle.
        obtenu: Valeur constatée.
        attendu: Valeur attendue.

    Returns:
        True si le contrôle passe.
    """
    ok = obtenu == attendu
    marque = "  OK  " if ok else " ECHEC"
    detail = "" if ok else f"   attendu {attendu!r}, obtenu {obtenu!r}"
    print(f"  [{marque}] {intitule}{detail}")
    return ok


def verifier_reconciliation() -> int:
    """
    Contrôle l'ensemble des jeux de réconciliation.

    Returns:
        Le nombre d'échecs.
    """
    echecs = 0
    print("=" * 78)
    print("RECONCILIATION")
    print("=" * 78)

    r = rapprocher(RECONCILIATION / "01-nominal-parfait")
    print("\n01-nominal-parfait")
    echecs += not controle("aucun ecart", r["ecarts"], 0)
    echecs += not controle("12 transactions rapprochees", r["rapprochees"], 12)
    echecs += not controle("taux de 100 %", r["taux"], 100.0)

    r = rapprocher(RECONCILIATION / "02-toutes-natures-decart")
    print("\n02-toutes-natures-decart")
    echecs += not controle(
        "trois natures presentes", r["natures"], ["amount", "missing_A", "missing_B"]
    )

    for nom, contrepartie in [
        ("03-format-tableur-francais", "Société Générale"),
        ("05-format-utf8-bom", "Société Générale"),
    ]:
        r = rapprocher(RECONCILIATION / nom)
        print(f"\n{nom}")
        echecs += not controle("aucun ecart", r["ecarts"], 0)
        echecs += not controle("3 transactions lues", r["rapprochees"], 3)

    for nom, attendu in [("04-format-tabulation", 5), ("06-entetes-avec-espaces", 5)]:
        r = rapprocher(RECONCILIATION / nom)
        print(f"\n{nom}")
        echecs += not controle(f"{attendu} transactions rapprochees",
                               r["rapprochees"], attendu)
        echecs += not controle("aucun ecart", r["ecarts"], 0)

    r = rapprocher(RECONCILIATION / "07-valeurs-avec-separateur")
    print("\n07-valeurs-avec-separateur")
    echecs += not controle("2 transactions rapprochees", r["rapprochees"], 2)
    echecs += not controle("aucun ecart", r["ecarts"], 0)

    r = rapprocher(RECONCILIATION / "08-montants-illisibles")
    print("\n08-montants-illisibles")
    echecs += not controle("2 montants inexploitables signales",
                           r["natures"], ["amount_invalid"])
    echecs += not controle("1 transaction rapprochee", r["rapprochees"], 1)

    r = rapprocher(RECONCILIATION / "09-montants-textuels")
    print("\n09-montants-textuels")
    echecs += not controle("montants textuels rapproches", r["ecarts"], 0)
    echecs += not controle("3 transactions rapprochees", r["rapprochees"], 3)

    r = rapprocher(RECONCILIATION / "10-cles-avec-espaces")
    print("\n10-cles-avec-espaces")
    echecs += not controle("cles normalisees", r["ecarts"], 0)

    r = rapprocher(RECONCILIATION / "11-doublons-de-cles")
    print("\n11-doublons-de-cles")
    echecs += not controle("traitement poursuivi", "erreur" in r, False)

    r = rapprocher(RECONCILIATION / "12-systeme-b-vide")
    print("\n12-systeme-b-vide")
    echecs += not controle("tout en absence du Systeme B",
                           r["natures"], ["missing_B"])
    echecs += not controle("7 ecarts", r["ecarts"], 7)
    echecs += not controle("taux de 0 %", r["taux"], 0.0)

    r = rapprocher(RECONCILIATION / "13-libelles-hostiles")
    print("\n13-libelles-hostiles")
    dossier_sortie = Path(RACINE / "data" / "samples" / ".controle")
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    chemin = generate_excel_report(r["kpis"], r["breaks"], dossier_sortie)
    classeur = load_workbook(chemin)
    formules = [
        cellule.coordinate
        for feuille in classeur.worksheets
        for ligne in feuille.iter_rows()
        for cellule in ligne
        if cellule.data_type == "f"
    ]
    echecs += not controle("aucune formule dans le classeur", len(formules), 0)

    r = rapprocher(RECONCILIATION / "14-volumetrie")
    print("\n14-volumetrie")
    echecs += not controle("traitement sans erreur", "erreur" in r, False)
    print(f"  [ INFO ] {r['rapprochees']} rapprochees, {r['ecarts']} ecarts, "
          f"{r['duree']:.1f} s")

    r = rapprocher(RECONCILIATION / "15-rejet-fichier-vide")
    print("\n15-rejet-fichier-vide")
    echecs += not controle("rejet", r.get("erreur"), "ValueError")
    echecs += not controle("message citant le vide", "vide" in r.get("message", ""), True)

    r = rapprocher(RECONCILIATION / "16-rejet-colonne-manquante")
    print("\n16-rejet-colonne-manquante")
    echecs += not controle("rejet", r.get("erreur"), "ValueError")
    echecs += not controle("colonne nommee", "currency" in r.get("message", ""), True)

    r = rapprocher(RECONCILIATION / "17-rejet-lignes-malformees")
    print("\n17-rejet-lignes-malformees")
    echecs += not controle("rejet", r.get("erreur"), "ValueError")
    echecs += not controle("message lisible",
                           "mal formé" in r.get("message", ""), True)

    r = rapprocher(RECONCILIATION / "18-entete-seule")
    print("\n18-entete-seule")
    echecs += not controle("traitement sans erreur", "erreur" in r, False)
    echecs += not controle("aucune transaction", r["rapprochees"], 0)

    return echecs


def verifier_selection() -> int:
    """
    Contrôle l'ensemble des référentiels de sélection.

    Returns:
        Le nombre d'échecs.
    """
    echecs = 0
    print("\n" + "=" * 78)
    print("SELECTION DES PROCESSUS")
    print("=" * 78)

    def evaluer_fichier(nom: str):
        dossier = SELECTION / nom
        cible = dossier.parent / ".controle-selection"
        cible.mkdir(parents=True, exist_ok=True)
        (cible / "processus_candidats.csv").write_bytes(dossier.read_bytes())
        try:
            return evaluer(charger_candidats(cible)), None
        except Exception as exc:
            return None, exc

    ev, err = evaluer_fichier("20-toutes-orientations.csv")
    print("\n20-toutes-orientations")
    echecs += not controle("six orientations distinctes",
                           ev["orientation"].nunique() if ev is not None else 0, 6)

    ev, err = evaluer_fichier("21-tout-automatisable.csv")
    print("\n21-tout-automatisable")
    echecs += not controle("toutes en automatisation",
                           set(ev["orientation"]), {"Automatiser en RPA"})

    ev, err = evaluer_fichier("22-tout-ecarte.csv")
    print("\n22-tout-ecarte")
    echecs += not controle("toutes ecartees", set(ev["orientation"]), {"Écarter"})

    ev, err = evaluer_fichier("23-valeurs-manquantes.csv")
    print("\n23-valeurs-manquantes")
    echecs += not controle("evaluation aboutie", err, None)
    if ev is not None:
        echecs += not controle("notes calculees",
                               bool(ev["score_valeur"].notna().all()), True)

    ev, err = evaluer_fichier("24-rejet-colonne-manquante.csv")
    print("\n24-rejet-colonne-manquante")
    echecs += not controle("rejet", type(err).__name__, "ValueError")
    echecs += not controle("colonne nommee",
                           "volumetrie_annuelle" in str(err), True)

    ev, err = evaluer_fichier("25-format-tableur-francais.csv")
    print("\n25-format-tableur-francais")
    echecs += not controle("six orientations distinctes",
                           ev["orientation"].nunique() if ev is not None else 0, 6)

    return echecs


def main() -> int:
    """Exécute tous les contrôles."""
    echecs = verifier_reconciliation() + verifier_selection()

    print("\n" + "=" * 78)
    if echecs:
        print(f"{echecs} controle(s) en echec")
    else:
        print("Tous les jeux produisent le resultat annonce")
    print("=" * 78)

    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())

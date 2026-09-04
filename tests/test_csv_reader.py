"""
Tests de la lecture tolérante des fichiers CSV.

Ces cas correspondent à ce que produisent réellement les outils bureautiques
et les extractions de systèmes hétérogènes. Chacun d'eux, non traité,
obligerait l'utilisateur à convertir son fichier avant de pouvoir le déposer.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from csv_reader import lire_csv

COLONNES = ["trade_id", "counterparty", "amount"]
ENTETE = "trade_id,counterparty,amount"


def ecrire(chemin: Path, contenu: str, encodage: str = "utf-8") -> Path:
    """Écrit un fichier d'essai dans l'encodage demandé."""
    chemin.write_bytes(contenu.encode(encodage))
    return chemin


def test_format_standard(tmp_path):
    """Une virgule et de l'UTF-8 restent le cas nominal."""
    chemin = ecrire(tmp_path / "f.csv", f"{ENTETE}\nTR1,Bank A,1000\n")

    df = lire_csv(chemin, "d'essai", COLONNES)

    assert len(df) == 1
    assert df["counterparty"].iloc[0] == "Bank A"


def test_export_de_tableur_francais(tmp_path):
    """
    Un export de tableur français arrive en point-virgule et en page de code
    Windows. C'est le cas le plus fréquent en pratique.
    """
    contenu = "trade_id;counterparty;amount\nTR1;Société Générale;1000\n"
    chemin = ecrire(tmp_path / "f.csv", contenu, "cp1252")

    df = lire_csv(chemin, "d'essai", COLONNES)

    assert df["counterparty"].iloc[0] == "Société Générale"


def test_utf8_avec_marque_dordre_des_octets(tmp_path):
    """
    Une marque d'ordre des octets se colle au premier nom de colonne et rendrait
    la colonne introuvable si elle n'était pas absorbée.
    """
    chemin = ecrire(tmp_path / "f.csv", f"{ENTETE}\nTR1,Bank A,1000\n", "utf-8-sig")

    df = lire_csv(chemin, "d'essai", COLONNES)

    assert "trade_id" in df.columns


def test_separateur_tabulation(tmp_path):
    """Un export tabulé est reconnu."""
    contenu = "trade_id\tcounterparty\tamount\nTR1\tBank A\t1000\n"
    chemin = ecrire(tmp_path / "f.csv", contenu)

    df = lire_csv(chemin, "d'essai", COLONNES)

    assert len(df) == 1


def test_espaces_dans_les_entetes(tmp_path):
    """
    Un espace en fin de nom de colonne est invisible à l'œil et provoquerait
    un diagnostic incompréhensible.
    """
    contenu = "trade_id , counterparty ,amount\nTR1,Bank A,1000\n"
    chemin = ecrire(tmp_path / "f.csv", contenu)

    df = lire_csv(chemin, "d'essai", COLONNES)

    assert list(df.columns) == COLONNES


def test_fichier_absent(tmp_path):
    """L'absence de fichier lève une erreur dédiée."""
    with pytest.raises(FileNotFoundError):
        lire_csv(tmp_path / "absent.csv", "d'essai", COLONNES)


def test_fichier_vide(tmp_path):
    """Un fichier de zéro octet est signalé explicitement."""
    chemin = ecrire(tmp_path / "f.csv", "")

    with pytest.raises(ValueError, match="vide"):
        lire_csv(chemin, "d'essai", COLONNES)


def test_entete_seule_est_acceptee(tmp_path):
    """Un fichier réduit à son en-tête est valide mais sans ligne."""
    chemin = ecrire(tmp_path / "f.csv", f"{ENTETE}\n")

    df = lire_csv(chemin, "d'essai", COLONNES)

    assert df.empty
    assert list(df.columns) == COLONNES


def test_colonne_manquante_nomme_le_manque_et_le_trouve(tmp_path):
    """
    Le message cite la colonne absente et celles qui ont été trouvées, ce qui
    permet de diagnostiquer un mauvais séparateur ou un mauvais fichier.
    """
    chemin = ecrire(tmp_path / "f.csv", "trade_id,counterparty\nTR1,Bank A\n")

    with pytest.raises(ValueError) as erreur:
        lire_csv(chemin, "d'essai", COLONNES)

    assert "amount" in str(erreur.value)
    assert "Colonnes trouvées" in str(erreur.value)


def test_lignes_mal_formees_donnent_un_message_lisible(tmp_path):
    """
    Le message de la bibliothèque cite des numéros de champs incompréhensibles
    pour un exploitant. Il est réécrit.
    """
    contenu = f"{ENTETE}\nTR1,Bank A,1000\nTR2,Bank,B,2000,extra\n"
    chemin = ecrire(tmp_path / "f.csv", contenu)

    with pytest.raises(ValueError, match="mal formé"):
        lire_csv(chemin, "d'essai", COLONNES)


def test_valeur_contenant_le_separateur(tmp_path):
    """Une valeur entre guillemets peut contenir le séparateur."""
    contenu = f'{ENTETE}\nTR1,"Bank A, Paris",1000\n'
    chemin = ecrire(tmp_path / "f.csv", contenu)

    df = lire_csv(chemin, "d'essai", COLONNES)

    assert df["counterparty"].iloc[0] == "Bank A, Paris"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

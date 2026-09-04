"""
Tests de la grille de sélection des processus candidats.

Les tests portent moins sur l'arithmétique que sur la doctrine : chaque
scénario vérifie qu'un profil de processus donné reçoit bien l'orientation que
le programme a décidé de lui appliquer.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from process_assessment import (
    ORIENTATIONS,
    calculer_charge,
    charger_candidats,
    construire_restitution,
    evaluer,
    noter,
    synthese_par_orientation,
    synthese_par_secteur,
)


def candidat(**overrides) -> dict:
    """
    Fabrique un processus candidat de référence, personnalisable par mot-clé.

    Le profil de base est celui d'un bon candidat : volumineux, déterministe,
    stable et sur données structurées.

    Args:
        overrides: Champs à remplacer.

    Returns:
        Un processus candidat complet.
    """
    base = {
        "process_id": "TEST-01",
        "nom": "Processus de référence",
        "secteur": "CMO",
        "perimetre": "France",
        "volumetrie_annuelle": 45000,
        "temps_unitaire_min": 8,
        "taux_regles": 95,
        "stabilite": 5,
        "structuration_donnees": "structuré",
        "nb_applications": 2,
        "api_disponible": "non",
        "criticite_reglementaire": 4,
        "taux_erreur_actuel": 3.2,
    }
    base.update(overrides)
    return base


def orientation_de(**overrides) -> str:
    """Évalue un candidat unique et rend son orientation."""
    return evaluer(pd.DataFrame([candidat(**overrides)])).iloc[0]["orientation"]


# ---------------------------------------------------------------------------
# Charge et notation
# ---------------------------------------------------------------------------

def test_conversion_en_equivalents_temps_plein():
    """La charge se déduit de la volumétrie et du temps unitaire."""
    df = pd.DataFrame([candidat(volumetrie_annuelle=48000, temps_unitaire_min=10)])

    # 48 000 occurrences de 10 minutes font 8 000 heures, soit 5 ETP à 1 600 h.
    assert calculer_charge(df).iloc[0] == 5.0


def test_scores_restent_bornes():
    """Aucune note ne peut sortir de l'échelle, même sur des valeurs extrêmes."""
    df = pd.DataFrame([candidat(
        volumetrie_annuelle=10_000_000,
        temps_unitaire_min=600,
        criticite_reglementaire=99,
        taux_erreur_actuel=250,
    )])

    resultat = noter(df).iloc[0]

    assert 0 <= resultat["score_valeur"] <= 100
    assert 0 <= resultat["score_faisabilite"] <= 100


def test_donnees_manquantes_ne_font_pas_echouer_la_notation():
    """Un référentiel incomplet reste évaluable, avec des valeurs par défaut."""
    df = pd.DataFrame([candidat(
        criticite_reglementaire=None,
        taux_erreur_actuel=None,
        nb_applications=None,
        structuration_donnees="inconnu",
    )])

    resultat = noter(df).iloc[0]

    assert not pd.isna(resultat["score_valeur"])
    assert not pd.isna(resultat["score_faisabilite"])


# ---------------------------------------------------------------------------
# Doctrine d'orientation
# ---------------------------------------------------------------------------

def test_bon_candidat_est_retenu():
    """Un processus volumineux, déterministe et structuré part en automatisation."""
    assert orientation_de() == ORIENTATIONS["automatiser"]


def test_api_disponible_ecarte_la_rpa():
    """
    Lorsqu'une interface applicative existe, piloter l'écran par un robot est
    un contresens technique. Ce contrôle passe avant tous les autres, y compris
    pour un processus par ailleurs excellent candidat.
    """
    assert orientation_de(api_disponible="oui") == ORIENTATIONS["integration"]


def test_charge_insuffisante_est_ecartee():
    """Un processus trop peu volumineux ne rentabilise pas son robot."""
    resultat = orientation_de(volumetrie_annuelle=500, temps_unitaire_min=5)

    assert resultat == ORIENTATIONS["ecarter"]


def test_donnees_non_structurees_orientent_vers_un_projet_hybride():
    """
    Un gisement réel sur des documents non structurés appelle une brique de
    reconnaissance avant le robot, pas un robot seul.
    """
    resultat = orientation_de(
        structuration_donnees="non structuré",
        taux_regles=50,
        stabilite=4,
        volumetrie_annuelle=68000,
        temps_unitaire_min=9,
    )

    assert resultat == ORIENTATIONS["hybride"]


def test_processus_instable_doit_etre_optimise_avant():
    """
    Un gain réel mais un processus dépendant du jugement humain doit être
    simplifié avant d'être automatisé, sous peine de figer le désordre.
    """
    resultat = orientation_de(taux_regles=55, stabilite=3, nb_applications=4)

    assert resultat == ORIENTATIONS["optimiser"]


def test_gain_faible_mais_simple_va_au_backlog():
    """Un processus facile mais peu rentable est conservé comme complément."""
    resultat = orientation_de(
        volumetrie_annuelle=32000,
        temps_unitaire_min=6,
        criticite_reglementaire=3,
        taux_erreur_actuel=2.4,
        taux_regles=90,
    )

    assert resultat == ORIENTATIONS["backlog"]


def test_priorite_aux_automatisations_simples():
    """
    Un projet hybride passe après une automatisation classique même lorsque son
    gisement est supérieur : il est plus long et plus risqué, et le programme
    a choisi de sécuriser les gains rapides d'abord.
    """
    df = pd.DataFrame([
        candidat(process_id="HYBRIDE", volumetrie_annuelle=68000, temps_unitaire_min=9,
                 structuration_donnees="non structuré", taux_regles=50),
        candidat(process_id="SIMPLE", volumetrie_annuelle=30000, temps_unitaire_min=6),
    ])

    resultat = evaluer(df)

    assert resultat.iloc[0]["process_id"] == "SIMPLE"
    assert resultat.iloc[0]["orientation"] == ORIENTATIONS["automatiser"]
    assert resultat.iloc[1]["orientation"] == ORIENTATIONS["hybride"]
    # Le gisement du projet hybride est pourtant nettement supérieur.
    assert resultat.iloc[1]["charge_etp"] > resultat.iloc[0]["charge_etp"]


def test_chaque_orientation_est_justifiee():
    """Toute décision porte une justification exploitable en comité."""
    df = pd.DataFrame([
        candidat(process_id="A"),
        candidat(process_id="B", api_disponible="oui"),
        candidat(process_id="C", volumetrie_annuelle=300),
    ])

    resultat = evaluer(df)

    assert (resultat["justification"].str.len() > 40).all()


# ---------------------------------------------------------------------------
# Restitutions
# ---------------------------------------------------------------------------

def test_synthese_par_orientation_couvre_le_portefeuille():
    """La somme des processus par orientation redonne le portefeuille entier."""
    df = pd.DataFrame([
        candidat(process_id="A"),
        candidat(process_id="B", api_disponible="oui"),
        candidat(process_id="C", volumetrie_annuelle=300),
    ])

    synthese = synthese_par_orientation(evaluer(df))

    assert synthese["nb_processus"].sum() == 3


def test_synthese_par_secteur_distingue_la_charge_retenue():
    """
    La charge retenue ne compte que les processus effectivement automatisables,
    ce qui évite d'annoncer un gain sur un périmètre écarté.
    """
    df = pd.DataFrame([
        candidat(process_id="A", secteur="CMO"),
        candidat(process_id="B", secteur="CMO", api_disponible="oui"),
    ])

    synthese = synthese_par_secteur(evaluer(df)).iloc[0]

    assert synthese["nb_processus"] == 2
    assert synthese["charge_retenue_etp"] < synthese["charge_etp"]


def test_restitution_contient_les_quatre_tableaux():
    """Le classeur d'évaluation est complet."""
    restitution = construire_restitution(evaluer(pd.DataFrame([candidat()])))

    assert set(restitution) == {
        "classement", "synthese_orientation", "synthese_secteur", "detail_notation"
    }


def test_portefeuille_vide_ne_fait_pas_echouer_les_syntheses():
    """Un portefeuille sans candidat rend des tableaux vides, pas une erreur."""
    assert synthese_par_orientation(pd.DataFrame()).empty
    assert synthese_par_secteur(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# Chargement du référentiel
# ---------------------------------------------------------------------------

def test_referentiel_absent_est_signale(tmp_path):
    """L'absence de référentiel lève une erreur dédiée."""
    with pytest.raises(FileNotFoundError):
        charger_candidats(tmp_path)


def test_referentiel_vide_est_signale(tmp_path):
    """Un référentiel de zéro octet est signalé explicitement."""
    (tmp_path / "processus_candidats.csv").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="vide"):
        charger_candidats(tmp_path)


def test_colonne_manquante_est_nommee(tmp_path):
    """Une colonne obligatoire absente est signalée par son nom."""
    (tmp_path / "processus_candidats.csv").write_text(
        "process_id,nom\nTEST-01,Essai\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="volumetrie_annuelle"):
        charger_candidats(tmp_path)


def test_referentiel_livre_est_exploitable():
    """Le référentiel fourni dans le dépôt s'évalue de bout en bout."""
    evaluation = evaluer(charger_candidats())

    assert len(evaluation) >= 15
    # Le référentiel est construit pour illustrer toutes les orientations.
    assert evaluation["orientation"].nunique() == len(ORIENTATIONS)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

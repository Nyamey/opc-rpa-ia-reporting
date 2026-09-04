"""
Grille de sélection des processus candidats à l'automatisation.

Un programme d'automatisation échoue rarement pour des raisons techniques. Il
échoue parce qu'on automatise le mauvais processus : trop peu volumineux pour
rentabiliser le robot, trop instable pour tenir dans le temps, ou reposant sur
un jugement humain qu'aucune règle ne remplace.

Ce module note chaque candidat sur deux axes, la valeur et la faisabilité,
puis en déduit une orientation. Il ne décide pas à la place du comité : il rend
le raisonnement explicite et comparable d'un processus à l'autre.
"""

import logging
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

from config import (
    CANDIDATS_FILE,
    HEURES_ANNUELLES_ETP,
    INPUT_DIR,
    NOTES_STRUCTURATION,
    POIDS_FAISABILITE,
    POIDS_VALEUR,
    SEUIL_ETP_MINIMAL,
    SEUIL_FAISABILITE,
    SEUIL_TAUX_REGLES,
    SEUIL_TAUX_REGLES_HYBRIDE,
    SEUIL_VALEUR,
)
from csv_reader import lire_csv

logger = logging.getLogger(__name__)

COLONNES_REQUISES = [
    "process_id",
    "nom",
    "secteur",
    "perimetre",
    "volumetrie_annuelle",
    "temps_unitaire_min",
    "taux_regles",
    "stabilite",
    "structuration_donnees",
    "nb_applications",
    "api_disponible",
    "criticite_reglementaire",
    "taux_erreur_actuel",
]

# Orientations possibles. L'ordre porte la priorité de traitement.
ORIENTATIONS = {
    "integration": "Intégration applicative",
    "automatiser": "Automatiser en RPA",
    "hybride": "Projet hybride RPA et IA",
    "optimiser": "Optimiser avant d'automatiser",
    "backlog": "Backlog opportuniste",
    "ecarter": "Écarter",
}

PRIORITES = {
    "Automatiser en RPA": 1,
    "Projet hybride RPA et IA": 2,
    "Intégration applicative": 3,
    "Optimiser avant d'automatiser": 4,
    "Backlog opportuniste": 5,
    "Écarter": 6,
}


def charger_candidats(input_dir: Path = INPUT_DIR) -> pd.DataFrame:
    """
    Charge le référentiel des processus candidats.

    Args:
        input_dir: Répertoire contenant le référentiel.

    Returns:
        Le référentiel des candidats.

    Raises:
        FileNotFoundError: Le référentiel est absent.
        ValueError: Le référentiel est vide ou incomplet.
    """
    return lire_csv(
        input_dir / CANDIDATS_FILE,
        "du référentiel des processus candidats",
        COLONNES_REQUISES,
    )


def _note_applications(nombre: float) -> float:
    """
    Note la complexité d'intégration d'après le nombre d'applications.

    Chaque application supplémentaire ajoute une interface à maintenir et un
    point de rupture potentiel. Au-delà de cinq, la fragilité du robot devient
    le premier facteur d'indisponibilité.

    Args:
        nombre: Nombre d'applications traversées par le processus.

    Returns:
        Une note sur cent.
    """
    if pd.isna(nombre):
        return 50.0

    return float(max(0.0, min(100.0, 120.0 - 20.0 * float(nombre))))


def calculer_charge(df: pd.DataFrame) -> pd.Series:
    """
    Convertit la volumétrie et le temps unitaire en équivalents temps plein.

    Args:
        df: Référentiel des candidats.

    Returns:
        La charge annuelle de chaque processus, en ETP.
    """
    volumetrie = pd.to_numeric(df["volumetrie_annuelle"], errors="coerce").fillna(0)
    temps = pd.to_numeric(df["temps_unitaire_min"], errors="coerce").fillna(0)

    heures = volumetrie * temps / 60
    return (heures / HEURES_ANNUELLES_ETP).round(2)


def _note_charge(etp: pd.Series) -> pd.Series:
    """
    Note la charge sur une échelle bornée.

    Le plafond est fixé à cinq ETP : au-delà, un processus est déjà largement
    prioritaire et distinguer huit ETP de douze n'apporte rien à l'arbitrage.

    Args:
        etp: Charge annuelle en équivalents temps plein.

    Returns:
        Une note sur cent.
    """
    return (etp / 5.0 * 100).clip(upper=100.0)


def noter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Attribue à chaque candidat sa note de valeur et sa note de faisabilité.

    Args:
        df: Référentiel des candidats.

    Returns:
        Le référentiel enrichi des notes et de la charge.
    """
    resultat = df.copy()

    resultat["charge_etp"] = calculer_charge(resultat)

    criticite = pd.to_numeric(resultat["criticite_reglementaire"], errors="coerce").fillna(3)
    taux_erreur = pd.to_numeric(resultat["taux_erreur_actuel"], errors="coerce").fillna(0)
    taux_regles = pd.to_numeric(resultat["taux_regles"], errors="coerce").fillna(0)
    stabilite = pd.to_numeric(resultat["stabilite"], errors="coerce").fillna(3)
    applications = pd.to_numeric(resultat["nb_applications"], errors="coerce")

    # Axe valeur. Le taux d'erreur est plafonné à cinq pour cent, seuil au delà
    # duquel un processus est de toute façon considéré comme peu fiable.
    resultat["note_charge"] = _note_charge(resultat["charge_etp"])
    resultat["note_criticite"] = (criticite / 5.0 * 100).clip(0, 100)
    resultat["note_taux_erreur"] = (taux_erreur / 5.0 * 100).clip(0, 100)

    resultat["score_valeur"] = (
        resultat["note_charge"] * POIDS_VALEUR["charge"]
        + resultat["note_criticite"] * POIDS_VALEUR["criticite"]
        + resultat["note_taux_erreur"] * POIDS_VALEUR["taux_erreur"]
    ).round(1)

    # Axe faisabilité
    resultat["note_taux_regles"] = taux_regles.clip(0, 100)
    resultat["note_stabilite"] = (stabilite / 5.0 * 100).clip(0, 100)
    resultat["note_structuration"] = (
        resultat["structuration_donnees"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map(NOTES_STRUCTURATION)
        .fillna(50.0)
    )
    resultat["note_applications"] = applications.map(_note_applications)

    resultat["score_faisabilite"] = (
        resultat["note_taux_regles"] * POIDS_FAISABILITE["taux_regles"]
        + resultat["note_stabilite"] * POIDS_FAISABILITE["stabilite"]
        + resultat["note_structuration"] * POIDS_FAISABILITE["structuration"]
        + resultat["note_applications"] * POIDS_FAISABILITE["applications"]
    ).round(1)

    return resultat


def _orienter(ligne: pd.Series) -> Tuple[str, str]:
    """
    Détermine l'orientation d'un processus et la justifie.

    L'ordre des contrôles porte la doctrine du programme. La disponibilité
    d'une interface applicative est examinée en premier : lorsqu'un système
    expose une API, faire piloter son écran par un robot est un contresens
    technique, plus fragile et plus coûteux à maintenir qu'une intégration.

    Args:
        ligne: Processus déjà noté.

    Returns:
        Le couple (orientation, justification).
    """
    api = str(ligne.get("api_disponible", "non")).strip().lower() in ("oui", "o", "true", "1")
    valeur = ligne["score_valeur"]
    faisabilite = ligne["score_faisabilite"]
    charge = ligne["charge_etp"]
    structuration = str(ligne.get("structuration_donnees", "")).strip().lower()
    regles = ligne["note_taux_regles"]

    if api:
        return (
            ORIENTATIONS["integration"],
            "Une interface applicative existe. Un robot pilotant l'écran serait "
            "plus fragile et plus coûteux à maintenir qu'une intégration directe.",
        )

    if charge < SEUIL_ETP_MINIMAL:
        return (
            ORIENTATIONS["ecarter"],
            f"La charge de {charge} ETP ne rentabilise pas la construction et la "
            f"maintenance d'un robot, même si le processus est techniquement simple.",
        )

    if valeur < SEUIL_VALEUR:
        if faisabilite >= SEUIL_FAISABILITE:
            return (
                ORIENTATIONS["backlog"],
                "Techniquement simple mais gain limité. À retenir comme complément "
                "si un robot du même périmètre est déjà construit.",
            )
        return (
            ORIENTATIONS["ecarter"],
            "Ni le gain ni la faisabilité ne justifient une automatisation.",
        )

    # À partir d'ici le gain est établi. Restent deux critères éliminatoires,
    # que la moyenne pondérée ne doit pas pouvoir compenser.

    # Un robot ne sait pas lire un document. Quelle que soit la stabilité du
    # processus, une donnée non structurée impose une brique de reconnaissance
    # en amont, donc un projet hybride et non une automatisation classique.
    if structuration == "non structuré":
        if regles >= SEUIL_TAUX_REGLES_HYBRIDE:
            return (
                ORIENTATIONS["hybride"],
                "Le gain est réel mais les données d'entrée ne sont pas structurées. "
                "Une brique de reconnaissance documentaire doit précéder le robot.",
            )
        return (
            ORIENTATIONS["optimiser"],
            "Données non structurées et part de jugement humain trop importante. "
            "Même assistée par une reconnaissance documentaire, la chaîne "
            "resterait manuelle dans les faits.",
        )

    if regles < SEUIL_TAUX_REGLES:
        return (
            ORIENTATIONS["optimiser"],
            f"Seuls {regles:.0f} pour cent du traitement suivent des règles "
            f"explicites. Automatiser en l'état reviendrait à figer les "
            f"contournements existants : le processus doit d'abord être simplifié.",
        )

    if faisabilite >= SEUIL_FAISABILITE:
        return (
            ORIENTATIONS["automatiser"],
            f"Charge de {charge} ETP et processus suffisamment déterministe. "
            f"Candidat direct pour une automatisation classique.",
        )

    return (
        ORIENTATIONS["optimiser"],
        "Le gain justifierait l'investissement mais le processus est trop "
        "instable ou traverse trop d'applications. Il doit être fiabilisé "
        "avant toute automatisation.",
    )


def evaluer(df: pd.DataFrame) -> pd.DataFrame:
    """
    Note puis oriente l'ensemble des processus candidats.

    Args:
        df: Référentiel des candidats.

    Returns:
        Le référentiel évalué, trié par priorité puis par charge décroissante.
    """
    logger.info("Évaluation des processus candidats")

    resultat = noter(df)

    orientations = resultat.apply(_orienter, axis=1)
    resultat["orientation"] = [valeur[0] for valeur in orientations]
    resultat["justification"] = [valeur[1] for valeur in orientations]
    resultat["priorite"] = resultat["orientation"].map(PRIORITES)

    resultat = resultat.sort_values(
        ["priorite", "charge_etp"], ascending=[True, False]
    ).reset_index(drop=True)

    resultat["rang"] = range(1, len(resultat) + 1)

    retenus = resultat[resultat["orientation"].isin([
        ORIENTATIONS["automatiser"], ORIENTATIONS["hybride"]
    ])]

    logger.info(
        f"Évaluation terminée : {len(retenus)} processus retenus sur {len(resultat)}, "
        f"représentant {retenus['charge_etp'].sum():.1f} ETP de charge adressable"
    )

    return resultat


def synthese_par_orientation(evaluation: pd.DataFrame) -> pd.DataFrame:
    """
    Résume le portefeuille par orientation.

    Args:
        evaluation: Référentiel évalué.

    Returns:
        Le nombre de processus et la charge cumulée par orientation.
    """
    if evaluation.empty:
        return pd.DataFrame(columns=["orientation", "nb_processus", "charge_etp"])

    synthese = evaluation.groupby("orientation").agg(
        nb_processus=("process_id", "count"),
        charge_etp=("charge_etp", "sum"),
    ).reset_index()

    synthese["charge_etp"] = synthese["charge_etp"].round(2)
    synthese["priorite"] = synthese["orientation"].map(PRIORITES)

    return synthese.sort_values("priorite").drop(columns="priorite").reset_index(drop=True)


def synthese_par_secteur(evaluation: pd.DataFrame) -> pd.DataFrame:
    """
    Résume le portefeuille par secteur opérationnel.

    Cette vue sert aux échanges avec les responsables de secteur, qui
    raisonnent sur leur périmètre et non sur le portefeuille global.

    Args:
        evaluation: Référentiel évalué.

    Returns:
        Le nombre de processus, la charge totale et la charge retenue par secteur.
    """
    if evaluation.empty:
        return pd.DataFrame(columns=["secteur", "nb_processus", "charge_etp", "charge_retenue_etp"])

    retenus = [ORIENTATIONS["automatiser"], ORIENTATIONS["hybride"]]
    travail = evaluation.copy()
    travail["charge_retenue"] = travail["charge_etp"].where(
        travail["orientation"].isin(retenus), 0.0
    )

    synthese = travail.groupby("secteur").agg(
        nb_processus=("process_id", "count"),
        charge_etp=("charge_etp", "sum"),
        charge_retenue_etp=("charge_retenue", "sum"),
    ).reset_index()

    synthese["charge_etp"] = synthese["charge_etp"].round(2)
    synthese["charge_retenue_etp"] = synthese["charge_retenue_etp"].round(2)

    return synthese.sort_values("charge_retenue_etp", ascending=False).reset_index(drop=True)


def construire_restitution(evaluation: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Assemble les tableaux de restitution de l'évaluation.

    Args:
        evaluation: Référentiel évalué.

    Returns:
        Un dictionnaire de tableaux, un par feuille du classeur.
    """
    colonnes_classement = [
        "rang", "process_id", "nom", "secteur", "perimetre", "charge_etp",
        "score_valeur", "score_faisabilite", "orientation", "justification",
    ]

    colonnes_detail = colonnes_classement[:-1] + [
        "volumetrie_annuelle", "temps_unitaire_min", "taux_regles", "stabilite",
        "structuration_donnees", "nb_applications", "api_disponible",
        "criticite_reglementaire", "taux_erreur_actuel",
        "note_charge", "note_criticite", "note_taux_erreur",
        "note_taux_regles", "note_stabilite", "note_structuration", "note_applications",
        "justification",
    ]

    return {
        "classement": evaluation[colonnes_classement],
        "synthese_orientation": synthese_par_orientation(evaluation),
        "synthese_secteur": synthese_par_secteur(evaluation),
        "detail_notation": evaluation[colonnes_detail],
    }

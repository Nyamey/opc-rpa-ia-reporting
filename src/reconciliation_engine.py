"""
Moteur de réconciliation.

Compare les transactions du Système A et du Système B, puis identifie les
écarts. Deux lignes sont rapprochées lorsque toutes les clés de rapprochement
définies dans la configuration sont identiques ; le montant est ensuite
comparé séparément avec une tolérance.
"""

import logging
from pathlib import Path
from typing import Tuple

import pandas as pd

from config import (
    AMOUNT_TOLERANCE,
    INPUT_DIR,
    MATCH_KEYS,
    REQUIRED_COLUMNS,
    SYSTEM_A_FILE,
    SYSTEM_B_FILE,
)
from csv_reader import lire_csv

logger = logging.getLogger(__name__)


def load_and_validate_files(input_dir: Path = INPUT_DIR) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Charge et valide les deux fichiers de transactions.

    Le séparateur et l'encodage sont reconnus automatiquement : un fichier
    exporté depuis un tableur français, en point-virgule et en page de code
    Windows, est accepté sans conversion préalable.

    Args:
        input_dir: Répertoire contenant les fichiers d'entrée.

    Returns:
        Le couple (transactions du Système A, transactions du Système B).

    Raises:
        FileNotFoundError: Un des fichiers d'entrée est absent.
        ValueError: Un fichier est vide ou mal formé.
    """
    df_a = lire_csv(input_dir / SYSTEM_A_FILE, "du Système A", REQUIRED_COLUMNS)
    df_b = lire_csv(input_dir / SYSTEM_B_FILE, "du Système B", REQUIRED_COLUMNS)
    return df_a, df_b


def _prepare(df: pd.DataFrame, system_name: str) -> pd.DataFrame:
    """
    Normalise un jeu de transactions avant le rapprochement.

    Les clés de rapprochement sont converties en texte épuré afin qu'un
    identifiant numérique d'un côté et textuel de l'autre soient bien
    rapprochés. Les montants sont convertis en nombres : une valeur
    illisible devient NaN plutôt que de faire échouer le traitement.

    Args:
        df: Transactions brutes issues du fichier d'entrée.
        system_name: Libellé du système, utilisé dans les avertissements.

    Returns:
        Une copie normalisée du DataFrame.
    """
    df = df.copy()

    # Un fichier sans aucune ligne peut arriver sans colonnes du tout.
    # On rétablit le schéma attendu pour que la fusion reste possible.
    if df.empty:
        df = pd.DataFrame(columns=REQUIRED_COLUMNS)

    for key in MATCH_KEYS:
        df[key] = df[key].astype(str).str.strip()

    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    unreadable = int(df["amount"].isna().sum())
    if unreadable:
        logger.warning(
            f"{system_name} : {unreadable} montant(s) illisible(s) ou absent(s). "
            f"Ces transactions seront signalées comme écarts à revoir."
        )

    duplicates = int(df.duplicated(subset=MATCH_KEYS).sum())
    if duplicates:
        logger.warning(
            f"{system_name} : {duplicates} ligne(s) partagent les mêmes clés de "
            f"rapprochement. Le rapprochement risque de produire des doublons, "
            f"il est conseillé de dédoublonner le fichier source."
        )

    return df


def _build_break(row: pd.Series, break_type: str, details: str) -> dict:
    """
    Construit l'enregistrement d'un écart à partir d'une ligne fusionnée.

    Args:
        row: Ligne issue de la fusion des deux systèmes.
        break_type: Nature de l'écart.
        details: Description lisible de l'écart.

    Returns:
        Un dictionnaire prêt à être ajouté au tableau des écarts.
    """
    return {
        "trade_id": row["trade_id"],
        "counterparty": row["counterparty"],
        "product": row["product"],
        "trade_date": row["trade_date"],
        "currency": row["currency"],
        "amount_a": row["amount_a"],
        "amount_b": row["amount_b"],
        "break_type": break_type,
        "break_details": details,
    }


def reconcile(df_a: pd.DataFrame, df_b: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Rapproche les transactions des deux systèmes et isole les écarts.

    Quatre natures d'écart sont produites :
      - `amount` : la transaction existe des deux côtés mais les montants
        diffèrent au-delà de la tolérance ;
      - `amount_invalid` : la transaction existe des deux côtés mais au moins
        un montant est absent ou illisible, la comparaison est impossible ;
      - `missing_B` : la transaction n'existe que dans le Système A ;
      - `missing_A` : la transaction n'existe que dans le Système B.

    Un écart de date ou de devise se traduit mécaniquement par un couple
    `missing_A` et `missing_B`, puisque ces deux colonnes font partie des
    clés de rapprochement.

    Args:
        df_a: Transactions du Système A.
        df_b: Transactions du Système B.

    Returns:
        Le couple (transactions rapprochées, écarts).
    """
    logger.info("Démarrage du rapprochement")

    df_a = _prepare(df_a, "Système A")
    df_b = _prepare(df_b, "Système B")

    # Deux extractions sans aucune ligne constituent un cas légitime, un jour
    # sans activité par exemple. La fusion est court-circuitée car elle échoue
    # sur des colonnes vides des deux côtés, avec une erreur interne de la
    # bibliothèque qui n'apprendrait rien à un exploitant.
    if df_a.empty and df_b.empty:
        logger.warning(
            "Les deux systèmes sont dépourvus de transaction. "
            "Vérifiez que les extractions amont ont bien abouti."
        )
        return pd.DataFrame(), pd.DataFrame()

    merged = pd.merge(
        df_a,
        df_b,
        on=MATCH_KEYS,
        how="outer",
        indicator=True,
        suffixes=("_a", "_b"),
    )

    breaks_raw = []
    matched_transactions = []

    for _, row in merged.iterrows():
        origin = row["_merge"]

        if origin == "left_only":
            breaks_raw.append(
                _build_break(row, "missing_B", "Transaction absente du Système B")
            )
            continue

        if origin == "right_only":
            breaks_raw.append(
                _build_break(row, "missing_A", "Transaction absente du Système A")
            )
            continue

        amount_a = row["amount_a"]
        amount_b = row["amount_b"]

        # Un montant manquant des deux côtés donnerait une différence NaN,
        # que toute comparaison évalue à False. Sans ce contrôle explicite,
        # la transaction serait comptée comme rapprochée à tort.
        if pd.isna(amount_a) or pd.isna(amount_b):
            breaks_raw.append(
                _build_break(
                    row,
                    "amount_invalid",
                    f"Montant absent ou illisible (A : {amount_a}, B : {amount_b})",
                )
            )
            continue

        if abs(amount_a - amount_b) > AMOUNT_TOLERANCE:
            breaks_raw.append(
                _build_break(
                    row,
                    "amount",
                    f"Différence de montant : {amount_a} contre {amount_b}",
                )
            )
            continue

        matched_transactions.append(row)

    breaks_df = pd.DataFrame(breaks_raw)
    matched_df = pd.DataFrame(matched_transactions)

    logger.info(
        f"Rapprochement terminé : {len(matched_df)} transaction(s) rapprochée(s), "
        f"{len(breaks_df)} écart(s)"
    )

    return matched_df, breaks_df

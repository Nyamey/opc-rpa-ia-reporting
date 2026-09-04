"""
Calcul des indicateurs de pilotage.

À partir des transactions rapprochées et des écarts, ce module produit le
tableau de synthèse ainsi que les répartitions d'écarts par motif, par
contrepartie, par produit et par nature.
"""

import logging
from datetime import datetime
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


def _count_by(breaks_df: pd.DataFrame, column: str) -> pd.DataFrame:
    """
    Compte les écarts par valeur d'une colonne, du plus fréquent au moins
    fréquent.

    Args:
        breaks_df: Tableau des écarts.
        column: Colonne servant de critère de regroupement.

    Returns:
        Un tableau à deux colonnes : le critère et le nombre d'écarts. Le
        tableau est vide si la colonne est absente, ce qui permet d'appeler
        cette fonction avant la classification sans provoquer d'erreur.
    """
    if breaks_df.empty or column not in breaks_df.columns:
        return pd.DataFrame(columns=[column, "count"])

    counts = breaks_df.groupby(column).size().reset_index(name="count")
    return counts.sort_values("count", ascending=False).reset_index(drop=True)


def _total_break_amount(breaks_df: pd.DataFrame) -> float:
    """
    Additionne l'exposition portée par les écarts.

    Pour une différence de montant, seul l'écart est compté. Pour une
    transaction absente d'un système, le montant connu est compté en entier.

    Args:
        breaks_df: Tableau des écarts.

    Returns:
        Le montant cumulé, arrondi au centime.
    """
    if breaks_df.empty or not {"amount_a", "amount_b"} <= set(breaks_df.columns):
        return 0.0

    amount_a = pd.to_numeric(breaks_df["amount_a"], errors="coerce").fillna(0)
    amount_b = pd.to_numeric(breaks_df["amount_b"], errors="coerce").fillna(0)

    return round(float((amount_a - amount_b).abs().sum()), 2)


def compute_kpis(matched_df: pd.DataFrame, breaks_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Calcule les indicateurs de la campagne de réconciliation.

    Le taux de rapprochement rapporte le nombre de transactions rapprochées
    au nombre de transactions distinctes présentes dans au moins un des deux
    systèmes. Une transaction absente d'un système compte donc pour une seule
    unité au dénominateur, et non pour deux.

    Args:
        matched_df: Transactions rapprochées.
        breaks_df: Écarts, classifiés ou non.

    Returns:
        Un dictionnaire de tableaux, un par feuille du rapport Excel.
    """
    logger.info("Calcul des indicateurs")

    matched_count = len(matched_df)
    breaks_count = len(breaks_df)
    total = matched_count + breaks_count
    match_rate = (matched_count / total * 100) if total > 0 else 100.0

    kpi_summary = pd.DataFrame([{
        "total_transactions": total,
        "matched_count": matched_count,
        "breaks_count": breaks_count,
        "match_rate": round(match_rate, 2),
        "total_break_amount": _total_break_amount(breaks_df),
        "calculation_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }])

    logger.info(
        f"Indicateurs calculés : taux de rapprochement {match_rate:.2f} %, "
        f"{breaks_count} écart(s)"
    )

    return {
        "kpi_summary": kpi_summary,
        "breaks_by_reason": _count_by(breaks_df, "suggested_reason"),
        "breaks_by_counterparty": _count_by(breaks_df, "counterparty"),
        "breaks_by_product": _count_by(breaks_df, "product"),
        "breaks_by_type": _count_by(breaks_df, "break_type"),
    }

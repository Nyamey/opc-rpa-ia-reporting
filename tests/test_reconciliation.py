"""
Tests unitaires du moteur de réconciliation, du calcul des indicateurs et de
la classification des écarts.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kpi_calculator import compute_kpis
from llm_classifier import classify_breaks
from reconciliation_engine import load_and_validate_files, reconcile


def transaction(**overrides) -> dict:
    """
    Fabrique une transaction de référence, personnalisable par mot-clé.

    Args:
        overrides: Champs à remplacer dans la transaction de référence.

    Returns:
        Une transaction complète sous forme de dictionnaire.
    """
    base = {
        "trade_id": "TR001",
        "counterparty": "Bank A",
        "product": "Swap",
        "trade_date": "2026-01-15",
        "amount": 1_000_000.00,
        "currency": "USD",
    }
    base.update(overrides)
    return base


def test_rapprochement_parfait():
    """Deux fichiers identiques ne doivent produire aucun écart."""
    df_a = pd.DataFrame([transaction()])
    df_b = df_a.copy()

    matched_df, breaks_df = reconcile(df_a, df_b)

    assert len(matched_df) == 1
    assert len(breaks_df) == 0


def test_ecart_de_montant():
    """Une différence de montant au-delà de la tolérance devient un écart."""
    df_a = pd.DataFrame([transaction(trade_id="TR002", amount=500_000.00)])
    df_b = pd.DataFrame([transaction(trade_id="TR002", amount=500_000.50)])

    matched_df, breaks_df = reconcile(df_a, df_b)

    assert len(matched_df) == 0
    assert len(breaks_df) == 1
    assert breaks_df.iloc[0]["break_type"] == "amount"


def test_ecart_de_montant_dans_la_tolerance():
    """Une différence inférieure à la tolérance reste un rapprochement."""
    df_a = pd.DataFrame([transaction(amount=500_000.000)])
    df_b = pd.DataFrame([transaction(amount=500_000.005)])

    matched_df, breaks_df = reconcile(df_a, df_b)

    assert len(matched_df) == 1
    assert len(breaks_df) == 0


def test_transaction_absente_du_systeme_b():
    """Un Système B totalement vide ne doit pas faire échouer le traitement."""
    df_a = pd.DataFrame([transaction(trade_id="TR009")])
    df_b = pd.DataFrame()

    matched_df, breaks_df = reconcile(df_a, df_b)

    assert len(matched_df) == 0
    assert len(breaks_df) == 1
    assert breaks_df.iloc[0]["break_type"] == "missing_B"


def test_transaction_absente_du_systeme_a():
    """Une transaction connue du seul Système B est signalée."""
    df_a = pd.DataFrame()
    df_b = pd.DataFrame([transaction(trade_id="TR010")])

    matched_df, breaks_df = reconcile(df_a, df_b)

    assert len(matched_df) == 0
    assert len(breaks_df) == 1
    assert breaks_df.iloc[0]["break_type"] == "missing_A"


def test_deux_systemes_sans_transaction():
    """
    Deux extractions vides constituent un cas légitime, un jour sans activité
    par exemple. Le traitement doit aboutir plutôt que d'échouer sur une erreur
    interne de la bibliothèque de fusion.
    """
    matched_df, breaks_df = reconcile(pd.DataFrame(), pd.DataFrame())

    assert matched_df.empty
    assert breaks_df.empty


def test_indicateurs_sur_deux_systemes_vides():
    """Sans aucune transaction, le taux de rapprochement reste défini."""
    matched_df, breaks_df = reconcile(pd.DataFrame(), pd.DataFrame())
    summary = compute_kpis(matched_df, breaks_df)["kpi_summary"].iloc[0]

    assert summary["total_transactions"] == 0
    assert summary["match_rate"] == 100.0


def test_ecart_de_devise():
    """
    La devise faisant partie des clés, une divergence produit deux écarts
    symétriques plutôt qu'un rapprochement erroné.
    """
    df_a = pd.DataFrame([transaction(currency="EUR")])
    df_b = pd.DataFrame([transaction(currency="USD")])

    matched_df, breaks_df = reconcile(df_a, df_b)

    assert len(matched_df) == 0
    assert set(breaks_df["break_type"]) == {"missing_A", "missing_B"}


def test_montant_illisible_nest_pas_rapproche():
    """
    Un montant vide des deux côtés donne une différence indéterminée. Sans
    contrôle explicite la transaction serait comptée comme rapprochée.
    """
    df_a = pd.DataFrame([transaction(amount=None)])
    df_b = pd.DataFrame([transaction(amount=None)])

    matched_df, breaks_df = reconcile(df_a, df_b)

    assert len(matched_df) == 0
    assert breaks_df.iloc[0]["break_type"] == "amount_invalid"


def test_montant_textuel_est_converti():
    """Un montant écrit sous forme de texte reste comparable."""
    df_a = pd.DataFrame([transaction(amount="1000000.00")])
    df_b = pd.DataFrame([transaction(amount=1_000_000.00)])

    matched_df, breaks_df = reconcile(df_a, df_b)

    assert len(matched_df) == 1
    assert len(breaks_df) == 0


def test_cles_avec_espaces_superflus():
    """Les espaces autour des clés ne doivent pas empêcher le rapprochement."""
    df_a = pd.DataFrame([transaction(trade_id=" TR001 ", counterparty="Bank A ")])
    df_b = pd.DataFrame([transaction(trade_id="TR001", counterparty="Bank A")])

    matched_df, breaks_df = reconcile(df_a, df_b)

    assert len(matched_df) == 1
    assert len(breaks_df) == 0


def test_calcul_des_indicateurs():
    """La synthèse reprend les volumes et le taux de rapprochement."""
    matched_df = pd.DataFrame([transaction()])
    breaks_df = pd.DataFrame([{
        "trade_id": "TR002",
        "counterparty": "Bank B",
        "product": "Forward",
        "trade_date": "2026-01-15",
        "currency": "EUR",
        "amount_a": 500_000.00,
        "amount_b": 500_000.50,
        "break_type": "amount",
        "break_details": "Différence de montant",
    }])

    kpis = compute_kpis(matched_df, breaks_df)
    summary = kpis["kpi_summary"].iloc[0]

    assert summary["total_transactions"] == 2
    assert summary["matched_count"] == 1
    assert summary["breaks_count"] == 1
    assert summary["match_rate"] == 50.0
    assert summary["total_break_amount"] == 0.50


def test_indicateurs_sans_ecart():
    """Sans aucun écart, le taux de rapprochement vaut cent pour cent."""
    kpis = compute_kpis(pd.DataFrame([transaction()]), pd.DataFrame())
    summary = kpis["kpi_summary"].iloc[0]

    assert summary["match_rate"] == 100.0
    assert summary["breaks_count"] == 0
    assert kpis["breaks_by_reason"].empty


def test_classification_par_regles():
    """Chaque nature d'écart reçoit un motif et une action exploitables."""
    breaks_df = pd.DataFrame([
        {"break_type": "amount", "counterparty": "Bank A"},
        {"break_type": "missing_A", "counterparty": "Bank B"},
        {"break_type": "missing_B", "counterparty": "Bank C"},
        {"break_type": "amount_invalid", "counterparty": "Bank D"},
    ])

    classified = classify_breaks(breaks_df)

    assert (classified["suggested_reason"] != "").all()
    assert (classified["suggested_action"] != "").all()
    assert (classified["confidence"] > 0).all()
    assert "Bank A" in classified.iloc[0]["suggested_action"]


def test_fichier_vide_rejete(tmp_path):
    """Un fichier d'entrée vide produit un message d'erreur explicite."""
    (tmp_path / "transactions_systemA.csv").write_text("", encoding="utf-8")
    (tmp_path / "transactions_systemB.csv").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="vide"):
        load_and_validate_files(tmp_path)


def test_colonne_manquante_rejetee(tmp_path):
    """Une colonne obligatoire absente est signalée par son nom."""
    complet = "trade_id,counterparty,product,trade_date,amount,currency\nTR1,B,Swap,2026-01-15,1,EUR\n"
    incomplet = "trade_id,counterparty,product,trade_date,amount\nTR1,B,Swap,2026-01-15,1\n"

    (tmp_path / "transactions_systemA.csv").write_text(complet, encoding="utf-8")
    (tmp_path / "transactions_systemB.csv").write_text(incomplet, encoding="utf-8")

    with pytest.raises(ValueError, match="currency"):
        load_and_validate_files(tmp_path)


def test_fichier_absent_rejete(tmp_path):
    """L'absence d'un fichier d'entrée lève une erreur dédiée."""
    with pytest.raises(FileNotFoundError):
        load_and_validate_files(tmp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

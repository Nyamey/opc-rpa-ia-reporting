"""
Tests de la couche d'export destinée à Power BI.

Ces tests portent principalement sur la stabilité du schéma et sur
l'historisation, qui sont les deux propriétés dont dépend le bon
rafraîchissement du rapport.
"""

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kpi_calculator import compute_kpis
from powerbi_export import (
    BREAKS_COLUMNS,
    BREAKS_HISTORY_COLUMNS,
    HISTORY_COLUMNS,
    MATCHED_COLUMNS,
    export_for_powerbi,
)


def matched_sample() -> pd.DataFrame:
    """Fabrique une transaction rapprochée."""
    return pd.DataFrame([{
        "trade_id": "TR001",
        "counterparty": "Bank A",
        "product": "Swap",
        "trade_date": "2026-01-15",
        "currency": "USD",
        "amount_a": 1_000_000.00,
        "amount_b": 1_000_000.00,
    }])


def breaks_sample() -> pd.DataFrame:
    """Fabrique un écart de montant déjà qualifié."""
    return pd.DataFrame([{
        "trade_id": "TR002",
        "counterparty": "Bank B",
        "product": "Forward",
        "trade_date": "2026-01-16",
        "currency": "EUR",
        "amount_a": 500_000.00,
        "amount_b": 500_500.00,
        "break_type": "amount",
        "break_details": "Différence de montant",
        "suggested_reason": "Erreur de saisie du montant",
        "suggested_action": "Vérifier avec le middle office",
        "confidence": 0.8,
    }])


def read(path: str) -> pd.DataFrame:
    """Relit une table exportée."""
    return pd.read_csv(path, encoding="utf-8-sig")


def test_toutes_les_tables_sont_produites(tmp_path):
    """Chaque exécution dépose l'intégralité du jeu de tables."""
    kpis = compute_kpis(matched_sample(), breaks_sample())
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    assert set(paths) == {
        "fact_breaks",
        "fact_matched",
        "fact_breaks_history",
        "kpi_history",
        "dim_break_type",
        "dim_date",
    }
    for path in paths.values():
        assert Path(path).exists()


def test_schema_stable_sans_ecart(tmp_path):
    """
    Sans aucun écart, la table de faits conserve toutes ses colonnes. C'est
    cette propriété qui évite un échec de rafraîchissement les jours où le
    rapprochement est parfait.
    """
    kpis = compute_kpis(matched_sample(), pd.DataFrame())
    paths = export_for_powerbi(kpis, matched_sample(), pd.DataFrame(), tmp_path)

    breaks = read(paths["fact_breaks"])

    assert list(breaks.columns) == BREAKS_COLUMNS
    assert breaks.empty


def test_schema_stable_sans_rapprochement(tmp_path):
    """Symétriquement, la table des transactions rapprochées garde son schéma."""
    kpis = compute_kpis(pd.DataFrame(), breaks_sample())
    paths = export_for_powerbi(kpis, pd.DataFrame(), breaks_sample(), tmp_path)

    matched = read(paths["fact_matched"])

    assert list(matched.columns) == MATCHED_COLUMNS
    assert matched.empty


def test_exposition_calculee_par_ecart(tmp_path):
    """L'exposition d'un écart de montant est la différence en valeur absolue."""
    kpis = compute_kpis(matched_sample(), breaks_sample())
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    breaks = read(paths["fact_breaks"])

    assert breaks.iloc[0]["break_amount"] == 500.0


def test_exposition_dune_transaction_absente(tmp_path):
    """
    Une transaction absente d'un système compte pour son montant entier,
    puisque c'est bien ce montant qui est en risque.
    """
    absente = breaks_sample()
    absente.loc[0, "amount_b"] = None
    absente.loc[0, "break_type"] = "missing_B"

    kpis = compute_kpis(pd.DataFrame(), absente)
    paths = export_for_powerbi(kpis, pd.DataFrame(), absente, tmp_path)

    breaks = read(paths["fact_breaks"])

    assert breaks.iloc[0]["break_amount"] == 500_000.00


def test_chaque_execution_est_conservee(tmp_path):
    """
    Deux exécutions successives laissent deux lignes. C'est la propriété qui
    fait exister l'historique : la remplacer par un grain journalier revenait
    à n'avoir jamais qu'une seule ligne en pratique.
    """
    kpis = compute_kpis(matched_sample(), breaks_sample())

    export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)
    time.sleep(1.1)  # Les identifiants d'exécution sont datés à la seconde.
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    history = read(paths["kpi_history"])

    assert len(history) == 2
    assert list(history.columns) == HISTORY_COLUMNS


def test_derniere_execution_du_jour_est_marquee(tmp_path):
    """
    Une seule exécution par journée porte le drapeau, ce qui permet au rapport
    de tracer un point par jour sans perdre la trace des rejeux.
    """
    kpis = compute_kpis(matched_sample(), breaks_sample())

    export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)
    time.sleep(1.1)
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    history = read(paths["kpi_history"])

    assert history["est_derniere_du_jour"].sum() == 1
    assert history.iloc[-1]["est_derniere_du_jour"] == 1


def test_historique_reprend_les_journees_anterieures(tmp_path):
    """Une exécution d'un jour antérieur est conservée, pas écrasée."""
    kpis = compute_kpis(matched_sample(), breaks_sample())
    history_path = tmp_path / "kpi_history.csv"

    ancienne = pd.DataFrame([{
        "run_id": "20260101_090000",
        "run_date": "2026-01-01",
        "run_timestamp": "2026-01-01 09:00:00",
        "total_transactions": 10,
        "matched_count": 9,
        "breaks_count": 1,
        "match_rate": 90.0,
        "total_break_amount": 100.0,
        "est_derniere_du_jour": 1,
    }])
    ancienne.to_csv(history_path, index=False, encoding="utf-8-sig")

    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)
    history = read(paths["kpi_history"])

    assert len(history) == 2
    assert "2026-01-01" in history["run_date"].astype(str).values


def historique_ecarts(jours: list, trade_id: str = "TR002") -> pd.DataFrame:
    """
    Fabrique un historique d'écarts couvrant les journées indiquées.

    Args:
        jours: Journées de présence de l'écart, au format ISO.
        trade_id: Identifiant de la transaction concernée.

    Returns:
        L'historique au schéma attendu.
    """
    cle = f"{trade_id}|Bank B|Forward|2026-01-16|EUR|amount"
    lignes = [{
        "run_date": jour,
        "run_id": jour.replace("-", "") + "_080000",
        "break_key": cle,
        "trade_id": trade_id,
        "counterparty": "Bank B",
        "product": "Forward",
        "trade_date": "2026-01-16",
        "currency": "EUR",
        "break_type": "amount",
        "break_amount": 500.0,
        "suggested_reason": "Erreur de saisie du montant",
        "confidence": 0.8,
    } for jour in jours]

    return pd.DataFrame(lignes)[BREAKS_HISTORY_COLUMNS]


def test_cles_decarts_ne_se_collisionnent_pas(tmp_path):
    """
    Deux écarts distincts dont les attributs contiennent le séparateur ne
    doivent pas partager la même clé, sans quoi ils partageraient aussi leur
    ancienneté.
    """
    premier = breaks_sample()
    premier.loc[0, "counterparty"] = "A|B"
    premier.loc[0, "product"] = "C"

    second = breaks_sample()
    second.loc[0, "trade_id"] = "TR003"
    second.loc[0, "counterparty"] = "A"
    second.loc[0, "product"] = "B|C"

    ecarts = pd.concat([premier, second], ignore_index=True)
    kpis = compute_kpis(pd.DataFrame(), ecarts)
    paths = export_for_powerbi(kpis, pd.DataFrame(), ecarts, tmp_path)

    cles = read(paths["fact_breaks"])["break_key"]

    assert cles.nunique() == 2


def test_ecart_nouveau_a_une_anciennete_nulle(tmp_path):
    """Un écart jamais vu auparavant est ouvert depuis zéro jour."""
    kpis = compute_kpis(matched_sample(), breaks_sample())
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    breaks = read(paths["fact_breaks"])

    assert breaks.iloc[0]["days_open"] == 0


def test_anciennete_dun_ecart_persistant(tmp_path):
    """
    Un écart déjà présent les jours précédents porte sa date de première
    détection et son ancienneté. C'est cette information qui distingue un écart
    du matin d'un écart qui traîne depuis une semaine.
    """
    aujourdhui = datetime.now().date()
    veille = (aujourdhui - timedelta(days=1)).strftime("%Y-%m-%d")
    origine = (aujourdhui - timedelta(days=6)).strftime("%Y-%m-%d")

    historique_ecarts([origine, veille]).to_csv(
        tmp_path / "fact_breaks_history.csv", index=False, encoding="utf-8-sig"
    )

    kpis = compute_kpis(matched_sample(), breaks_sample())
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    breaks = read(paths["fact_breaks"])

    assert breaks.iloc[0]["first_seen_date"] == origine
    assert breaks.iloc[0]["days_open"] == 6


def test_rejeu_du_jour_ne_gonfle_pas_lhistorique_des_ecarts(tmp_path):
    """
    Plusieurs exécutions le même jour ne laissent qu'une ligne par écart et par
    journée. Sans cette règle, dix essais successifs feraient croire à dix
    journées d'ancienneté.
    """
    kpis = compute_kpis(matched_sample(), breaks_sample())

    export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)
    export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    history = read(paths["fact_breaks_history"])

    assert len(history) == 1


def test_ecart_resolu_disparait_du_detail_mais_reste_dans_lhistorique(tmp_path):
    """
    Un écart corrigé sort de la photographie du jour tout en restant traçable
    dans l'historique, ce qui permet de mesurer le délai de résolution.
    """
    veille = (datetime.now().date() - timedelta(days=1)).strftime("%Y-%m-%d")
    historique_ecarts([veille]).to_csv(
        tmp_path / "fact_breaks_history.csv", index=False, encoding="utf-8-sig"
    )

    kpis = compute_kpis(matched_sample(), pd.DataFrame())
    paths = export_for_powerbi(kpis, matched_sample(), pd.DataFrame(), tmp_path)

    assert read(paths["fact_breaks"]).empty
    assert len(read(paths["fact_breaks_history"])) == 1


def test_historique_des_ecarts_corrompu_est_reconstruit(tmp_path):
    """Un historique d'écarts illisible ne bloque pas la production du jour."""
    (tmp_path / "fact_breaks_history.csv").write_bytes(b"\x00\x01pas un CSV\x02")

    kpis = compute_kpis(matched_sample(), breaks_sample())
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    assert len(read(paths["fact_breaks_history"])) == 1


def test_historique_corrompu_est_reconstruit(tmp_path):
    """Un historique illisible ne doit pas faire échouer la production du jour."""
    (tmp_path / "kpi_history.csv").write_bytes(b"\x00\x01ceci n'est pas un CSV\x02")

    kpis = compute_kpis(matched_sample(), breaks_sample())
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    history = read(paths["kpi_history"])

    assert len(history) == 1


def test_calendrier_couvre_les_dates_historisees(tmp_path):
    """
    Le calendrier doit englober les dates d'exécution déjà historisées, sans
    quoi les points de tendance anciens perdraient leur lien avec la table de
    dates.
    """
    history_path = tmp_path / "kpi_history.csv"
    pd.DataFrame([{
        "run_id": "20260101_090000",
        "run_date": "2026-01-01",
        "run_timestamp": "2026-01-01 09:00:00",
        "total_transactions": 10,
        "matched_count": 9,
        "breaks_count": 1,
        "match_rate": 90.0,
        "total_break_amount": 100.0,
        "est_derniere_du_jour": 1,
    }]).to_csv(history_path, index=False, encoding="utf-8-sig")

    kpis = compute_kpis(matched_sample(), breaks_sample())
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    calendrier = read(paths["dim_date"])["date"].astype(str).tolist()

    assert "2026-01-01" in calendrier
    assert "2026-01-16" in calendrier


def test_calendrier_est_continu(tmp_path):
    """Le calendrier ne saute aucune journée, même sans transaction."""
    kpis = compute_kpis(matched_sample(), breaks_sample())
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    calendrier = pd.to_datetime(read(paths["dim_date"])["date"])
    ecarts = calendrier.diff().dropna().dt.days.unique()

    assert list(ecarts) == [1]


def test_referentiel_des_natures_est_complet(tmp_path):
    """Le référentiel couvre les quatre natures produites par le moteur."""
    kpis = compute_kpis(matched_sample(), breaks_sample())
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    natures = set(read(paths["dim_break_type"])["break_type"])

    assert natures == {"amount", "amount_invalid", "missing_A", "missing_B"}


def test_accents_relisibles(tmp_path):
    """L'encodage retenu restitue les accents à la relecture."""
    kpis = compute_kpis(matched_sample(), breaks_sample())
    paths = export_for_powerbi(kpis, matched_sample(), breaks_sample(), tmp_path)

    libelles = read(paths["dim_break_type"])["libelle"].tolist()

    assert "Écart de montant" in libelles


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

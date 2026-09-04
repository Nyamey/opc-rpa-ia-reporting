"""
Export des données destinées à Power BI.

Le classeur Excel est conçu pour être lu par un humain : ses feuilles varient
selon le contenu et disparaissent lorsqu'elles sont vides. Ce comportement
convient mal à un outil décisionnel, qui exige un schéma constant sous peine
d'échouer au rafraîchissement.

Ce module produit donc un jeu de tables séparé, toujours présent et toujours
composé des mêmes colonnes, organisé en modèle en étoile.

Il tient également deux historiques, sans lesquels le rapport ne montrerait
jamais que la photographie du jour : l'historique des indicateurs, qui porte
les courbes de tendance, et l'historique des écarts, qui permet de mesurer
depuis combien de temps un écart traîne sans être résolu.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

import pandas as pd

from config import HISTORY_RETENTION_DAYS, POWERBI_DIR
from security import neutralize_frame

logger = logging.getLogger(__name__)

# Schémas figés. Toute table est écrite avec exactement ces colonnes, dans cet
# ordre, y compris lorsqu'elle ne contient aucune ligne.
BREAKS_COLUMNS = [
    "run_id",
    "run_date",
    "break_key",
    "trade_id",
    "counterparty",
    "product",
    "trade_date",
    "currency",
    "amount_a",
    "amount_b",
    "break_amount",
    "break_type",
    "break_details",
    "suggested_reason",
    "suggested_action",
    "confidence",
    "first_seen_date",
    "days_open",
]

MATCHED_COLUMNS = [
    "run_id",
    "run_date",
    "trade_id",
    "counterparty",
    "product",
    "trade_date",
    "currency",
    "amount",
]

HISTORY_COLUMNS = [
    "run_id",
    "run_date",
    "run_timestamp",
    "total_transactions",
    "matched_count",
    "breaks_count",
    "match_rate",
    "total_break_amount",
    "est_derniere_du_jour",
]

# Historique du détail des écarts. Son grain est la journée : plusieurs
# exécutions le même jour mettent à jour la ligne du jour au lieu de la
# dupliquer, ce qui évite que l'historique n'enfle à chaque essai.
BREAKS_HISTORY_COLUMNS = [
    "run_date",
    "run_id",
    "break_key",
    "trade_id",
    "counterparty",
    "product",
    "trade_date",
    "currency",
    "break_type",
    "break_amount",
    "suggested_reason",
    "confidence",
]

# Colonnes composant l'identité d'un écart d'une journée sur l'autre.
BREAK_KEY_PARTS = ["trade_id", "counterparty", "product", "trade_date", "currency", "break_type"]

# Référentiel des natures d'écart. Il porte le libellé lisible, l'équipe à
# solliciter et un ordre d'affichage, afin que les visuels ne classent pas les
# natures par ordre alphabétique.
BREAK_TYPES = [
    {
        "break_type": "amount",
        "libelle": "Écart de montant",
        "equipe": "Middle office",
        "ordre": 1,
    },
    {
        "break_type": "amount_invalid",
        "libelle": "Montant inexploitable",
        "equipe": "Support des données",
        "ordre": 2,
    },
    {
        "break_type": "missing_B",
        "libelle": "Absente du Système B",
        "equipe": "Back office",
        "ordre": 3,
    },
    {
        "break_type": "missing_A",
        "libelle": "Absente du Système A",
        "equipe": "Front office",
        "ordre": 4,
    },
]

MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

# Un encodage portant la marque d'ordre des octets évite que Power BI et Excel
# n'interprètent les accents en page de code locale.
ENCODING = "utf-8-sig"


def _write(df: pd.DataFrame, columns: list, path: Path) -> None:
    """
    Écrit une table en garantissant son schéma.

    Les colonnes absentes sont créées vides et les colonnes surnuméraires sont
    écartées, de sorte que le fichier produit présente toujours la même
    structure quel que soit le contenu des données.

    Args:
        df: Données à écrire.
        columns: Schéma attendu, dans l'ordre d'écriture.
        path: Chemin du fichier de destination.
    """
    frame = df.copy() if not df.empty else pd.DataFrame(columns=columns)

    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA

    # Ces fichiers sont destinés à Power BI mais restent ouvrables d'un
    # double-clic dans un tableur, qui interpréterait alors les valeurs
    # commençant par un caractère de formule.
    neutralize_frame(frame[columns]).to_csv(path, index=False, encoding=ENCODING)


def _read_existing(path: Path, columns: list, label: str) -> pd.DataFrame:
    """
    Relit un historique existant, en tolérant son absence ou sa corruption.

    Un historique devenu illisible est reconstruit à neuf avec un
    avertissement. Perdre la profondeur historique est regrettable, mais ne pas
    produire le rapport du jour le serait davantage.

    Args:
        path: Chemin de l'historique.
        columns: Schéma attendu.
        label: Libellé employé dans l'avertissement.

    Returns:
        L'historique existant, ou une table vide au bon schéma.
    """
    if not path.exists():
        return pd.DataFrame(columns=columns)

    try:
        return pd.read_csv(path, encoding=ENCODING)
    except Exception as exc:
        logger.warning(f"{label} illisible ({exc}), reconstruction à neuf")
        return pd.DataFrame(columns=columns)


def _purge(df: pd.DataFrame, date_column: str, label: str) -> pd.DataFrame:
    """
    Retire les lignes plus anciennes que la durée de conservation.

    Args:
        df: Historique à purger.
        date_column: Colonne portant la date de référence.
        label: Libellé employé dans le message de journal.

    Returns:
        L'historique purgé.
    """
    if HISTORY_RETENTION_DAYS <= 0 or df.empty or date_column not in df.columns:
        return df

    limite = (datetime.now() - timedelta(days=HISTORY_RETENTION_DAYS)).strftime("%Y-%m-%d")
    conserve = df[df[date_column].astype(str) >= limite]

    retirees = len(df) - len(conserve)
    if retirees:
        logger.info(f"{label} : {retirees} ligne(s) purgée(s), antérieure(s) au {limite}")

    return conserve


def _build_dim_date(dates: pd.Series) -> pd.DataFrame:
    """
    Construit la table de dates couvrant la période observée.

    La table est continue : elle comprend tous les jours entre la première et
    la dernière date rencontrée, y compris ceux sans transaction. Sans cette
    continuité, une courbe de tendance masquerait les journées creuses au lieu
    de les afficher à zéro.

    Args:
        dates: Dates rencontrées dans les données, sous forme de texte.

    Returns:
        La table de dates, avec ses attributs de calendrier en français.
    """
    parsed = pd.to_datetime(dates, errors="coerce").dropna()

    if parsed.empty:
        parsed = pd.Series([pd.Timestamp(datetime.now().date())])

    calendrier = pd.date_range(parsed.min().normalize(), parsed.max().normalize(), freq="D")

    return pd.DataFrame({
        "date": calendrier.strftime("%Y-%m-%d"),
        "annee": calendrier.year,
        "mois": calendrier.month,
        "nom_mois": [MOIS[m - 1] for m in calendrier.month],
        "jour": calendrier.day,
        "semaine": calendrier.isocalendar().week.astype(int),
        "nom_jour": [JOURS[d] for d in calendrier.dayofweek],
        "est_jour_ouvre": [int(d < 5) for d in calendrier.dayofweek],
    })


def _build_break_key(df: pd.DataFrame) -> pd.Series:
    """
    Construit l'identité d'un écart, stable d'une journée sur l'autre.

    Le montant en est volontairement exclu : un écart dont le montant évolue
    légèrement reste le même écart tant que la transaction et la nature de la
    divergence ne changent pas.

    Args:
        df: Écarts à identifier.

    Returns:
        La clé d'identité de chaque écart.
    """
    if df.empty:
        return pd.Series(dtype=str)

    # Le séparateur est échappé dans chaque composant. Sans cette précaution,
    # une contrepartie nommée « A|B » associée au produit « C » produirait la
    # même clé que la contrepartie « A » associée au produit « B|C », et les
    # deux écarts partageraient à tort leur ancienneté.
    parts = [
        df[column].astype(str).str.strip().str.replace("|", "\\|", regex=False)
        for column in BREAK_KEY_PARTS
    ]
    return pd.Series(["|".join(values) for values in zip(*parts)], index=df.index)


def _append_kpi_history(row: dict, path: Path) -> pd.DataFrame:
    """
    Ajoute l'exécution courante à l'historique des indicateurs.

    Chaque exécution est conservée, y compris plusieurs le même jour. La
    colonne `est_derniere_du_jour` permet au rapport de ne retenir qu'un point
    par journée pour les courbes de tendance, sans perdre la trace des rejeux.

    Args:
        row: Indicateurs de l'exécution courante.
        path: Chemin de l'historique.

    Returns:
        L'historique complet après ajout.
    """
    history = _read_existing(path, HISTORY_COLUMNS, "Historique des indicateurs")

    # Un identifiant d'exécution est unique à la seconde près. S'il figure déjà
    # dans l'historique, il s'agit d'une réécriture et non d'une exécution
    # supplémentaire.
    if not history.empty and "run_id" in history.columns:
        history = history[history["run_id"].astype(str) != row["run_id"]]

    history = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
    history = _purge(history, "run_date", "Historique des indicateurs")
    history = history.sort_values(["run_date", "run_timestamp"]).reset_index(drop=True)

    # Marque la dernière exécution de chaque journée.
    derniere = history.groupby("run_date")["run_timestamp"].transform("max")
    history["est_derniere_du_jour"] = (history["run_timestamp"] == derniere).astype(int)

    return history


def _append_breaks_history(breaks: pd.DataFrame, run_id: str, run_date: str, path: Path) -> pd.DataFrame:
    """
    Ajoute les écarts du jour à leur historique.

    Le grain est la journée : une exécution relancée le même jour remplace les
    lignes du jour au lieu de les dupliquer. Sans cette règle, dix essais
    successifs feraient croire à dix journées d'ancienneté.

    Args:
        breaks: Écarts de l'exécution courante, munis de leur clé d'identité.
        run_id: Identifiant de l'exécution.
        run_date: Journée de l'exécution.
        path: Chemin de l'historique.

    Returns:
        L'historique complet après ajout.
    """
    history = _read_existing(path, BREAKS_HISTORY_COLUMNS, "Historique des écarts")

    if not history.empty and "run_date" in history.columns:
        history = history[history["run_date"].astype(str) != run_date]

    if not breaks.empty:
        du_jour = breaks.copy()
        du_jour["run_id"] = run_id
        du_jour["run_date"] = run_date
        for column in BREAKS_HISTORY_COLUMNS:
            if column not in du_jour.columns:
                du_jour[column] = pd.NA
        history = pd.concat([history, du_jour[BREAKS_HISTORY_COLUMNS]], ignore_index=True)

    history = _purge(history, "run_date", "Historique des écarts")
    return history.sort_values(["run_date", "break_key"]).reset_index(drop=True)


def _compute_aging(breaks: pd.DataFrame, history: pd.DataFrame, run_date: str) -> pd.DataFrame:
    """
    Détermine depuis quand chaque écart est ouvert.

    Un écart présent depuis dix jours appelle une action bien plus urgente
    qu'un écart apparu le matin même. C'est cette information, absente de la
    photographie du jour, que l'historique rend disponible.

    Args:
        breaks: Écarts de l'exécution courante.
        history: Historique des écarts, exécution courante comprise.
        run_date: Journée de l'exécution.

    Returns:
        Les écarts complétés de leur date de première détection et de leur
        ancienneté en jours.
    """
    breaks = breaks.copy()

    if breaks.empty:
        return breaks

    if history.empty or "break_key" not in history.columns:
        breaks["first_seen_date"] = run_date
        breaks["days_open"] = 0
        return breaks

    premiere = history.groupby("break_key")["run_date"].min()
    breaks["first_seen_date"] = breaks["break_key"].map(premiere).fillna(run_date)

    courant = pd.Timestamp(run_date)
    origine = pd.to_datetime(breaks["first_seen_date"], errors="coerce")
    breaks["days_open"] = (courant - origine).dt.days.fillna(0).astype(int)

    return breaks


def export_for_powerbi(
    kpis: Dict[str, pd.DataFrame],
    matched_df: pd.DataFrame,
    breaks_df: pd.DataFrame,
    output_dir: Path = POWERBI_DIR,
) -> Dict[str, str]:
    """
    Produit le jeu de tables consommé par le rapport Power BI.

    Sept fichiers sont écrits à chaque exécution. Cinq sont remplacés, deux
    sont des historiques qui s'enrichissent.

    Args:
        kpis: Tableaux d'indicateurs renvoyés par le calculateur.
        matched_df: Transactions rapprochées.
        breaks_df: Écarts qualifiés.
        output_dir: Répertoire de destination des tables.

    Returns:
        Un dictionnaire associant à chaque table le chemin du fichier écrit.
    """
    logger.info("Export des tables Power BI")

    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    run_id = now.strftime("%Y%m%d_%H%M%S")
    run_date = now.strftime("%Y-%m-%d")

    paths = {
        "fact_breaks": output_dir / "fact_breaks.csv",
        "fact_matched": output_dir / "fact_matched.csv",
        "fact_breaks_history": output_dir / "fact_breaks_history.csv",
        "kpi_history": output_dir / "kpi_history.csv",
        "dim_break_type": output_dir / "dim_break_type.csv",
        "dim_date": output_dir / "dim_date.csv",
    }

    # Écarts de l'exécution courante
    breaks_export = breaks_df.copy()
    if not breaks_export.empty:
        amount_a = pd.to_numeric(breaks_export["amount_a"], errors="coerce").fillna(0)
        amount_b = pd.to_numeric(breaks_export["amount_b"], errors="coerce").fillna(0)
        breaks_export["break_amount"] = (amount_a - amount_b).abs().round(2)
        breaks_export["break_key"] = _build_break_key(breaks_export)
        breaks_export["run_id"] = run_id
        breaks_export["run_date"] = run_date

    # Historique des écarts, puis calcul de l'ancienneté à partir de celui-ci
    breaks_history = _append_breaks_history(
        breaks_export, run_id, run_date, paths["fact_breaks_history"]
    )
    breaks_export = _compute_aging(breaks_export, breaks_history, run_date)

    # Transactions rapprochées. Le rapprochement produit des colonnes
    # suffixées, le montant retenu est celui du Système A.
    matched_export = matched_df.copy()
    if not matched_export.empty and "amount" not in matched_export.columns:
        matched_export["amount"] = matched_export.get("amount_a")
    if not matched_export.empty:
        matched_export["run_id"] = run_id
        matched_export["run_date"] = run_date

    # Historique des indicateurs
    summary = kpis.get("kpi_summary")
    indicators = summary.iloc[0] if summary is not None and not summary.empty else {}
    kpi_history = _append_kpi_history(
        {
            "run_id": run_id,
            "run_date": run_date,
            "run_timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "total_transactions": int(indicators.get("total_transactions", 0)),
            "matched_count": int(indicators.get("matched_count", 0)),
            "breaks_count": int(indicators.get("breaks_count", 0)),
            "match_rate": float(indicators.get("match_rate", 0.0)),
            "total_break_amount": float(indicators.get("total_break_amount", 0.0)),
            "est_derniere_du_jour": 1,
        },
        paths["kpi_history"],
    )

    _write(breaks_export, BREAKS_COLUMNS, paths["fact_breaks"])
    _write(matched_export, MATCHED_COLUMNS, paths["fact_matched"])
    _write(breaks_history, BREAKS_HISTORY_COLUMNS, paths["fact_breaks_history"])
    _write(kpi_history, HISTORY_COLUMNS, paths["kpi_history"])

    pd.DataFrame(BREAK_TYPES).to_csv(paths["dim_break_type"], index=False, encoding=ENCODING)

    # La table de dates doit couvrir les dates de négociation de l'exécution
    # courante mais aussi toutes les dates déjà historisées, sans quoi les
    # points de tendance les plus anciens sortiraient de la plage et perdraient
    # leur lien avec le calendrier.
    observed_dates = pd.concat([
        breaks_export.get("trade_date", pd.Series(dtype=str)),
        matched_export.get("trade_date", pd.Series(dtype=str)),
        breaks_history.get("run_date", pd.Series(dtype=str)).astype(str),
        kpi_history["run_date"].astype(str),
    ], ignore_index=True)

    _build_dim_date(observed_dates).to_csv(paths["dim_date"], index=False, encoding=ENCODING)

    journees = kpi_history["run_date"].nunique() if not kpi_history.empty else 0
    logger.info(
        f"Tables Power BI exportées dans {output_dir} "
        f"({len(kpi_history)} exécution(s) sur {journees} journée(s) dans l'historique)"
    )

    return {name: str(path) for name, path in paths.items()}

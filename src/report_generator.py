"""
Génération des livrables.

Trois fichiers sont produits à chaque exécution : le classeur Excel détaillé,
la synthèse texte destinée au reporting managérial, et le relevé des erreurs
rencontrées pendant le traitement.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

from config import ERRORS_SUMMARY_FILE, OUTPUT_DIR, OUTPUT_EXCEL_FILE, OUTPUT_SUMMARY_FILE
from security import neutralize_frame

logger = logging.getLogger(__name__)

# Feuilles du classeur Excel, dans l'ordre d'apparition.
EXCEL_SHEETS = [
    ("kpi_summary", "Synthese_KPI"),
    ("breaks_by_type", "Ecarts_par_nature"),
    ("breaks_by_reason", "Ecarts_par_motif"),
    ("breaks_by_counterparty", "Ecarts_par_contrepartie"),
    ("breaks_by_product", "Ecarts_par_produit"),
]

# Largeur maximale appliquée aux colonnes pour éviter les colonnes démesurées.
MAX_COLUMN_WIDTH = 60


def _autosize_columns(worksheet, df: pd.DataFrame) -> None:
    """
    Ajuste la largeur des colonnes au contenu le plus long.

    Args:
        worksheet: Feuille openpyxl à mettre en forme.
        df: Données écrites dans cette feuille.
    """
    for position, column in enumerate(df.columns, start=1):
        longest = max(
            [len(str(column))] + [len(str(value)) for value in df[column].head(200)]
        )
        letter = worksheet.cell(row=1, column=position).column_letter
        worksheet.column_dimensions[letter].width = min(longest + 2, MAX_COLUMN_WIDTH)


def ecrire_classeur(feuilles: List[tuple], chemin: Path) -> str:
    """
    Écrit un classeur Excel à partir d'une liste de feuilles nommées.

    Le contenu est assaini avant écriture et la largeur des colonnes ajustée.
    Cette fonction est le point de passage unique vers Excel : toute autre
    restitution du projet doit l'emprunter plutôt que d'appeler directement la
    bibliothèque, faute de quoi elle perdrait ces deux protections.

    Args:
        feuilles: Couples (nom de feuille, contenu).
        chemin: Chemin du classeur à produire.

    Returns:
        Le chemin du classeur généré.
    """
    if not feuilles:
        # Un classeur sans aucune feuille visible est rejeté par Excel.
        feuilles = [("Synthese", pd.DataFrame([{"message": "Aucune donnée à restituer"}]))]

    with pd.ExcelWriter(chemin, engine="openpyxl") as writer:
        for nom, frame in feuilles:
            # Les libellés proviennent des fichiers d'entrée. Une valeur
            # commençant par un signe égal serait écrite comme formule et non
            # comme texte, et s'exécuterait à l'ouverture du classeur.
            frame = neutralize_frame(frame)
            frame.to_excel(writer, sheet_name=nom, index=False)
            _autosize_columns(writer.sheets[nom], frame)

    logger.info(f"Classeur généré : {chemin}")
    return str(chemin)


def generate_excel_report(
    kpis: Dict[str, pd.DataFrame],
    breaks_df: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
) -> str:
    """
    Produit le classeur Excel de restitution.

    Args:
        kpis: Tableaux d'indicateurs renvoyés par le calculateur.
        breaks_df: Écarts classifiés.
        output_dir: Répertoire de destination.

    Returns:
        Le chemin du classeur généré.
    """
    logger.info("Génération du rapport Excel")

    output_path = output_dir / OUTPUT_EXCEL_FILE
    sheets: List[tuple] = []

    for key, sheet_name in EXCEL_SHEETS:
        frame = kpis.get(key)
        if frame is not None and not frame.empty:
            sheets.append((sheet_name, frame))

    if not breaks_df.empty:
        # Le détail des écarts est inséré juste après la synthèse.
        sheets.insert(1, ("Detail_ecarts", breaks_df))

    return ecrire_classeur(sheets, output_path)


def _top_lines(frame: pd.DataFrame, label_column: str, title: str, unit: str) -> List[str]:
    """
    Met en forme les trois premières lignes d'une répartition d'écarts.

    Args:
        frame: Tableau de répartition trié par nombre décroissant.
        label_column: Colonne portant le libellé à afficher.
        title: Titre de la section.
        unit: Mot placé après le nombre, par exemple « écart ».

    Returns:
        Les lignes de texte de la section, ou une liste vide si le tableau
        ne contient rien.
    """
    if frame is None or frame.empty or label_column not in frame.columns:
        return []

    lines = [title, "-" * 40]
    for _, row in frame.head(3).iterrows():
        lines.append(f"  - {row[label_column]} : {row['count']} {unit}")
    lines.append("")
    return lines


def generate_text_summary(
    kpis: Dict[str, pd.DataFrame],
    output_dir: Path = OUTPUT_DIR,
) -> str:
    """
    Produit la synthèse texte destinée à un envoi par courriel.

    Args:
        kpis: Tableaux d'indicateurs renvoyés par le calculateur.
        output_dir: Répertoire de destination.

    Returns:
        Le chemin du fichier de synthèse généré.
    """
    logger.info("Génération de la synthèse texte")

    output_path = output_dir / OUTPUT_SUMMARY_FILE
    summary = kpis.get("kpi_summary")

    if summary is not None and not summary.empty:
        indicators = summary.iloc[0]
    else:
        indicators = pd.Series({
            "total_transactions": 0,
            "matched_count": 0,
            "breaks_count": 0,
            "match_rate": 100.0,
            "total_break_amount": 0.0,
        })

    lines = [
        "=" * 60,
        "RECONCILIATION DES TRANSACTIONS ET REPORTING KPI",
        "SYNTHESE D'EXECUTION",
        "=" * 60,
        "",
        f"Date d'exécution : {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}",
        "",
        "INDICATEURS CLES",
        "-" * 40,
        f"Transactions traitées      : {indicators['total_transactions']}",
        f"Transactions rapprochées   : {indicators['matched_count']}",
        f"Écarts détectés            : {indicators['breaks_count']}",
        f"Taux de rapprochement      : {indicators['match_rate']:.2f} %",
        f"Exposition des écarts      : {indicators['total_break_amount']:,.2f}",
        "",
    ]

    lines += _top_lines(
        kpis.get("breaks_by_reason"), "suggested_reason", "PRINCIPAUX MOTIFS D'ECART", "écart(s)"
    )
    lines += _top_lines(
        kpis.get("breaks_by_counterparty"),
        "counterparty",
        "CONTREPARTIES LES PLUS EXPOSEES",
        "écart(s)",
    )
    lines += _top_lines(
        kpis.get("breaks_by_product"), "product", "PRODUITS LES PLUS EXPOSES", "écart(s)"
    )

    lines += [
        "=" * 60,
        "Rapport généré automatiquement par la chaîne de réconciliation",
        "=" * 60,
    ]

    # La marque d'ordre des octets permet aux outils Windows, dont la console
    # et le Bloc-notes, d'afficher correctement les accents sans réglage.
    with open(output_path, "w", encoding="utf-8-sig") as handle:
        handle.write("\n".join(lines))

    logger.info(f"Synthèse texte générée : {output_path}")
    return str(output_path)


def generate_errors_summary(errors: List[Dict], output_dir: Path = OUTPUT_DIR) -> str:
    """
    Produit le relevé des erreurs rencontrées pendant le traitement.

    Le fichier est écrit même lorsque aucune erreur n'est survenue : sa
    présence systématique permet aux outils de supervision de s'appuyer
    dessus sans traiter le cas du fichier absent.

    Args:
        errors: Erreurs collectées pendant l'exécution.
        output_dir: Répertoire de destination.

    Returns:
        Le chemin du relevé généré.
    """
    output_path = output_dir / ERRORS_SUMMARY_FILE
    columns = ["timestamp", "error_type", "message"]

    errors_df = pd.DataFrame(errors) if errors else pd.DataFrame(columns=columns)

    # Les messages d'erreur reprennent souvent une valeur du fichier d'entrée.
    # Ce relevé étant ouvert dans un tableur, il est assaini comme les autres.
    errors_df = neutralize_frame(errors_df)
    errors_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    if errors:
        logger.info(f"Relevé d'erreurs généré ({len(errors)} entrée(s)) : {output_path}")
    else:
        logger.info(f"Relevé d'erreurs vide généré : {output_path}")

    return str(output_path)

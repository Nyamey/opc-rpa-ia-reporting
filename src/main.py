"""
Point d'entrée de la chaîne de réconciliation et de reporting KPI.

Le script enchaîne le chargement des fichiers, le rapprochement, la
classification des écarts, le calcul des indicateurs et la production des
livrables.

Utilisation :
    python src/main.py --input-dir data/input --output-dir data/output
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Le répertoire src doit être dans le chemin d'import pour que les modules
# se référencent entre eux sans préfixe de paquet.
sys.path.insert(0, str(Path(__file__).parent))

from config import INPUT_DIR, LOG_FORMAT, LOG_LEVEL, LOGS_DIR, OUTPUT_DIR, POWERBI_DIR
from kpi_calculator import compute_kpis
from llm_classifier import classify_breaks
from powerbi_export import export_for_powerbi
from reconciliation_engine import load_and_validate_files, reconcile
from report_generator import generate_errors_summary, generate_excel_report, generate_text_summary


def setup_logging(logs_dir: Path = LOGS_DIR, log_level: str = LOG_LEVEL) -> logging.Logger:
    """
    Met en place la journalisation vers un fichier horodaté et vers la console.

    Args:
        logs_dir: Répertoire où déposer les fichiers de journal.
        log_level: Niveau de journalisation, par exemple INFO ou DEBUG.

    Returns:
        Le journal du module principal.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"run_{timestamp}.log"

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(LOG_FORMAT))

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Les gestionnaires existants sont retirés pour qu'un second appel dans le
    # même processus, en test par exemple, ne duplique pas chaque message.
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.addHandler(console)
    root.addHandler(file_handler)

    logger = logging.getLogger(__name__)
    logger.info(f"Journalisation démarrée, fichier : {log_file}")

    return logger


def parse_arguments() -> argparse.Namespace:
    """
    Lit les arguments de la ligne de commande.

    Returns:
        Les arguments analysés.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Réconciliation automatisée des transactions et production des "
            "indicateurs de pilotage pour les opérations bancaires."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default=str(INPUT_DIR),
        help=f"Répertoire des fichiers d'entrée (par défaut : {INPUT_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(OUTPUT_DIR),
        help=f"Répertoire des livrables (par défaut : {OUTPUT_DIR})",
    )
    parser.add_argument(
        "--powerbi-dir",
        type=str,
        default=str(POWERBI_DIR),
        help=f"Répertoire des tables Power BI (par défaut : {POWERBI_DIR})",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Niveau de journalisation (par défaut : {LOG_LEVEL})",
    )

    return parser.parse_args()


def run(input_dir: Path, output_dir: Path, powerbi_dir: Path, logger: logging.Logger) -> None:
    """
    Déroule les six étapes du traitement.

    Args:
        input_dir: Répertoire des fichiers d'entrée.
        output_dir: Répertoire des livrables destinés à la lecture humaine.
        powerbi_dir: Répertoire des tables consommées par Power BI.
        logger: Journal à utiliser.
    """
    logger.info("Étape 1 sur 6 : chargement et validation des fichiers d'entrée")
    df_a, df_b = load_and_validate_files(input_dir)

    logger.info("Étape 2 sur 6 : rapprochement des transactions")
    matched_df, breaks_raw_df = reconcile(df_a, df_b)

    logger.info("Étape 3 sur 6 : classification des écarts")
    breaks_classified_df = classify_breaks(breaks_raw_df)

    logger.info("Étape 4 sur 6 : calcul des indicateurs")
    kpis = compute_kpis(matched_df, breaks_classified_df)

    logger.info("Étape 5 sur 6 : génération des livrables")
    excel_path = generate_excel_report(kpis, breaks_classified_df, output_dir)
    summary_path = generate_text_summary(kpis, output_dir)
    errors_path = generate_errors_summary([], output_dir)

    logger.info("Étape 6 sur 6 : export des tables Power BI")
    powerbi_paths = export_for_powerbi(kpis, matched_df, breaks_classified_df, powerbi_dir)

    logger.info(f"Rapport Excel : {excel_path}")
    logger.info(f"Synthèse texte : {summary_path}")
    logger.info(f"Relevé d'erreurs : {errors_path}")
    logger.info(f"Tables Power BI : {powerbi_dir} ({len(powerbi_paths)} tables)")


def main() -> None:
    """
    Orchestre l'exécution complète et gère les erreurs de haut niveau.

    Toute erreur interrompt le traitement, est consignée dans le relevé
    d'erreurs et provoque une sortie en code 1, afin qu'un ordonnanceur
    détecte l'échec sans avoir à analyser les journaux.
    """
    args = parse_arguments()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    powerbi_dir = Path(args.powerbi_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    powerbi_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(log_level=args.log_level)

    logger.info("=" * 60)
    logger.info("Réconciliation des transactions et reporting KPI")
    logger.info("=" * 60)

    errors: List[Dict] = []

    try:
        run(input_dir, output_dir, powerbi_dir, logger)
    except (FileNotFoundError, ValueError) as exc:
        # Erreurs attendues : fichier absent, fichier vide, colonne manquante.
        # Le message est suffisamment explicite pour être restitué tel quel.
        logger.error(f"Traitement interrompu : {exc}")
        errors.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_type": type(exc).__name__,
            "message": str(exc),
        })
        generate_errors_summary(errors, output_dir)
        sys.exit(1)
    except Exception as exc:
        logger.error(f"Erreur inattendue : {exc}", exc_info=True)
        errors.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_type": type(exc).__name__,
            "message": str(exc),
        })
        generate_errors_summary(errors, output_dir)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info(f"Traitement terminé avec succès. Livrables déposés dans {output_dir}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

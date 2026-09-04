"""
Point d'entrée de la grille de sélection des processus.

Ce traitement est distinct de la chaîne de réconciliation quotidienne. Il
s'exécute en amont d'un projet, lors du cadrage du portefeuille, et non tous
les matins.

Utilisation :
    python src/evaluer_processus.py --input-dir data/input --output-dir data/output
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    EVALUATION_EXCEL_FILE,
    INPUT_DIR,
    LOG_FORMAT,
    LOG_LEVEL,
    OUTPUT_DIR,
    POWERBI_DIR,
    SEUIL_FAISABILITE,
    SEUIL_VALEUR,
)
from process_assessment import charger_candidats, construire_restitution, evaluer
from report_generator import ecrire_classeur
from security import neutralize_frame

logger = logging.getLogger(__name__)

# Feuilles du classeur d'évaluation, dans l'ordre d'apparition.
FEUILLES = [
    ("classement", "Classement"),
    ("synthese_orientation", "Synthese_orientation"),
    ("synthese_secteur", "Synthese_secteur"),
    ("detail_notation", "Detail_notation"),
]


def configurer_journalisation(log_level: str) -> None:
    """
    Met en place la journalisation vers la console.

    Args:
        log_level: Niveau de journalisation.
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=LOG_FORMAT,
        stream=sys.stdout,
        force=True,
    )


def lire_arguments() -> argparse.Namespace:
    """
    Lit les arguments de la ligne de commande.

    Returns:
        Les arguments analysés.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Évalue les processus candidats à l'automatisation et propose une "
            "orientation pour chacun."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default=str(INPUT_DIR),
        help=f"Répertoire du référentiel des candidats (par défaut : {INPUT_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(OUTPUT_DIR),
        help=f"Répertoire du classeur d'évaluation (par défaut : {OUTPUT_DIR})",
    )
    parser.add_argument(
        "--powerbi-dir",
        type=str,
        default=str(POWERBI_DIR),
        help=f"Répertoire de la table Power BI (par défaut : {POWERBI_DIR})",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Niveau de journalisation (par défaut : {LOG_LEVEL})",
    )

    return parser.parse_args()


def afficher_synthese(evaluation) -> None:
    """
    Restitue en console les éléments d'arbitrage.

    Args:
        evaluation: Référentiel évalué.
    """
    retenus = evaluation[evaluation["orientation"].isin(
        ["Automatiser en RPA", "Projet hybride RPA et IA"]
    )]

    logger.info("=" * 70)
    logger.info(
        f"Portefeuille évalué : {len(evaluation)} processus, "
        f"{evaluation['charge_etp'].sum():.1f} ETP de charge manuelle totale"
    )
    logger.info(
        f"Processus retenus : {len(retenus)}, "
        f"{retenus['charge_etp'].sum():.1f} ETP de charge adressable"
    )
    logger.info(f"Seuils appliqués : valeur {SEUIL_VALEUR}, faisabilité {SEUIL_FAISABILITE}")
    logger.info("=" * 70)

    for _, ligne in evaluation.head(5).iterrows():
        logger.info(
            f"  {ligne['rang']:>2}. {ligne['process_id']:<12} "
            f"{ligne['charge_etp']:>5.2f} ETP  "
            f"V{ligne['score_valeur']:>5.1f} F{ligne['score_faisabilite']:>5.1f}  "
            f"{ligne['orientation']}"
        )


def main() -> None:
    """
    Déroule l'évaluation et produit les restitutions.
    """
    args = lire_arguments()
    configurer_journalisation(args.log_level)

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    powerbi_dir = Path(args.powerbi_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    powerbi_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Grille de sélection des processus candidats")

    try:
        candidats = charger_candidats(input_dir)
        evaluation = evaluer(candidats)
    except (FileNotFoundError, ValueError) as exc:
        logger.error(f"Évaluation interrompue : {exc}")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"Erreur inattendue : {exc}", exc_info=True)
        sys.exit(1)

    restitution = construire_restitution(evaluation)

    chemin_excel = ecrire_classeur(
        [(nom, restitution[cle]) for cle, nom in FEUILLES if not restitution[cle].empty],
        output_dir / EVALUATION_EXCEL_FILE,
    )

    # Table destinée au rapport Power BI. Le référentiel évalué est remplacé à
    # chaque cadrage : contrairement aux écarts, il n'a pas d'historique à
    # conserver puisqu'il décrit un état du portefeuille à un instant donné.
    chemin_table = powerbi_dir / "dim_processus.csv"
    evaluation["date_evaluation"] = datetime.now().strftime("%Y-%m-%d")
    neutralize_frame(evaluation).to_csv(chemin_table, index=False, encoding="utf-8-sig")

    afficher_synthese(evaluation)

    logger.info(f"Classeur d'évaluation : {chemin_excel}")
    logger.info(f"Table Power BI : {chemin_table}")


if __name__ == "__main__":
    main()

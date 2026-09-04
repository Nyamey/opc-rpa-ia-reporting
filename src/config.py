"""
Configuration centrale du projet de réconciliation et de reporting KPI.

Toutes les valeurs modifiables du traitement sont regroupées ici : chemins,
noms de fichiers, clés de rapprochement, tolérance sur les montants et
paramètres d'appel au modèle de langage.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Répertoires de base
BASE_DIR = Path(__file__).parent.parent
INPUT_DIR = BASE_DIR / "data" / "input"
OUTPUT_DIR = BASE_DIR / "data" / "output"
LOGS_DIR = BASE_DIR / "logs"

# Tables consommées par le rapport Power BI. Elles sont séparées des livrables
# destinés à la lecture humaine, car leur schéma doit rester constant.
POWERBI_DIR = BASE_DIR / "data" / "powerbi"

# Charge le fichier .env s'il existe, afin que les identifiants du modèle de
# langage puissent être fournis sans être écrits en dur dans le code.
load_dotenv(BASE_DIR / ".env")

# Création des répertoires au chargement du module
for directory in [INPUT_DIR, OUTPUT_DIR, LOGS_DIR, POWERBI_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Noms de fichiers
SYSTEM_A_FILE = "transactions_systemA.csv"
SYSTEM_B_FILE = "transactions_systemB.csv"
OUTPUT_EXCEL_FILE = "kpi_report.xlsx"
OUTPUT_SUMMARY_FILE = "summary.txt"
ERRORS_SUMMARY_FILE = "errors_summary.csv"

# Colonnes obligatoires dans les deux fichiers d'entrée
REQUIRED_COLUMNS = [
    "trade_id",
    "counterparty",
    "product",
    "trade_date",
    "amount",
    "currency",
]

# Paramètres de réconciliation
# Deux lignes sont considérées comme la même transaction si toutes ces
# colonnes sont identiques. Le montant est comparé à part, avec tolérance.
MATCH_KEYS = ["trade_id", "counterparty", "product", "trade_date", "currency"]
AMOUNT_TOLERANCE = 0.01

# Paramètres du modèle de langage (facultatif)
LLM_API_URL = os.getenv("LLM_API_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))

# Le modèle n'est sollicité que si une URL a été configurée. Sinon le
# traitement bascule sur la classification par règles.
USE_LLM = bool(LLM_API_URL)

# ---------------------------------------------------------------------------
# Grille de sélection des processus candidats à l'automatisation
# ---------------------------------------------------------------------------

CANDIDATS_FILE = "processus_candidats.csv"
EVALUATION_EXCEL_FILE = "evaluation_processus.xlsx"

# Nombre d'heures travaillées par an et par équivalent temps plein. Sert à
# convertir une charge en minutes en charge exprimée en ETP.
HEURES_ANNUELLES_ETP = 1600

# Pondération de l'axe valeur. La charge pèse le plus lourd : c'est elle qui
# détermine le gain, les autres critères ne font que moduler la priorité.
POIDS_VALEUR = {
    "charge": 0.55,
    "criticite": 0.25,
    "taux_erreur": 0.20,
}

# Pondération de l'axe faisabilité. Le taux de règles domine : un processus
# qui repose sur le jugement humain ne s'automatise pas, quelle que soit la
# qualité des autres critères.
POIDS_FAISABILITE = {
    "taux_regles": 0.40,
    "stabilite": 0.25,
    "structuration": 0.20,
    "applications": 0.15,
}

# Note de faisabilité attribuée selon la structuration des données d'entrée.
# Une donnée non structurée n'interdit pas l'automatisation mais impose une
# brique de reconnaissance, donc un projet hybride plutôt qu'un robot seul.
NOTES_STRUCTURATION = {
    "structuré": 100,
    "semi-structuré": 60,
    "non structuré": 20,
}

# Seuils de passage sur chacun des deux axes, sur cent.
SEUIL_VALEUR = 50
SEUIL_FAISABILITE = 60

# Taux de règles en deçà duquel une automatisation directe est exclue, quelle
# que soit la qualité des autres critères. Un processus dont une part
# importante repose sur le jugement humain doit d'abord être simplifié :
# l'automatiser en l'état reviendrait à figer le désordre existant.
SEUIL_TAUX_REGLES = 60

# Taux de règles minimal pour qu'un projet hybride garde un sens. En deçà, la
# reconnaissance documentaire ne suffirait pas et le traitement resterait
# manuel dans les faits.
SEUIL_TAUX_REGLES_HYBRIDE = 40

# En deçà de ce volume de charge, l'automatisation ne se justifie pas même si
# le processus est techniquement simple : le coût de construction et de
# maintenance du robot dépasserait le gain.
SEUIL_ETP_MINIMAL = 0.5

# Durée de conservation des historiques décisionnels, en jours.
# Une valeur nulle ou négative désactive la purge et conserve tout.
HISTORY_RETENTION_DAYS = int(os.getenv("HISTORY_RETENTION_DAYS", "730"))

# Paramètres de journalisation
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

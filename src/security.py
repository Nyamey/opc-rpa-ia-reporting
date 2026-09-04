"""
Défenses appliquées aux données non fiables.

Les fichiers d'entrée proviennent de systèmes tiers et leur contenu se
retrouve dans des livrables ouverts par des analystes. Ce module regroupe les
protections qui empêchent une donnée hostile de devenir du code exécutable ou
de faire fuiter un secret.
"""

import logging
import re
from typing import Any
from urllib.parse import urlparse

import pandas as pd
from pandas.api import types as ptypes

logger = logging.getLogger(__name__)

# Caractères qui, en tête de cellule, font qu'un tableur interprète le contenu
# comme une formule au lieu d'un texte.
FORMULA_PREFIXES = ("=", "+", "-", "@")

# Caractères de contrôle qui permettent de décaler le début réel d'une cellule
# et de contourner un contrôle qui ne regarderait que le premier caractère.
CONTROL_PREFIXES = ("\t", "\r", "\n")

# Préfixe de neutralisation. L'apostrophe force le mode texte et reste visible,
# ce qui signale à l'analyste que la valeur reçue était anormale.
TEXT_MARKER = "'"

# Longueur au-delà de laquelle une valeur textuelle est tronquée. Une cellule
# démesurée ne présente pas de risque d'exécution mais sature les livrables.
MAX_CELL_LENGTH = 2000

# Motifs masqués avant journalisation d'un message d'erreur réseau.
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)=([^&\s'\"]+)"),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{8,})"),
]


def neutralize_cell(value: Any) -> Any:
    """
    Rend une valeur inoffensive pour un tableur.

    Une chaîne commençant par un caractère de formule est préfixée d'une
    apostrophe, ce qui la fait interpréter comme du texte. Sans cette
    protection, une contrepartie nommée `=cmd|'/c calc'!A0` devient une
    formule exécutable dans le classeur produit.

    Args:
        value: Valeur issue des données d'entrée.

    Returns:
        La valeur neutralisée si elle était dangereuse, sinon telle quelle.
    """
    if not isinstance(value, str) or not value:
        return value

    if len(value) > MAX_CELL_LENGTH:
        value = value[:MAX_CELL_LENGTH] + "… [tronqué]"

    if value[0] in FORMULA_PREFIXES or value[0] in CONTROL_PREFIXES:
        return TEXT_MARKER + value

    return value


def neutralize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applique la neutralisation à toutes les colonnes textuelles d'un tableau.

    Les colonnes numériques et de dates sont laissées intactes : elles ne
    peuvent pas porter de formule, et les convertir en texte dégraderait les
    livrables.

    Args:
        df: Tableau à assainir.

    Returns:
        Une copie assainie du tableau.
    """
    if df.empty:
        return df

    safe = df.copy()

    for column in safe.columns:
        # Le test porte sur ce qu'une colonne ne peut pas contenir plutôt que
        # sur le type des chaînes. Selon la version de pandas, une colonne de
        # texte se présente comme « object » ou comme « str », et se fier à
        # l'un des deux rendrait la protection silencieusement inopérante.
        dtype = safe[column].dtype
        if (
            ptypes.is_numeric_dtype(dtype)
            or ptypes.is_datetime64_any_dtype(dtype)
            or ptypes.is_bool_dtype(dtype)
        ):
            continue

        safe[column] = safe[column].map(neutralize_cell)

    return safe


def redact(text: Any) -> str:
    """
    Masque les identifiants susceptibles d'apparaître dans un message d'erreur.

    Les bibliothèques réseau reprennent volontiers l'adresse appelée dans leurs
    exceptions. Si un jeton figure dans cette adresse ou dans un en-tête cité,
    il se retrouverait en clair dans les journaux, qui sont conservés et
    souvent transmis au support.

    Args:
        text: Message à assainir.

    Returns:
        Le message avec les secrets remplacés par un marqueur.
    """
    result = str(text)
    for pattern in SECRET_PATTERNS:
        result = pattern.sub(r"\1[masqué]", result)
    return result


def validate_llm_url(url: str) -> None:
    """
    Vérifie qu'une adresse de modèle de langage est utilisable sans risque.

    Une adresse en clair ferait circuler le jeton d'authentification en clair
    sur le réseau. L'exception est faite pour les adresses locales, employées
    lors des essais.

    Args:
        url: Adresse configurée.

    Raises:
        ValueError: L'adresse est mal formée ou non chiffrée.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Adresse du modèle de langage invalide : le schéma « {parsed.scheme} » "
            f"n'est pas accepté, utilisez https."
        )

    if not parsed.hostname:
        raise ValueError("Adresse du modèle de langage invalide : hôte absent.")

    est_local = parsed.hostname in ("localhost", "127.0.0.1", "::1")

    if parsed.scheme == "http" and not est_local:
        raise ValueError(
            "Adresse du modèle de langage refusée : une adresse en http ferait "
            "circuler le jeton d'authentification en clair. Utilisez https."
        )


def quote_untrusted(value: Any, maximum: int = 200) -> str:
    """
    Prépare une donnée non fiable avant insertion dans une consigne au modèle.

    Les retours à la ligne et les délimiteurs sont retirés afin qu'une valeur
    hostile ne puisse pas se faire passer pour une nouvelle instruction dans la
    consigne. La longueur est bornée pour la même raison.

    Args:
        value: Donnée issue des fichiers d'entrée.
        maximum: Longueur maximale conservée.

    Returns:
        La donnée sous une forme utilisable dans une consigne.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "non renseigné"

    text = str(value).replace("\r", " ").replace("\n", " ").replace("`", "'")
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > maximum:
        text = text[:maximum] + "…"

    return text or "non renseigné"

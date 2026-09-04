"""
Lecture tolérante des fichiers CSV.

Les fichiers reçus ne sont pas toujours produits par la chaîne d'extraction
prévue. Un tableur français exporte en point-virgule et dans la page de code
Windows, un système anglo-saxon en virgule et en UTF-8, et un fichier passé par
plusieurs mains peut porter une marque d'ordre des octets.

Refuser ces variantes obligerait l'utilisateur à convertir son fichier avant
tout traitement. Ce module les reconnaît à la place, et ne rend une erreur que
lorsque le contenu est réellement inexploitable.
"""

import csv
import logging
from pathlib import Path
from typing import List

import pandas as pd

logger = logging.getLogger(__name__)

# Encodages tentés dans l'ordre. L'UTF-8 avec marque d'ordre des octets passe
# en premier car il se reconnaît sans ambiguïté ; la page de code Windows vient
# ensuite car c'est ce que produit un tableur français.
ENCODAGES = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]

# Séparateurs reconnus.
SEPARATEURS = [",", ";", "\t", "|"]


def _detecter_encodage(chemin: Path) -> str:
    """
    Détermine l'encodage d'un fichier en tentant les variantes courantes.

    Args:
        chemin: Fichier à examiner.

    Returns:
        Le premier encodage qui décode le fichier sans erreur.

    Raises:
        ValueError: Aucun encodage connu ne convient.
    """
    brut = chemin.read_bytes()

    for encodage in ENCODAGES:
        try:
            brut.decode(encodage)
        except (UnicodeDecodeError, LookupError):
            continue
        return encodage

    raise ValueError(
        f"L'encodage du fichier {chemin.name} n'est pas reconnu. "
        f"Enregistrez-le en UTF-8 avant de le déposer."
    )


def _detecter_separateur(entete: str) -> str:
    """
    Détermine le séparateur de colonnes à partir de la ligne d'en-tête.

    L'analyseur de la bibliothèque standard est consulté en premier. S'il
    échoue, le séparateur le plus fréquent dans l'en-tête est retenu, ce qui
    couvre les cas où l'en-tête ne comporte qu'une poignée de colonnes.

    Args:
        entete: Première ligne du fichier.

    Returns:
        Le séparateur retenu.
    """
    try:
        dialecte = csv.Sniffer().sniff(entete, delimiters="".join(SEPARATEURS))
        if dialecte.delimiter in SEPARATEURS:
            return dialecte.delimiter
    except csv.Error:
        pass

    occurrences = {sep: entete.count(sep) for sep in SEPARATEURS}
    meilleur = max(occurrences, key=occurrences.get)

    # Aucun séparateur présent : le fichier n'a qu'une colonne, la virgule
    # convient alors aussi bien qu'un autre choix.
    return meilleur if occurrences[meilleur] > 0 else ","


def lire_csv(chemin: Path, libelle: str, colonnes_requises: List[str]) -> pd.DataFrame:
    """
    Lit un fichier CSV et vérifie qu'il contient les colonnes attendues.

    Args:
        chemin: Fichier à lire.
        libelle: Désignation employée dans les messages d'erreur.
        colonnes_requises: Colonnes obligatoires.

    Returns:
        Le contenu du fichier.

    Raises:
        FileNotFoundError: Le fichier n'existe pas.
        ValueError: Le fichier est vide, illisible ou incomplet.
    """
    if not chemin.exists():
        logger.error(f"Fichier introuvable : {chemin}")
        raise FileNotFoundError(f"Fichier introuvable : {chemin}")

    if chemin.stat().st_size == 0:
        logger.error(f"Fichier vide : {chemin}")
        raise ValueError(
            f"Le fichier {libelle} est vide : {chemin.name}. Il doit contenir au "
            f"minimum une ligne d'en-tête avec les colonnes "
            f"{', '.join(colonnes_requises)}."
        )

    encodage = _detecter_encodage(chemin)

    with open(chemin, "r", encoding=encodage) as handle:
        entete = handle.readline()

    if not entete.strip():
        raise ValueError(
            f"Le fichier {libelle} ne comporte pas de ligne d'en-tête exploitable : "
            f"{chemin.name}."
        )

    separateur = _detecter_separateur(entete)

    try:
        df = pd.read_csv(chemin, encoding=encodage, sep=separateur)
    except pd.errors.EmptyDataError as exc:
        raise ValueError(
            f"Le fichier {libelle} ne contient aucune colonne exploitable : {chemin.name}."
        ) from exc
    except pd.errors.ParserError as exc:
        # Message volontairement réécrit : celui de la bibliothèque cite des
        # numéros de champs incompréhensibles pour un exploitant.
        raise ValueError(
            f"Le fichier {libelle} est mal formé : toutes les lignes n'ont pas le "
            f"même nombre de colonnes. Vérifiez les valeurs contenant le "
            f"séparateur « {separateur} », qui doivent être entre guillemets."
        ) from exc

    # Les en-têtes sont épurés : un espace résiduel en fin de nom de colonne est
    # invisible à l'œil et provoquerait un diagnostic incompréhensible.
    df.columns = [str(col).strip() for col in df.columns]

    manquantes = [col for col in colonnes_requises if col not in df.columns]
    if manquantes:
        logger.error(f"Colonnes manquantes dans le fichier {libelle} : {manquantes}")
        raise ValueError(
            f"Colonnes obligatoires manquantes dans le fichier {libelle} : "
            f"{', '.join(manquantes)}. Colonnes trouvées : {', '.join(df.columns)}."
        )

    if separateur != "," or encodage != "utf-8":
        logger.info(
            f"{libelle} : séparateur « {separateur} » et encodage {encodage} détectés"
        )

    logger.info(f"{libelle} chargé : {len(df)} ligne(s)")
    return df

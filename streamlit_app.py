"""
Vue interactive du projet d'automatisation des opérations bancaires.

L'application ne réimplémente aucune règle métier : elle appelle les mêmes
modules que les traitements en ligne de commande. Une divergence entre ce que
montre l'écran et ce que produit le traitement quotidien est donc impossible
par construction.

Lancement :
    streamlit run streamlit_app.py
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import (
    CANDIDATS_FILE,
    INPUT_DIR,
    OUTPUT_SUMMARY_FILE,
    POWERBI_DIR,
    SEUIL_FAISABILITE,
    SEUIL_VALEUR,
    SYSTEM_A_FILE,
    SYSTEM_B_FILE,
)
from kpi_calculator import compute_kpis
from llm_classifier import classify_breaks
from process_assessment import (
    COLONNES_REQUISES,
    charger_candidats,
    construire_restitution,
    evaluer,
)
from reconciliation_engine import load_and_validate_files, reconcile
from report_generator import ecrire_classeur, generate_excel_report, generate_text_summary

# ---------------------------------------------------------------------------
# Palette
#
# Les trois teintes de série sont les trois premiers emplacements de la palette
# de référence, seuls à valider la séparation sur l'ensemble des paires, ce
# qu'exige un nuage de points. C'est la raison pour laquelle les six
# orientations sont regroupées en trois familles de décision : inventer six
# couleurs produirait des paires indistinguables pour une partie des lecteurs.
# ---------------------------------------------------------------------------

SURFACE = "#fcfcfb"
ENCRE = "#0b0b0b"
ENCRE_SECONDAIRE = "#52514e"
ENCRE_ATTENUEE = "#898781"
GRILLE = "#e1e0d9"
AXE = "#c3c2b7"

SERIE_1 = "#2a78d6"
SERIE_2 = "#eb6834"
SERIE_3 = "#1baf7a"

POLICE = "system-ui, -apple-system, Segoe UI, sans-serif"

# Regroupement des orientations en familles de décision.
FAMILLES = {
    "Automatiser en RPA": "Retenu pour automatisation",
    "Projet hybride RPA et IA": "Retenu pour automatisation",
    "Intégration applicative": "À retravailler ou réorienter",
    "Optimiser avant d'automatiser": "À retravailler ou réorienter",
    "Backlog opportuniste": "Non retenu",
    "Écarter": "Non retenu",
}

COULEURS_FAMILLE = {
    "Retenu pour automatisation": SERIE_1,
    "À retravailler ou réorienter": SERIE_2,
    "Non retenu": SERIE_3,
}

ORIENTATIONS_RETENUES = ["Automatiser en RPA", "Projet hybride RPA et IA"]


def mise_en_forme(figure: go.Figure, hauteur: int = 420) -> go.Figure:
    """
    Applique l'habillage commun à toutes les figures.

    Grille et axes restent en retrait pour que les marques de données portent
    le regard.

    Args:
        figure: Figure à habiller.
        hauteur: Hauteur en pixels.

    Returns:
        La figure habillée.
    """
    figure.update_layout(
        height=hauteur,
        margin=dict(l=10, r=10, t=50, b=10),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=POLICE, size=13, color=ENCRE_SECONDAIRE),
        title=dict(font=dict(size=15, color=ENCRE), x=0, xanchor="left"),
        hoverlabel=dict(font=dict(family=POLICE, size=12), bgcolor=SURFACE),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            title=None,
            font=dict(size=12),
        ),
    )
    figure.update_xaxes(
        showgrid=True, gridcolor=GRILLE, gridwidth=1,
        zeroline=False, linecolor=AXE, tickfont=dict(color=ENCRE_ATTENUEE),
    )
    figure.update_yaxes(
        showgrid=True, gridcolor=GRILLE, gridwidth=1,
        zeroline=False, linecolor=AXE, tickfont=dict(color=ENCRE_ATTENUEE),
    )
    return figure


# ---------------------------------------------------------------------------
# Dépôt de fichiers
#
# Les fichiers déposés sont écrits dans un répertoire temporaire propre à la
# session, jamais dans `data/input`. Deux raisons à cela : le jeu de
# démonstration du dépôt ne doit pas être écrasé, et une exécution issue d'un
# essai ne doit pas s'inscrire dans l'historique qui porte les courbes de
# tendance du projet.
# ---------------------------------------------------------------------------

TAILLE_MAX_MO = 50


def _valider_depot(fichier, libelle: str) -> bytes:
    """
    Contrôle un fichier déposé avant tout traitement.

    Args:
        fichier: Fichier remis par le composant de dépôt.
        libelle: Désignation employée dans les messages.

    Returns:
        Le contenu du fichier, ou None s'il est refusé.
    """
    if fichier is None:
        return None

    if not fichier.name.lower().endswith(".csv"):
        st.error(f"{libelle} : seuls les fichiers CSV sont acceptés.")
        return None

    contenu = fichier.getvalue()

    if len(contenu) > TAILLE_MAX_MO * 1024 * 1024:
        st.error(f"{libelle} : le fichier dépasse {TAILLE_MAX_MO} Mo.")
        return None

    if not contenu.strip():
        st.error(f"{libelle} : le fichier est vide.")
        return None

    return contenu


def _ecrire_depot(fichiers: dict) -> Path:
    """
    Dépose les contenus reçus dans un répertoire temporaire isolé.

    Args:
        fichiers: Association entre nom de fichier attendu et contenu.

    Returns:
        Le répertoire contenant les fichiers écrits.
    """
    dossier = Path(tempfile.mkdtemp(prefix="opc-depot-"))
    for nom, contenu in fichiers.items():
        (dossier / nom).write_bytes(contenu)
    return dossier


def _modele(chemin: Path, lignes: int = 3) -> bytes:
    """
    Construit un modèle de fichier à partir du jeu de démonstration.

    Fournir un modèle évite à l'utilisateur d'avoir à deviner les noms de
    colonnes attendus, qui sont nombreux pour le référentiel des candidats.

    Args:
        chemin: Fichier de référence.
        lignes: Nombre de lignes d'exemple conservées.

    Returns:
        Le modèle encodé, prêt au téléchargement.
    """
    try:
        apercu = pd.read_csv(chemin, encoding="utf-8-sig").head(lignes)
    except Exception:
        return b""
    return apercu.to_csv(index=False).encode("utf-8-sig")


# ---------------------------------------------------------------------------
# Chargement des données
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Évaluation du portefeuille en cours")
def charger_evaluation(depot: bytes = None) -> pd.DataFrame:
    """
    Évalue le portefeuille de processus candidats.

    Args:
        depot: Référentiel déposé par l'utilisateur, ou None pour employer le
            jeu de démonstration du dépôt.

    Returns:
        Le référentiel évalué.
    """
    dossier = INPUT_DIR if depot is None else _ecrire_depot({CANDIDATS_FILE: depot})

    evaluation = evaluer(charger_candidats(dossier))
    evaluation["famille"] = evaluation["orientation"].map(FAMILLES)
    return evaluation


@st.cache_data(show_spinner="Rapprochement en cours")
def charger_reconciliation(depot_a: bytes = None, depot_b: bytes = None) -> tuple:
    """
    Exécute le rapprochement et le calcul des indicateurs.

    Args:
        depot_a: Transactions du Système A déposées, ou None.
        depot_b: Transactions du Système B déposées, ou None.

    Returns:
        Le quadruplet (rapprochées, écarts qualifiés, indicateurs, répertoire).
    """
    if depot_a is None or depot_b is None:
        dossier = INPUT_DIR
    else:
        dossier = _ecrire_depot({SYSTEM_A_FILE: depot_a, SYSTEM_B_FILE: depot_b})

    df_a, df_b = load_and_validate_files(dossier)
    matched, breaks_bruts = reconcile(df_a, df_b)
    breaks = classify_breaks(breaks_bruts)
    return matched, breaks, compute_kpis(matched, breaks), dossier


@st.cache_data(show_spinner=False)
def produire_livrables_reconciliation(_kpis: dict, _breaks: pd.DataFrame, cle: str) -> dict:
    """
    Génère le classeur et la synthèse dans un répertoire temporaire.

    Args:
        _kpis: Indicateurs calculés.
        _breaks: Écarts qualifiés.
        cle: Empreinte du jeu de données, qui sert de clé de cache.

    Returns:
        Association entre nom de livrable et contenu binaire.
    """
    dossier = Path(tempfile.mkdtemp(prefix="opc-livrables-"))

    chemin_excel = Path(generate_excel_report(_kpis, _breaks, dossier))
    chemin_synthese = Path(generate_text_summary(_kpis, dossier))

    return {
        "kpi_report.xlsx": chemin_excel.read_bytes(),
        OUTPUT_SUMMARY_FILE: chemin_synthese.read_bytes(),
    }


@st.cache_data(show_spinner=False)
def produire_livrable_evaluation(_evaluation: pd.DataFrame, cle: str) -> bytes:
    """
    Génère le classeur d'évaluation du portefeuille.

    Args:
        _evaluation: Référentiel évalué.
        cle: Empreinte du jeu de données, qui sert de clé de cache.

    Returns:
        Le classeur, prêt au téléchargement.
    """
    dossier = Path(tempfile.mkdtemp(prefix="opc-evaluation-"))
    restitution = construire_restitution(_evaluation)

    feuilles = [
        ("Classement", restitution["classement"]),
        ("Synthese_orientation", restitution["synthese_orientation"]),
        ("Synthese_secteur", restitution["synthese_secteur"]),
        ("Detail_notation", restitution["detail_notation"]),
    ]

    chemin = Path(ecrire_classeur(feuilles, dossier / "evaluation_processus.xlsx"))
    return chemin.read_bytes()


@st.cache_data(show_spinner=False)
def charger_table(nom: str) -> pd.DataFrame:
    """
    Relit une table décisionnelle si elle a déjà été produite.

    Args:
        nom: Nom du fichier dans le répertoire Power BI.

    Returns:
        La table, ou un tableau vide si elle n'existe pas encore.
    """
    chemin = POWERBI_DIR / nom
    if not chemin.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(chemin, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Volet 1 : sélection des processus
# ---------------------------------------------------------------------------

def matrice_valeur_faisabilite(evaluation: pd.DataFrame) -> go.Figure:
    """
    Trace la matrice des candidats sur les deux axes de notation.

    Les seuils sont matérialisés, ce qui rend les quadrants lisibles sans
    coloriage de fond : un lecteur situe immédiatement un processus par rapport
    à la règle plutôt que par rapport aux autres points.

    Args:
        evaluation: Référentiel évalué.

    Returns:
        La figure.
    """
    figure = go.Figure()

    for famille, couleur in COULEURS_FAMILLE.items():
        sous_ensemble = evaluation[evaluation["famille"] == famille]
        if sous_ensemble.empty:
            continue

        figure.add_trace(go.Scatter(
            x=sous_ensemble["score_faisabilite"],
            y=sous_ensemble["score_valeur"],
            mode="markers",
            name=famille,
            marker=dict(
                size=sous_ensemble["charge_etp"],
                sizemode="area",
                # La référence de taille est calée sur la charge maximale du
                # portefeuille, avec un plancher pour que les petits processus
                # restent cliquables.
                sizeref=2.0 * evaluation["charge_etp"].max() / (34.0 ** 2),
                sizemin=8,
                color=couleur,
                line=dict(width=2, color=SURFACE),
                opacity=0.9,
            ),
            customdata=sous_ensemble[
                ["process_id", "nom", "secteur", "charge_etp", "orientation"]
            ].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b> %{customdata[1]}<br>"
                "Secteur %{customdata[2]}<br>"
                "Charge %{customdata[3]:.2f} ETP<br>"
                "Valeur %{y:.1f} sur 100<br>"
                "Faisabilité %{x:.1f} sur 100<br>"
                "<b>%{customdata[4]}</b>"
                "<extra></extra>"
            ),
        ))

    # Labels directs sur les cinq premiers du classement seulement : nommer les
    # vingt points rendrait le graphique illisible.
    tete = evaluation.nsmallest(5, "rang")
    figure.add_trace(go.Scatter(
        x=tete["score_faisabilite"],
        y=tete["score_valeur"],
        mode="text",
        text=tete["process_id"],
        textposition="top center",
        textfont=dict(size=11, color=ENCRE_SECONDAIRE, family=POLICE),
        showlegend=False,
        hoverinfo="skip",
    ))

    figure.add_vline(x=SEUIL_FAISABILITE, line=dict(color=AXE, width=1, dash="dot"))
    figure.add_hline(y=SEUIL_VALEUR, line=dict(color=AXE, width=1, dash="dot"))

    figure.add_annotation(
        x=SEUIL_FAISABILITE, y=101, yanchor="bottom", showarrow=False,
        text=f"seuil de faisabilité {SEUIL_FAISABILITE}",
        font=dict(size=11, color=ENCRE_ATTENUEE),
    )
    figure.add_annotation(
        x=101, y=SEUIL_VALEUR, xanchor="left", showarrow=False,
        text=f"seuil de valeur {SEUIL_VALEUR}",
        font=dict(size=11, color=ENCRE_ATTENUEE),
    )

    figure.update_layout(
        title="Matrice de sélection, aire proportionnelle à la charge en ETP",
        xaxis_title="Faisabilité technique",
        yaxis_title="Valeur métier",
    )
    figure.update_xaxes(range=[0, 112])
    figure.update_yaxes(range=[0, 112])

    return mise_en_forme(figure, hauteur=520)


def charge_par_secteur(evaluation: pd.DataFrame) -> go.Figure:
    """
    Compare la charge adressable à la charge totale de chaque secteur.

    Args:
        evaluation: Référentiel évalué.

    Returns:
        La figure.
    """
    travail = evaluation.copy()
    travail["retenue"] = travail["charge_etp"].where(
        travail["orientation"].isin(ORIENTATIONS_RETENUES), 0.0
    )

    synthese = travail.groupby("secteur").agg(
        totale=("charge_etp", "sum"),
        retenue=("retenue", "sum"),
    ).reset_index().sort_values("retenue")

    figure = go.Figure()

    figure.add_trace(go.Bar(
        y=synthese["secteur"], x=synthese["totale"], orientation="h",
        name="Charge recensée", marker=dict(color=GRILLE, cornerradius=4),
        hovertemplate="%{y}<br>Charge recensée %{x:.2f} ETP<extra></extra>",
    ))
    figure.add_trace(go.Bar(
        y=synthese["secteur"], x=synthese["retenue"], orientation="h",
        name="Charge adressable", marker=dict(color=SERIE_1, cornerradius=4),
        hovertemplate="%{y}<br>Charge adressable %{x:.2f} ETP<extra></extra>",
    ))

    figure.update_layout(
        title="Charge manuelle par secteur, en équivalents temps plein",
        barmode="overlay",
        xaxis_title="ETP",
    )
    figure.update_yaxes(showgrid=False)

    return mise_en_forme(figure, hauteur=340)


def afficher_selection() -> None:
    """Compose le volet de sélection des processus."""
    with st.expander("Utiliser votre propre référentiel de processus"):
        st.markdown(
            f"Déposez un fichier CSV comportant les colonnes suivantes : "
            f"`{'`, `'.join(COLONNES_REQUISES)}`.\n\n"
            "Le séparateur et l'encodage sont reconnus automatiquement, un export "
            "de tableur français en point-virgule est donc accepté tel quel."
        )

        modele = _modele(INPUT_DIR / CANDIDATS_FILE)
        if modele:
            st.download_button(
                "Télécharger un modèle",
                data=modele,
                file_name="modele_processus_candidats.csv",
                mime="text/csv",
            )

        depose = st.file_uploader(
            "Référentiel des processus candidats",
            type=["csv"],
            key="depot_candidats",
        )

    contenu = _valider_depot(depose, "Référentiel")

    if depose is not None and contenu is None:
        return

    try:
        evaluation = charger_evaluation(contenu)
    except (FileNotFoundError, ValueError) as exc:
        st.error(f"Référentiel inexploitable : {exc}")
        return
    except Exception as exc:
        st.error(f"Erreur inattendue pendant l'évaluation : {exc}")
        return

    if contenu is not None:
        st.success(f"Référentiel déposé traité : {len(evaluation)} processus évalués.")
    else:
        st.caption(
            "Portefeuille de démonstration du dépôt. Déposez votre propre "
            "référentiel ci-dessus pour évaluer vos processus."
        )

    retenus = evaluation[evaluation["orientation"].isin(ORIENTATIONS_RETENUES)]

    colonnes = st.columns(4)
    colonnes[0].metric("Processus évalués", len(evaluation))
    colonnes[1].metric("Charge recensée", f"{evaluation['charge_etp'].sum():.1f} ETP")
    colonnes[2].metric("Processus retenus", len(retenus))
    colonnes[3].metric("Charge adressable", f"{retenus['charge_etp'].sum():.1f} ETP")

    st.caption(
        "La charge adressable ne retient que les processus orientés vers une "
        "automatisation ou un projet hybride. Elle exclut ceux qui relèvent de "
        "l'intégration applicative ou d'une optimisation préalable."
    )

    secteurs = st.multiselect(
        "Filtrer par secteur",
        options=sorted(evaluation["secteur"].unique()),
        default=sorted(evaluation["secteur"].unique()),
    )
    filtre = evaluation[evaluation["secteur"].isin(secteurs)]

    if filtre.empty:
        st.warning("Aucun processus ne correspond au filtre.")
        return

    st.plotly_chart(matrice_valeur_faisabilite(filtre), use_container_width=True)
    st.plotly_chart(charge_par_secteur(filtre), use_container_width=True)

    st.subheader("Classement arbitré")

    classeur = produire_livrable_evaluation(
        evaluation, cle=f"{len(evaluation)}-{evaluation['charge_etp'].sum():.4f}"
    )
    st.download_button(
        "Télécharger le classeur d'évaluation",
        data=classeur,
        file_name="evaluation_processus.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.caption(
        "Le détail sert aux échanges avec les responsables de secteur : lorsqu'une "
        "orientation est contestée, la discussion doit porter sur les données "
        "recueillies et non sur la note finale."
    )
    st.dataframe(
        filtre[[
            "rang", "process_id", "nom", "secteur", "charge_etp",
            "score_valeur", "score_faisabilite", "orientation", "justification",
        ]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "rang": st.column_config.NumberColumn("Rang", width="small"),
            "process_id": st.column_config.TextColumn("Identifiant"),
            "nom": st.column_config.TextColumn("Processus", width="medium"),
            "secteur": st.column_config.TextColumn("Secteur", width="small"),
            "charge_etp": st.column_config.NumberColumn("Charge ETP", format="%.2f"),
            "score_valeur": st.column_config.ProgressColumn(
                "Valeur", min_value=0, max_value=100, format="%.1f"
            ),
            "score_faisabilite": st.column_config.ProgressColumn(
                "Faisabilité", min_value=0, max_value=100, format="%.1f"
            ),
            "orientation": st.column_config.TextColumn("Orientation"),
            "justification": st.column_config.TextColumn("Justification", width="large"),
        },
    )


# ---------------------------------------------------------------------------
# Volet 2 : réconciliation
# ---------------------------------------------------------------------------

def ecarts_par_nature(breaks: pd.DataFrame) -> go.Figure:
    """
    Compare le nombre d'écarts et l'exposition portée par chaque nature.

    Args:
        breaks: Écarts qualifiés.

    Returns:
        La figure.
    """
    travail = breaks.copy()
    amount_a = pd.to_numeric(travail["amount_a"], errors="coerce").fillna(0)
    amount_b = pd.to_numeric(travail["amount_b"], errors="coerce").fillna(0)
    travail["exposition"] = (amount_a - amount_b).abs()

    synthese = travail.groupby("break_type").agg(
        nombre=("trade_id", "count"),
        exposition=("exposition", "sum"),
    ).reset_index().sort_values("exposition")

    figure = go.Figure(go.Bar(
        y=synthese["break_type"], x=synthese["exposition"], orientation="h",
        marker=dict(color=SERIE_1, cornerradius=4),
        customdata=synthese["nombre"],
        hovertemplate=(
            "%{y}<br>Exposition %{x:,.0f}<br>"
            "%{customdata} écart(s)<extra></extra>"
        ),
    ))

    figure.update_layout(
        title="Exposition financière par nature d'écart",
        xaxis_title="Montant cumulé",
    )
    figure.update_yaxes(showgrid=False)

    return mise_en_forme(figure, hauteur=320)


def tendance(historique: pd.DataFrame) -> go.Figure:
    """
    Trace l'évolution du taux de rapprochement.

    Seule la dernière exécution de chaque journée est retenue : additionner
    toutes les exécutions compterait plusieurs fois une même journée relancée.

    Args:
        historique: Historique des indicateurs.

    Returns:
        La figure.
    """
    reference = historique[historique["est_derniere_du_jour"] == 1].sort_values("run_date")

    figure = go.Figure(go.Scatter(
        x=reference["run_date"], y=reference["match_rate"],
        mode="lines+markers",
        line=dict(color=SERIE_1, width=2),
        marker=dict(size=8, color=SERIE_1, line=dict(width=2, color=SURFACE)),
        hovertemplate="%{x}<br>Taux de rapprochement %{y:.2f} %<extra></extra>",
    ))

    figure.update_layout(
        title="Taux de rapprochement par journée traitée",
        yaxis_title="Pourcentage",
    )

    return mise_en_forme(figure, hauteur=320)


def afficher_reconciliation() -> None:
    """Compose le volet de réconciliation."""
    with st.expander("Utiliser vos propres fichiers de transactions"):
        st.markdown(
            "Déposez les deux extractions à rapprocher. Le traitement complet "
            "s'enchaîne automatiquement : contrôle des fichiers, rapprochement, "
            "qualification des écarts, calcul des indicateurs et production des "
            "livrables."
        )

        modele = _modele(INPUT_DIR / SYSTEM_A_FILE)
        if modele:
            st.download_button(
                "Télécharger un modèle",
                data=modele,
                file_name="modele_transactions.csv",
                mime="text/csv",
            )

        colonnes_depot = st.columns(2)
        depose_a = colonnes_depot[0].file_uploader(
            "Transactions du Système A", type=["csv"], key="depot_a"
        )
        depose_b = colonnes_depot[1].file_uploader(
            "Transactions du Système B", type=["csv"], key="depot_b"
        )

    contenu_a = _valider_depot(depose_a, "Système A")
    contenu_b = _valider_depot(depose_b, "Système B")

    depot_partiel = (depose_a is None) != (depose_b is None)
    depot_refuse = (depose_a is not None and contenu_a is None) or (
        depose_b is not None and contenu_b is None
    )

    if depot_refuse:
        return

    if depot_partiel:
        st.warning(
            "Les deux fichiers sont nécessaires au rapprochement. Déposez le "
            "second pour lancer le traitement."
        )
        return

    sur_depot = contenu_a is not None and contenu_b is not None

    try:
        matched, breaks, kpis, _ = charger_reconciliation(contenu_a, contenu_b)
    except (FileNotFoundError, ValueError) as exc:
        st.error(f"Fichiers inexploitables : {exc}")
        return
    except Exception as exc:
        st.error(f"Erreur inattendue pendant le rapprochement : {exc}")
        return

    indicateurs = kpis["kpi_summary"].iloc[0]

    if sur_depot:
        st.success(
            f"Fichiers déposés traités : {len(matched)} transaction(s) rapprochée(s) "
            f"et {len(breaks)} écart(s) détecté(s)."
        )
    else:
        st.caption(
            "Jeu de démonstration du dépôt. Déposez vos propres extractions "
            "ci-dessus pour rapprocher vos transactions."
        )

    colonnes = st.columns(4)
    colonnes[0].metric("Transactions traitées", int(indicateurs["total_transactions"]))
    colonnes[1].metric("Rapprochées", int(indicateurs["matched_count"]))
    colonnes[2].metric("Taux de rapprochement", f"{indicateurs['match_rate']:.2f} %")
    colonnes[3].metric("Exposition", f"{indicateurs['total_break_amount']:,.0f}")

    # Les livrables sont produits pour tout jeu de données, y compris déposé.
    livrables = produire_livrables_reconciliation(
        kpis, breaks,
        cle=f"{len(matched)}-{len(breaks)}-{indicateurs['total_break_amount']:.4f}",
    )

    colonnes_telechargement = st.columns(2)
    colonnes_telechargement[0].download_button(
        "Télécharger le rapport Excel",
        data=livrables["kpi_report.xlsx"],
        file_name="kpi_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    colonnes_telechargement[1].download_button(
        "Télécharger la synthèse",
        data=livrables[OUTPUT_SUMMARY_FILE],
        file_name=OUTPUT_SUMMARY_FILE,
        mime="text/plain",
        use_container_width=True,
    )

    if breaks.empty:
        st.success("Aucun écart détecté sur cette exécution.")
        return

    st.plotly_chart(ecarts_par_nature(breaks), use_container_width=True)

    # La tendance et l'ancienneté proviennent des historiques du dépôt, qui
    # décrivent le jeu de démonstration. Les rapprocher d'un fichier déposé
    # afficherait des chiffres sans rapport avec les données à l'écran.
    if not sur_depot:
        historique = charger_table("kpi_history.csv")
        if not historique.empty and "est_derniere_du_jour" in historique.columns:
            journees = historique[historique["est_derniere_du_jour"] == 1]
            if len(journees) > 1:
                st.plotly_chart(tendance(historique), use_container_width=True)
            else:
                st.info(
                    "La courbe de tendance apparaîtra à partir de la deuxième journée "
                    "traitée. L'historique ne compte pour l'instant qu'une seule journée."
                )

    st.subheader("Détail des écarts")

    detail = pd.DataFrame() if sur_depot else charger_table("fact_breaks.csv")

    if not detail.empty and "days_open" in detail.columns:
        colonnes_detail = [
            "trade_id", "counterparty", "product", "trade_date", "currency",
            "amount_a", "amount_b", "break_amount", "break_type",
            "days_open", "suggested_reason", "suggested_action",
        ]
        detail = detail[[c for c in colonnes_detail if c in detail.columns]]
        st.caption(
            "L'ancienneté provient de l'historique des écarts. Un écart ouvert "
            "depuis plusieurs jours appelle un traitement différent d'un écart "
            "apparu le matin même."
        )
    else:
        detail = breaks
        if sur_depot:
            st.caption(
                "L'ancienneté des écarts et la courbe de tendance ne sont pas "
                "affichées pour un fichier déposé : elles se construisent au fil "
                "des exécutions quotidiennes, à partir de l'historique alimenté "
                "par `python src/main.py`."
            )
        else:
            st.caption(
                "L'ancienneté des écarts nécessite d'avoir exécuté `python src/main.py` "
                "au moins une fois, afin que l'historique existe."
            )

    st.dataframe(detail, hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def main() -> None:
    """Compose l'application."""
    st.set_page_config(
        page_title="Automatisation des opérations bancaires",
        page_icon="🏦",
        layout="wide",
    )

    st.title("Automatisation des opérations bancaires")
    st.markdown(
        "Cette vue reprend les deux moments d'un programme d'automatisation : "
        "**sélectionner** les processus qui méritent d'être automatisés, puis "
        "**industrialiser** celui qui a été retenu. Les calculs sont ceux des "
        "traitements en ligne de commande, appelés directement."
    )

    volet_selection, volet_reconciliation = st.tabs([
        "Sélection des processus",
        "Réconciliation quotidienne",
    ])

    with volet_selection:
        afficher_selection()

    with volet_reconciliation:
        afficher_reconciliation()

    with st.sidebar:
        st.header("À propos")
        st.markdown(
            "**Volet 1** note vingt processus candidats des secteurs CMO, GRM, "
            "FTO et TBS sur deux axes, puis les oriente.\n\n"
            "**Volet 2** rapproche les transactions du front office et du back "
            "office, qualifie les écarts et calcule les indicateurs."
        )
        st.divider()
        st.caption(
            "Les données sont synthétiques et ne proviennent d'aucun client ni "
            "d'aucun établissement réel."
        )
        if st.button("Recalculer", use_container_width=True):
            st.cache_data.clear()
            st.rerun()


if __name__ == "__main__":
    main()

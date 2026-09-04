// ============================================================================
// Requêtes Power Query du rapport de réconciliation
//
// Mode d'emploi
//   1. Dans Power BI Desktop, ouvrir Accueil puis Transformer les données.
//   2. Créer d'abord le paramètre DossierDonnees décrit ci-dessous.
//   3. Pour chaque bloc suivant, créer une requête vide, ouvrir l'Éditeur
//      avancé, remplacer son contenu par le bloc, et nommer la requête comme
//      indiqué dans son titre.
//
// Les nombres sont typés avec la culture en-US parce que les fichiers portent
// un point décimal. Sans cette précision, une session Power BI en français
// interpréterait 1250000.00 comme un entier de douze chiffres.
//
// L'encodage 65001 correspond à l'UTF-8 et rend les accents correctement.
// ============================================================================


// ----------------------------------------------------------------------------
// PARAMÈTRE : DossierDonnees
//
// À créer via Gérer les paramètres plutôt que par l'Éditeur avancé.
//   Nom             : DossierDonnees
//   Type            : Texte
//   Valeur actuelle : le chemin complet du dossier data\powerbi
//                     par exemple C:\Users\vous\opc-rpa-ia-reconciliation\data\powerbi
//
// Ce paramètre est le seul point à modifier lors d'un déplacement du projet.
// ----------------------------------------------------------------------------


// ----------------------------------------------------------------------------
// REQUÊTE : fact_breaks
// Une ligne par écart détecté. Table de faits principale.
// ----------------------------------------------------------------------------
let
    Source = Csv.Document(
        File.Contents(DossierDonnees & "\fact_breaks.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(
        Entetes,
        {
            {"run_id", type text},
            {"run_date", type date},
            {"break_key", type text},
            {"trade_id", type text},
            {"counterparty", type text},
            {"product", type text},
            {"trade_date", type date},
            {"currency", type text},
            {"amount_a", type number},
            {"amount_b", type number},
            {"break_amount", type number},
            {"break_type", type text},
            {"break_details", type text},
            {"suggested_reason", type text},
            {"suggested_action", type text},
            {"confidence", type number},
            {"first_seen_date", type date},
            {"days_open", Int64.Type}
        },
        "en-US"
    ),
    // Sépare les écarts que le système a su expliquer de ceux qui appellent
    // une revue humaine. Le seuil reprend la règle RG06 du document métier.
    RevueManuelle = Table.AddColumn(
        Types,
        "revue_manuelle",
        each if [confidence] = null or [confidence] < 0.6 then "Oui" else "Non",
        type text
    ),
    // Tranches d'ancienneté, pour un visuel de vieillissement lisible.
    Anciennete = Table.AddColumn(
        RevueManuelle,
        "tranche_anciennete",
        each
            if [days_open] = null then "Inconnue"
            else if [days_open] = 0 then "Du jour"
            else if [days_open] <= 2 then "1 a 2 jours"
            else if [days_open] <= 5 then "3 a 5 jours"
            else if [days_open] <= 10 then "6 a 10 jours"
            else "Plus de 10 jours",
        type text
    )
in
    Anciennete


// ----------------------------------------------------------------------------
// REQUÊTE : fact_matched
// Une ligne par transaction rapprochée sans écart. Sert au calcul des volumes.
// ----------------------------------------------------------------------------
let
    Source = Csv.Document(
        File.Contents(DossierDonnees & "\fact_matched.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(
        Entetes,
        {
            {"run_id", type text},
            {"run_date", type date},
            {"trade_id", type text},
            {"counterparty", type text},
            {"product", type text},
            {"trade_date", type date},
            {"currency", type text},
            {"amount", type number}
        },
        "en-US"
    )
in
    Types


// ----------------------------------------------------------------------------
// REQUÊTE : fact_breaks_history
// Une ligne par écart et par journée où il était encore ouvert. C'est la
// source du suivi de vieillissement et des délais de résolution.
// ----------------------------------------------------------------------------
let
    Source = Csv.Document(
        File.Contents(DossierDonnees & "\fact_breaks_history.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(
        Entetes,
        {
            {"run_date", type date},
            {"run_id", type text},
            {"break_key", type text},
            {"trade_id", type text},
            {"counterparty", type text},
            {"product", type text},
            {"trade_date", type date},
            {"currency", type text},
            {"break_type", type text},
            {"break_amount", type number},
            {"suggested_reason", type text},
            {"confidence", type number}
        },
        "en-US"
    )
in
    Types


// ----------------------------------------------------------------------------
// REQUÊTE : kpi_history
// Une ligne par exécution. Source des courbes de tendance.
//
// Toutes les exécutions sont conservées, y compris plusieurs le même jour.
// Pour tracer un point par journée, filtrez sur est_derniere_du_jour = 1,
// soit dans le visuel, soit via la mesure prévue à cet effet.
// ----------------------------------------------------------------------------
let
    Source = Csv.Document(
        File.Contents(DossierDonnees & "\kpi_history.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(
        Entetes,
        {
            {"run_id", type text},
            {"run_date", type date},
            {"run_timestamp", type datetime},
            {"total_transactions", Int64.Type},
            {"matched_count", Int64.Type},
            {"breaks_count", Int64.Type},
            {"match_rate", type number},
            {"total_break_amount", type number},
            {"est_derniere_du_jour", Int64.Type}
        },
        "en-US"
    ),
    Trie = Table.Sort(Types, {{"run_timestamp", Order.Ascending}})
in
    Trie


// ----------------------------------------------------------------------------
// REQUÊTE : dim_break_type
// Référentiel des natures d'écart : libellé lisible, équipe et ordre de tri.
// ----------------------------------------------------------------------------
let
    Source = Csv.Document(
        File.Contents(DossierDonnees & "\dim_break_type.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(
        Entetes,
        {
            {"break_type", type text},
            {"libelle", type text},
            {"equipe", type text},
            {"ordre", Int64.Type}
        },
        "en-US"
    )
in
    Types


// ----------------------------------------------------------------------------
// REQUÊTE : dim_date
// Calendrier continu couvrant les dates de négociation et les dates
// d'exécution. À marquer comme table de dates après chargement.
// ----------------------------------------------------------------------------
let
    Source = Csv.Document(
        File.Contents(DossierDonnees & "\dim_date.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(
        Entetes,
        {
            {"date", type date},
            {"annee", Int64.Type},
            {"mois", Int64.Type},
            {"nom_mois", type text},
            {"jour", Int64.Type},
            {"semaine", Int64.Type},
            {"nom_jour", type text},
            {"est_jour_ouvre", Int64.Type}
        },
        "en-US"
    ),
    // Clé de tri des mois, sans laquelle les visuels classeraient avril avant
    // janvier. À utiliser via Trier par colonne sur nom_mois.
    Trie = Table.AddColumn(Types, "mois_tri", each [annee] * 100 + [mois], Int64.Type)
in
    Trie

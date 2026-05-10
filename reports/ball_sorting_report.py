import json
import os
import pandas as pd
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
)
from reportlab.lib.units import cm
from datetime import datetime

TOTAL_BALLS_PER_LEVEL = 31

def percent(x):
    return round(x * 100, 1)

def seconds_to_min_sec(seconds):
    minutes = int(seconds // 60)
    sec = int(seconds % 60)
    return f"{minutes} min {sec} s"

def save_bar_chart(labels, values, title, ylabel, filename, color):
    plt.figure(figsize=(8, 5))
    plt.bar(labels, values, color=color)
    plt.title(title, fontsize=14, fontweight="bold")
    plt.ylabel(ylabel)
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close()


def generate_clinical_pdf(json_file, patient_info=None):
    if json_file is None:
        raise ValueError("Veuillez importer un fichier JSON.")

    json_path = json_file.name

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    patient = data.get("patientName", "Inconnu")
    date = data.get("sessionDate", "Inconnue")
    try:
        parsed_date = datetime.strptime(date, "%d/%m/%Y %H:%M:%S")
        formatted_date = parsed_date.strftime("%d/%m/%Y %H:%M:%S")
    except:
        formatted_date = date

    if patient_info is None:
        patient_info = {}
        
    patient_lastname = patient_info.get("lastname", "")
    patient_firstname = patient_info.get("firstname", "")
    patient_birthdate = patient_info.get("birthdate", "")
    try:
        birthdate_obj = datetime.strptime(patient_birthdate, "%Y-%m-%d")
        patient_birthdate = birthdate_obj.strftime("%d-%m-%Y")
    except:
        pass
    therapist_name = patient_info.get("therapist", "")
    
    full_patient_name = f"{patient_firstname} {patient_lastname}".strip()
    
    if full_patient_name == "":
        full_patient_name = patient

    total_correct = data.get("totalCorrect", 0)
    total_errors = data.get("totalErrors", 0)
    total_manipulated = data.get("totalManipulated", 0)
    total_time = data.get("totalTime", 0)
    total_accuracy = percent(data.get("totalAccuracy", 0))

    levels = data.get("levels", [])

    # =========================
    # TABLEAU PAR NIVEAU
    # =========================
    
    level_rows = []
    level_counts = {}

    for lvl in levels:
        level_num = lvl["level"]
        
        if level_num not in level_counts:
            level_counts[level_num] = 1
        else:
            level_counts[level_num] += 1

        attempt = level_counts[level_num]
        label = f"Niveau {level_num} - Essai {attempt}"

        correct = lvl.get("correct", 0)
        errors = lvl.get("errors", 0)
        manipulated = lvl.get("manipulated", 0)
        time = lvl.get("time", 0)
        
        success_rate = percent(correct / TOTAL_BALLS_PER_LEVEL) if TOTAL_BALLS_PER_LEVEL > 0 else 0
        sorting_precision = percent(correct / manipulated) if manipulated > 0 else 0
        completion_rate = percent(manipulated / TOTAL_BALLS_PER_LEVEL) if TOTAL_BALLS_PER_LEVEL > 0 else 0
        
        level_rows.append([
            label,
            correct,
            errors,
            manipulated,
            round(time, 1),
            seconds_to_min_sec(time),
            success_rate,
            sorting_precision,
            completion_rate
        ])
        
    df_levels = pd.DataFrame(
        level_rows,
        columns=[
            "Niveau",
            "Correct",
            "Erreurs",
            "Balles manipulées",
            "Temps (s)",
            "Temps",
            "Taux de réussite global (%)",
            "Précision de tri (%)",
            "Taux de réalisation (%)"
        ]
    )

    # =========================
    # GRAPHES PAR NIVEAU
    # =========================

    level_labels = df_levels["Niveau"].tolist()
    success_rate_values = df_levels["Taux de réussite global (%)"].tolist()
    error_values = df_levels["Erreurs"].tolist()
    time_values = df_levels["Temps (s)"].tolist()

    level_labels_for_stats = df_levels["Niveau"].tolist()

    # =========================
    # STATS PAR COULEUR
    # =========================

    color_rows = []
    
    for i, lvl in enumerate(levels):
        level_number = level_labels_for_stats[i]

        for c in lvl.get("colorStats", []):
            total = c.get("totalBalls", 0)
            correct = c.get("correct", 0)
            errors = c.get("errors", 0)

            accuracy = correct / total if total > 0 else 0

            color_rows.append({
                "Niveau": level_number,
                "Couleur": c.get("color"),
                "Total balles": total,
                "Correct": correct,
                "Erreurs": errors,
                "Accuracy (%)": percent(accuracy)
            })

    df_colors = pd.DataFrame(color_rows)

    # =========================
    # STATS PAR PANIER
    # =========================

    basket_rows = []
    
    for i, lvl in enumerate(levels):
        level_number = level_labels_for_stats[i]

        for b in lvl.get("basketStats", []):
            attempts = b.get("attempts", 0)
            correct = b.get("correct", 0)
            errors = b.get("errors", 0)

            accuracy = correct / attempts if attempts > 0 else 0
            error_rate = errors / attempts if attempts > 0 else 0

            basket_rows.append({
                "Niveau": level_number,
                "Panier": b.get("basketColor"),
                "Distance": b.get("distance"),
                "Hauteur": b.get("height"),
                "Côté": b.get("side"),
                "Tentatives": attempts,
                "Correct": correct,
                "Erreurs": errors,
                "Accuracy (%)": percent(accuracy),
                "Taux erreur (%)": percent(error_rate)
            })

    df_baskets = pd.DataFrame(basket_rows)

    if df_baskets.empty:
        raise ValueError("Le fichier JSON ne contient pas de données basketStats.")

    difficult_baskets = df_baskets[df_baskets["Taux erreur (%)"] >= 30]

    # =========================
    # ANALYSE PAR DISTANCE / HAUTEUR / CÔTÉ
    # =========================

    df_distance = df_baskets.groupby("Distance")[["Tentatives", "Correct", "Erreurs"]].sum().reset_index()
    df_distance["Accuracy (%)"] = round((df_distance["Correct"] / df_distance["Tentatives"]) * 100, 1)

    df_height = df_baskets.groupby("Hauteur")[["Tentatives", "Correct", "Erreurs"]].sum().reset_index()
    df_height["Accuracy (%)"] = round((df_height["Correct"] / df_height["Tentatives"]) * 100, 1)

    df_side = df_baskets.groupby("Côté")[["Tentatives", "Correct", "Erreurs"]].sum().reset_index()
    df_side["Accuracy (%)"] = round((df_side["Correct"] / df_side["Tentatives"]) * 100, 1)

    # =========================
    # ANALYSE CLINIQUE
    # =========================

    clinical_notes = []

    if total_accuracy >= 90:
        clinical_notes.append("Très bonne précision globale dans le tri des couleurs.")
    elif total_accuracy >= 70:
        clinical_notes.append("Précision globale correcte, mais certaines erreurs doivent être analysées.")
    else:
        clinical_notes.append("Précision globale faible : possible difficulté cognitive, attentionnelle ou fatigue.")

    if total_errors > 0:
        clinical_notes.append("Des erreurs de tri ont été observées : vérifier les confusions entre couleurs.")
    else:
        clinical_notes.append("Aucune erreur de tri détectée sur la session.")

    if len(difficult_baskets) > 0:
        clinical_notes.append("Certains paniers présentent un taux d'erreur élevé, ce qui peut indiquer une difficulté motrice ou attentionnelle.")
    else:
        clinical_notes.append("Aucun panier ne présente un taux d'erreur particulièrement élevé.")

    if not df_distance.empty:
        worst_distance = df_distance.sort_values("Accuracy (%)").iloc[0]
        clinical_notes.append(
            f"La distance la plus difficile semble être : {worst_distance['Distance']} "
            f"avec {worst_distance['Accuracy (%)']}% de réussite."
        )

    if not df_height.empty:
        worst_height = df_height.sort_values("Accuracy (%)").iloc[0]
        clinical_notes.append(
            f"La hauteur la plus difficile semble être : {worst_height['Hauteur']} "
            f"avec {worst_height['Accuracy (%)']}% de réussite."
        )

    if not df_side.empty:
        worst_side = df_side.sort_values("Accuracy (%)").iloc[0]
        clinical_notes.append(
            f"Le côté le plus difficile semble être : {worst_side['Côté']} "
            f"avec {worst_side['Accuracy (%)']}% de réussite."
        )

    # =========================
    # ANALYSE MOTRICE TEXTUELLE
    # =========================

    motor_notes = []

    if not df_distance.empty:
        best_distance = df_distance.sort_values("Accuracy (%)", ascending=False).iloc[0]
        worst_distance = df_distance.sort_values("Accuracy (%)").iloc[0]

        motor_notes.append(
            f"Distance la mieux réussie : {best_distance['Distance']} "
            f"avec {best_distance['Accuracy (%)']}% de réussite."
        )

        motor_notes.append(
            f"Distance la plus difficile : {worst_distance['Distance']} "
            f"avec {worst_distance['Accuracy (%)']}% de réussite."
        )

    if not df_height.empty:
        best_height = df_height.sort_values("Accuracy (%)", ascending=False).iloc[0]
        worst_height = df_height.sort_values("Accuracy (%)").iloc[0]

        motor_notes.append(
            f"Hauteur la mieux réussie : {best_height['Hauteur']} "
            f"avec {best_height['Accuracy (%)']}% de réussite."
        )

        motor_notes.append(
            f"Hauteur la plus difficile : {worst_height['Hauteur']} "
            f"avec {worst_height['Accuracy (%)']}% de réussite."
        )

    if not df_side.empty:
        best_side = df_side.sort_values("Accuracy (%)", ascending=False).iloc[0]
        worst_side = df_side.sort_values("Accuracy (%)").iloc[0]

        motor_notes.append(
            f"Côté le mieux réussi : {best_side['Côté']} "
            f"avec {best_side['Accuracy (%)']}% de réussite."
        )

        motor_notes.append(
            f"Côté le plus difficile : {worst_side['Côté']} "
            f"avec {worst_side['Accuracy (%)']}% de réussite."
        )

    # =========================
    # CRÉATION DES GRAPHES
    # =========================

    save_bar_chart(level_labels, success_rate_values, "Taux de réussite global par niveau", "Taux de réussite (%)", "graph_accuracy_niveaux.png", "#4A90E2")
    save_bar_chart(level_labels, error_values, "Erreurs par niveau", "Nombre d'erreurs", "graph_erreurs_niveaux.png", "#E74C3C")
    save_bar_chart(level_labels, time_values, "Temps par niveau", "Temps (s)", "graph_temps_niveaux.png", "#F5A623")

    save_bar_chart(df_distance["Distance"], df_distance["Accuracy (%)"], "Accuracy selon la distance", "Accuracy (%)", "graph_distance.png", "#7ED321")
    save_bar_chart(df_height["Hauteur"], df_height["Accuracy (%)"], "Accuracy selon la hauteur", "Accuracy (%)", "graph_hauteur.png", "#9013FE")
    save_bar_chart(df_side["Côté"], df_side["Accuracy (%)"], "Accuracy selon le côté", "Accuracy (%)", "graph_cote.png", "#50E3C2")

    # =========================
    # CRÉATION PDF
    # =========================

    clean_patient = str(patient).replace(" ", "_").replace("/", "_")
    pdf_name = f"rapport_clinique_{clean_patient}.pdf"

    doc = SimpleDocTemplate(
        pdf_name,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )

    styles = getSampleStyleSheet()
    story = []



    logo_app_path = os.path.join("assets", "Logo-APP.png")
    logo_enp_path = os.path.join("assets", "Logo-ENP.png")

    left_logo = Image(logo_app_path, width=3*cm, height=3*cm) if os.path.exists(logo_app_path) else Paragraph("PhoeniXR", styles["Heading2"])
    right_logo = Image(logo_enp_path, width=3*cm, height=3*cm) if os.path.exists(logo_enp_path) else Paragraph("ENP", styles["Heading2"])

    header_table = Table(
    [[left_logo, "", right_logo]],
    colWidths=[4*cm, 9*cm, 4*cm]
    )

    header_table.setStyle(TableStyle([
    ("ALIGN", (0, 0), (0, 0), "LEFT"),
    ("ALIGN", (2, 0), (2, 0), "RIGHT"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    story.append(header_table)
    story.append(Spacer(1, 18))

    # =========================
    # PAGE DE GUARDE
    # =========================

    story.append(Paragraph("RAPPORT CLINIQUE", styles["Title"]))
    story.append(Paragraph("Ball Sorting Game", styles["Heading2"]))
    story.append(Paragraph("Rééducation fonctionnelle du membre supérieur", styles["Heading3"]))
    story.append(Spacer(1, 30))
    
    cover_data = [
    ["Patient", full_patient_name],
    ["Date de naissance", patient_birthdate],
    ["Thérapeute", therapist_name],
    ["Date de session", formatted_date],
    ]
    
    cover_table = Table(cover_data, colWidths=[5*cm, 10*cm])
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#D6EAF8")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1B4F72")),
        ("GRID", (0, 0), (-1, -1), 0.8, colors.grey),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
    ]))
    
    story.append(cover_table)
    story.append(PageBreak())

    # Synthèse clinique
    story.append(Paragraph("Synthèse clinique", styles["Heading2"]))
    
    total_balls = TOTAL_BALLS_PER_LEVEL * len(levels)

    global_success_rate = percent(total_correct / total_balls) if total_balls > 0 else 0
    global_sorting_precision = percent(total_correct / total_manipulated) if total_manipulated > 0 else 0
    
    summary_data = [
        ["Correctes", "Erreurs", "Balles manipulées", "Taux de réussite global", "Précision de tri", "Temps total"],
        [
            f"{total_correct} / {total_balls}",
            f"{total_errors} / {total_balls}",
            f"{total_manipulated} / {total_balls}",
            f"{global_success_rate}%",
            f"{global_sorting_precision}%",
            seconds_to_min_sec(total_time)
        ]
    ]

    summary_table = Table(summary_data, colWidths=[2.7*cm, 2.5*cm, 3.2*cm, 3.2*cm, 3*cm, 2.5*cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D6EAF8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1B4F72")),
        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8F9F9")),
    ]))
    
    story.append(summary_table)
    story.append(Spacer(1, 20))
    story.append(PageBreak())
    
    # =========================
    # RÉSULTATS DÉTAILLÉS PAR NIVEAU
    # =========================

    level_images = {
        1: os.path.join("assets", "level1-BallSorting.png"),
        2: os.path.join("assets", "level2-BallSorting.png"),
        3: os.path.join("assets", "level3-BallSorting.png"),
    }
    
    level_titles = {
        1: "Niveau 1 - Tri simple",
        2: "Niveau 2 - Avec contrainte temporelle",
        3: "Niveau 3 - Mémoire",
    }
    
    level_objectives = {
        1: "Objectif : évaluer la précision motrice de base, la coordination œil-main et la capacité à associer chaque balle à la couleur correspondante.",
        2: "Objectif : évaluer la précision du tri sous contrainte temporelle, ainsi que la capacité du patient à maintenir sa performance avec une limite de temps.",
        3: "Objectif : solliciter la mémoire de travail, l'attention visuelle et la coordination motrice lors d'un tri nécessitant une mémorisation temporaire des couleurs.",
    }
    
    story.append(Paragraph("Résultats détaillés par niveau", styles["Heading2"]))
    story.append(Spacer(1, 12))

    level_total_counts = {}

    for lvl in levels:
        level_num = lvl.get("level")
        level_total_counts[level_num] = level_total_counts.get(level_num, 0) + 1

    for i, lvl in enumerate(levels):
        level_label = level_labels_for_stats[i]
        level_num = lvl.get("level")

        attempt_number = int(level_label.split("Essai ")[1])

        detailed_level_title = level_titles.get(level_num, f"Niveau {level_num}")

        if level_total_counts.get(level_num, 0) > 1:
            detailed_level_title += f" - Essai {attempt_number}"

        story.append(Paragraph(detailed_level_title, styles["Heading2"]))
        story.append(Spacer(1, 8))
        
        img_path = level_images.get(level_num)
        if img_path and os.path.exists(img_path):
            story.append(Image(img_path, width=15*cm, height=8*cm))
            story.append(Spacer(1, 12))
            
        story.append(Paragraph(level_objectives.get(level_num, ""), styles["Normal"]))
        story.append(Spacer(1, 12))

        lvl_correct = lvl.get("correct", 0)
        lvl_errors = lvl.get("errors", 0)
        lvl_manipulated = lvl.get("manipulated", 0)
        lvl_time = lvl.get("time", 0)


        lvl_total_balls = TOTAL_BALLS_PER_LEVEL
        
        lvl_success_rate = percent(lvl_correct / lvl_total_balls) if lvl_total_balls > 0 else 0
        lvl_sorting_precision = percent(lvl_correct / lvl_manipulated) if lvl_manipulated > 0 else 0
        
        metrics_data = [
            ["Correctes", "Erreurs", "Balles manipulées", "Taux de réussite global", "Précision de tri", "Temps"],
            [
                f"{lvl_correct} / {lvl_total_balls}",
                f"{lvl_errors} / {lvl_total_balls}",
                f"{lvl_manipulated} / {lvl_total_balls}",
                f"{lvl_success_rate}%",
                f"{lvl_sorting_precision}%",
                seconds_to_min_sec(lvl_time)
            ]
        ]
        


        metrics_table = Table(metrics_data, colWidths=[2.7*cm, 2.5*cm, 3.2*cm, 3.2*cm, 3*cm, 2.5*cm])
        metrics_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D6EAF8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1B4F72")),
            ("GRID", (0, 0), (-1, -1), 0.8, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8F9F9")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        
        story.append(metrics_table)
        story.append(Spacer(1, 16))
        
        # Statistiques par couleur du niveau
        story.append(Paragraph("Statistiques par couleur", styles["Heading3"]))

        color_data = [["Couleur", "Total", "Correct", "Erreurs", "Accuracy"]]
        
        for c in lvl.get("colorStats", []):
            total = c.get("totalBalls", 0)
            correct = c.get("correct", 0)
            errors = c.get("errors", 0)
            acc = correct / total if total > 0 else 0
            
            color_data.append([
                c.get("color"),
                total,
                correct,
                errors,
                f"{percent(acc)}%"
            ])
            
        color_table = Table(color_data, repeatRows=1)
        color_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D5F5E3")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#145A32")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))

        story.append(color_table)
        story.append(Spacer(1, 14))

        # Statistiques par panier du niveau
        story.append(Paragraph("Statistiques par panier", styles["Heading3"]))
        
        basket_data = [["Panier", "Distance", "Hauteur", "Côté", "Tent.", "Correct", "Err.", "Acc."]]
        
        basket_level_rows = []
        
        for b in lvl.get("basketStats", []):
            attempts = b.get("attempts", 0)
            correct = b.get("correct", 0)
            errors = b.get("errors", 0)
            acc = correct / attempts if attempts > 0 else 0
            error_rate = errors / attempts if attempts > 0 else 0

            row_data = {
                "Panier": b.get("basketColor"),
                "Distance": b.get("distance"),
                "Hauteur": b.get("height"),
                "Côté": b.get("side"),
                "Tentatives": attempts,
                "Correct": correct,
                "Erreurs": errors,
                "Accuracy (%)": percent(acc),
                "Taux erreur (%)": percent(error_rate),
            }

            basket_level_rows.append(row_data)
            
            basket_data.append([
                row_data["Panier"],
                row_data["Distance"],
                row_data["Hauteur"],
                row_data["Côté"],
                row_data["Tentatives"],
                row_data["Correct"],
                row_data["Erreurs"],
                f'{row_data["Accuracy (%)"]}%'
            ])
            
        basket_table = Table(basket_data, repeatRows=1)
        basket_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FADBD8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#922B21")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
        ]))
        
        story.append(basket_table)
        story.append(Spacer(1, 14))

        # Interprétation automatique du niveau
        story.append(Paragraph("Interprétation du niveau", styles["Heading3"]))
        
        if len(basket_level_rows) > 0:
            df_level_baskets = pd.DataFrame(basket_level_rows)
            
            worst_basket = df_level_baskets.sort_values(
                ["Accuracy (%)", "Taux erreur (%)"],
                ascending=[True, False]
            ).iloc[0]
            
            best_basket = df_level_baskets.sort_values(
                ["Accuracy (%)", "Taux erreur (%)"],
                ascending=[False, True]
            ).iloc[0]
            
            if worst_basket["Accuracy (%)"] == 100:
                story.append(Paragraph(
                    "• Tous les paniers ont été réussis avec une précision de 100 %. Aucun panier ne présente de difficulté particulière sur ce niveau.",
                    styles["Normal"]
            ))
            else:
                story.append(Paragraph(
                    f"• Le panier {worst_basket['Panier']}, situé à distance {worst_basket['Distance']}, "
                    f"à hauteur {worst_basket['Hauteur']} et du côté {worst_basket['Côté']}, "
                    f"a présenté la plus grande difficulté du niveau avec {worst_basket['Accuracy (%)']}% de réussite "
                    f"et {worst_basket['Erreurs']} erreur(s) sur {worst_basket['Tentatives']} tentative(s).",
                    styles["Normal"]
                ))

                story.append(Spacer(1, 6))
                
                story.append(Paragraph(
                    f"• Le panier {best_basket['Panier']} a été le mieux réussi avec {best_basket['Accuracy (%)']}% de réussite "
                    f"sur {best_basket['Tentatives']} tentative(s).",
                    styles["Normal"]
                ))

        story.append(PageBreak())
        
    # =========================
    # ANALYSE GLOBALE
    # =========================

    story.append(Paragraph("Analyse globale", styles["Heading2"]))
    story.append(Spacer(1, 12))

    # Graphes principaux
    story.append(Paragraph("Graphiques principaux", styles["Heading2"]))

    for chart in ["graph_accuracy_niveaux.png", "graph_erreurs_niveaux.png", "graph_temps_niveaux.png"]:
        story.append(Image(chart, width=15*cm, height=9*cm))
        story.append(Spacer(1, 12))

    story.append(PageBreak())

    # Résultats par niveau
    story.append(Paragraph("Résultats par niveau", styles["Heading2"]))

    level_table_data = [["Niveau", "Correctes", "Erreurs", "Manipulées", "Taux réussite", "Précision tri", "Temps"]]

    for _, row in df_levels.iterrows():
        level_table_data.append([
            row["Niveau"],
            f'{row["Correct"]} / {TOTAL_BALLS_PER_LEVEL}',
            f'{row["Erreurs"]} / {TOTAL_BALLS_PER_LEVEL}',
            f'{row["Balles manipulées"]} / {TOTAL_BALLS_PER_LEVEL}',
            f'{row["Taux de réussite global (%)"]}%',
            f'{row["Précision de tri (%)"]}%',
            row["Temps"]
        ])

    level_table = Table(level_table_data)
    level_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D6EAF8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1B4F72")),
        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))

    story.append(level_table)
    story.append(Spacer(1, 18))

    # Analyse clinique
    story.append(Paragraph("Analyse clinique automatique", styles["Heading2"]))
    for note in clinical_notes:
        story.append(Paragraph(f"• {note}", styles["Normal"]))
        story.append(Spacer(1, 6))

    story.append(PageBreak())

    # Graphes moteurs
    story.append(Paragraph("Analyse motrice graphique", styles["Heading2"]))

    for chart in ["graph_distance.png", "graph_hauteur.png", "graph_cote.png"]:
        story.append(Image(chart, width=15*cm, height=9*cm))
        story.append(Spacer(1, 12))

    story.append(PageBreak())

    

    # Paniers difficiles
    story.append(Paragraph("Paniers difficiles détectés", styles["Heading2"]))

    if len(difficult_baskets) > 0:
        difficult_data = [["Niveau", "Panier", "Distance", "Hauteur", "Côté", "Tent.", "Err.", "Taux erreur"]]

        for _, row in difficult_baskets.iterrows():
            difficult_data.append([
                row["Niveau"],
                row["Panier"],
                row["Distance"],
                row["Hauteur"],
                row["Côté"],
                row["Tentatives"],
                row["Erreurs"],
                f'{row["Taux erreur (%)"]}%'
            ])

        difficult_table = Table(difficult_data, repeatRows=1)
        difficult_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5B7B1")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#641E16")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))

        story.append(difficult_table)
    else:
        story.append(Paragraph("Aucun panier difficile détecté.", styles["Normal"]))

    story.append(PageBreak())

    # Analyse motrice tables
    story.append(Paragraph("Analyse motrice", styles["Heading2"]))

    story.append(Paragraph("Performance selon la distance", styles["Heading3"]))
    distance_data = [["Distance", "Tentatives", "Correct", "Erreurs", "Accuracy"]]
    for _, row in df_distance.iterrows():
        distance_data.append([
            row["Distance"],
            row["Tentatives"],
            row["Correct"],
            row["Erreurs"],
            f'{row["Accuracy (%)"]}%'
        ])

    distance_table = Table(distance_data)
    distance_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(distance_table)
    story.append(Spacer(1, 15))

    story.append(Paragraph("Performance selon la hauteur", styles["Heading3"]))
    height_data = [["Hauteur", "Tentatives", "Correct", "Erreurs", "Accuracy"]]
    for _, row in df_height.iterrows():
        height_data.append([
            row["Hauteur"],
            row["Tentatives"],
            row["Correct"],
            row["Erreurs"],
            f'{row["Accuracy (%)"]}%'
        ])

    height_table = Table(height_data)
    height_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(height_table)
    story.append(Spacer(1, 15))

    story.append(Paragraph("Performance selon le côté", styles["Heading3"]))
    side_data = [["Côté", "Tentatives", "Correct", "Erreurs", "Accuracy"]]
    for _, row in df_side.iterrows():
        side_data.append([
            row["Côté"],
            row["Tentatives"],
            row["Correct"],
            row["Erreurs"],
            f'{row["Accuracy (%)"]}%'
        ])

    side_table = Table(side_data)
    side_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(side_table)

    story.append(PageBreak())

    # Analyse motrice textuelle
    story.append(Paragraph("Analyse motrice détaillée", styles["Heading2"]))

    for note in motor_notes:
        story.append(Paragraph(f"• {note}", styles["Normal"]))
        story.append(Spacer(1, 6))

    doc.build(story)

    return pdf_name

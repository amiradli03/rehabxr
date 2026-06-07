import json
import os
import re
import tempfile
from datetime import datetime
from xml.sax.saxutils import escape

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, HRFlowable
)
from reportlab.lib.units import cm

# -----------------------------------------------------------------------------
# Ball Sorting Game - Clinical PDF report generator
# Compatible with the old JSON schema and the new JSON schema.
# New schema supported:
# - root/session: selectedHand, basketSide
# - per level: selectedHand, basketSide
# - colorStats: availableBalls, manipulatedBalls, correct, errors
# -----------------------------------------------------------------------------

APP_NAME = "PhoeniXR"
DEFAULT_TOTAL_BALLS_PER_LEVEL = 31

PALETTE = {
    "primary": "#1B4F72",
    "primary_light": "#D6EAF8",
    "secondary": "#117A65",
    "secondary_light": "#D5F5E3",
    "warning": "#B9770E",
    "warning_light": "#FCF3CF",
    "danger": "#922B21",
    "danger_light": "#FADBD8",
    "purple": "#6C3483",
    "purple_light": "#EBDEF0",
    "grey": "#566573",
    "light_grey": "#F8F9F9",
    "dark": "#1C2833",
}

LEVEL_TITLES = {
    1: "Niveau 1 - Tri simple",
    2: "Niveau 2 - Contrainte temporelle",
    3: "Niveau 3 - Mémoire",
}

LEVEL_OBJECTIVES = {
    1: "Évaluer la précision motrice de base, la coordination œil-main et l'association entre la couleur de la balle et le panier correspondant.",
    2: "Évaluer la capacité à maintenir la précision du tri sous contrainte temporelle et sous augmentation de la charge motrice.",
    3: "Solliciter la mémoire de travail, l'attention visuelle et la coordination motrice dans une tâche de tri avec mémorisation temporaire des couleurs.",
}

# Optional images. If these files exist in assets/, they will be inserted.
LEVEL_IMAGES = {
    1: os.path.join("assets", "level1-BallSorting.png"),
    2: os.path.join("assets", "level2-BallSorting.png"),
    3: os.path.join("assets", "level3-BallSorting.png"),
}


def safe_div(numerator, denominator):
    return numerator / denominator if denominator not in (0, None) else 0


def percent(value):
    return round(float(value) * 100, 1)


def fmt_percent(value):
    return f"{percent(value)}%"


def seconds_to_min_sec(seconds):
    seconds = float(seconds or 0)
    minutes = int(seconds // 60)
    sec = int(seconds % 60)
    return f"{minutes} min {sec} s"


def clean_filename(value):
    value = str(value or "patient")
    value = re.sub(r"[^A-Za-z0-9_\-]+", "_", value.strip())
    return value.strip("_") or "patient"


def get_json_path(json_file):
    """Accepts a Gradio/File object, a pathlib.Path, or a plain string path."""
    if json_file is None:
        raise ValueError("Veuillez importer un fichier JSON.")
    if isinstance(json_file, (str, os.PathLike)):
        return os.fspath(json_file)
    if hasattr(json_file, "name"):
        return json_file.name
    raise TypeError("json_file doit etre un chemin ou un objet fichier avec l'attribut .name")


def format_session_date(date_value):
    if not date_value:
        return "Inconnue"
    for fmt in ["%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
        try:
            return datetime.strptime(str(date_value), fmt).strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            pass
    return str(date_value)


def format_birthdate(date_value):
    if not date_value:
        return ""
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
        try:
            return datetime.strptime(str(date_value), fmt).strftime("%d-%m-%Y")
        except Exception:
            pass
    return str(date_value)


def color_available(color_stat):
    # New schema: availableBalls. Old schema: totalBalls.
    return int(color_stat.get("availableBalls", color_stat.get("totalBalls", 0)) or 0)


def color_manipulated(color_stat):
    # New schema: manipulatedBalls. Fallback: correct + errors.
    if "manipulatedBalls" in color_stat:
        return int(color_stat.get("manipulatedBalls", 0) or 0)
    return int((color_stat.get("correct", 0) or 0) + (color_stat.get("errors", 0) or 0))


def level_available_balls(level):
    colors_ = level.get("colorStats", []) or []
    total = sum(color_available(c) for c in colors_)
    if total > 0:
        return total
    # Final fallback if colorStats is absent.
    return max(DEFAULT_TOTAL_BALLS_PER_LEVEL, int(level.get("manipulated", 0) or 0))


def level_manipulated_balls(level):
    if "manipulated" in level:
        return int(level.get("manipulated", 0) or 0)
    return sum(color_manipulated(c) for c in level.get("colorStats", []) or [])


def build_level_labels(levels):
    counts = {}
    labels = []
    for level in levels:
        num = int(level.get("level", 0) or 0)
        counts[num] = counts.get(num, 0) + 1
        labels.append(f"Niveau {num} - Essai {counts[num]}")
    return labels, counts


def make_paragraph_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CoverTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=30,
        textColor=colors.HexColor(PALETTE["primary"]),
        alignment=TA_CENTER,
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="SectionTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=colors.HexColor(PALETTE["primary"]),
        spaceBefore=8,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SubTitle",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor(PALETTE["dark"]),
        spaceBefore=8,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="Small",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
    ))
    styles.add(ParagraphStyle(
        name="SmallMuted",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor(PALETTE["grey"]),
    ))
    styles.add(ParagraphStyle(
        name="BulletSmall",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        leftIndent=8,
        firstLineIndent=-6,
    ))
    styles.add(ParagraphStyle(
        name="TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.2,
        leading=7.2,
        alignment=TA_CENTER,
        textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        name="TableCell",
        parent=styles["Normal"],
        fontSize=6.3,
        leading=7.4,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="KpiLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        alignment=TA_CENTER,
        textColor=colors.HexColor(PALETTE["grey"]),
    ))
    styles.add(ParagraphStyle(
        name="KpiValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        alignment=TA_CENTER,
        textColor=colors.HexColor(PALETTE["primary"]),
    ))
    return styles


def table_header(text, styles):
    return Paragraph(str(text), styles["TableHeader"])


def table_cell(value, styles):
    return Paragraph(str(value), styles["TableCell"])


def styled_table(data, header_bg="#1B4F72", col_widths=None, font_size=7, header_text_color=colors.white):
    """Create a compact ReportLab table with wrapping cells.
    Use \n in header labels to force a line break inside narrow columns.
    """
    header_style = ParagraphStyle(
        name="WrappedHeader",
        fontName="Helvetica-Bold",
        fontSize=font_size,
        leading=font_size + 1,
        alignment=TA_CENTER,
        textColor=header_text_color,
    )
    cell_style = ParagraphStyle(
        name="WrappedCell",
        fontName="Helvetica",
        fontSize=font_size,
        leading=font_size + 1,
        alignment=TA_CENTER,
        textColor=colors.black,
    )

    wrapped = []
    for r, row in enumerate(data):
        style = header_style if r == 0 else cell_style
        wrapped.append([
            Paragraph(escape(str(value)).replace("\n", "<br/>"), style)
            for value in row
        ])

    table = Table(wrapped, repeatRows=1, colWidths=col_widths, hAlign="CENTER")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#BFC9CA")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FFFFFF")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9F9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.6),
    ]))
    return table


def ratio_text(value, denominator):
    value = int(value or 0)
    denominator = int(denominator or 0)
    if denominator <= 0:
        return str(value)
    return f"{value} / {denominator}"


def find_level_image(level_num):
    """Find scene images even if the script is launched from another folder."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        LEVEL_IMAGES.get(level_num),
        os.path.join("assets", f"level{level_num}-BallSorting.png"),
        os.path.join("assets", f"level{level_num}_BallSorting.png"),
        os.path.join("assets", f"level{level_num}.png"),
    ]
    for path in candidates:
        if not path:
            continue
        possible_paths = [path]
        if not os.path.isabs(path):
            possible_paths.append(os.path.join(base_dir, path))
        for candidate in possible_paths:
            if os.path.exists(candidate):
                return candidate
    return None

def kpi_table(items, styles, columns=4):
    """items is a list of (label, value)."""
    rows = []
    for i in range(0, len(items), columns):
        row_items = items[i:i + columns]
        while len(row_items) < columns:
            row_items.append(("", ""))
        rows.append([Paragraph(label, styles["KpiLabel"]) for label, value in row_items])
        rows.append([Paragraph(str(value), styles["KpiValue"]) for label, value in row_items])
    col_width = 17.5 * cm / columns
    tbl = Table(rows, colWidths=[col_width] * columns, hAlign="CENTER")
    tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#D5DBDB")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FDFEFE")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PALETTE["primary_light"])),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor(PALETTE["primary_light"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return tbl


def draw_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor(PALETTE["grey"]))
    footer = f"{APP_NAME} - Rapport clinique Ball Sorting Game | Page {doc.page}"
    canvas.drawRightString(A4[0] - 1.5 * cm, 0.8 * cm, footer)
    canvas.restoreState()


def save_bar_chart(labels, values, title, ylabel, filename, color="#1B4F72", ylim=None):
    plt.figure(figsize=(8.2, 4.6))
    plt.bar(labels, values, color=color)
    plt.title(title, fontsize=13, fontweight="bold")
    plt.ylabel(ylabel)
    plt.xticks(rotation=25, ha="right", fontsize=8)
    plt.yticks(fontsize=8)
    if ylim:
        plt.ylim(*ylim)
    plt.grid(axis="y", linestyle="--", alpha=0.35)
    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close()


def save_grouped_bar_chart(df, x_col, value_cols, title, ylabel, filename):
    if df.empty:
        return None
    labels = df[x_col].astype(str).tolist()
    x = range(len(labels))
    width = 0.8 / max(1, len(value_cols))
    plt.figure(figsize=(8.2, 4.7))
    for idx, col in enumerate(value_cols):
        positions = [i - 0.4 + width / 2 + idx * width for i in x]
        plt.bar(positions, df[col].tolist(), width=width, label=col)
    plt.title(title, fontsize=13, fontweight="bold")
    plt.ylabel(ylabel)
    plt.xticks(list(x), labels, rotation=25, ha="right", fontsize=8)
    plt.yticks(fontsize=8)
    plt.grid(axis="y", linestyle="--", alpha=0.35)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close()
    return filename


def save_heatmap(df, index_col, columns_col, values_col, title, filename):
    if df.empty:
        return None
    pivot = df.pivot_table(index=index_col, columns=columns_col, values=values_col, aggfunc="sum", fill_value=0)
    if pivot.empty:
        return None
    plt.figure(figsize=(8.2, 4.8))
    plt.imshow(pivot.values, aspect="auto")
    plt.title(title, fontsize=13, fontweight="bold")
    plt.xticks(range(len(pivot.columns)), [str(c) for c in pivot.columns], rotation=25, ha="right", fontsize=8)
    plt.yticks(range(len(pivot.index)), [str(i) for i in pivot.index], fontsize=8)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            plt.text(j, i, str(int(pivot.values[i, j])), ha="center", va="center", fontsize=8)
    plt.colorbar(label=values_col)
    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close()
    return filename


def normalize_data(data):
    levels = data.get("levels", []) or []
    labels, counts = build_level_labels(levels)

    level_rows = []
    color_rows = []
    basket_rows = []

    for idx, level in enumerate(levels):
        label = labels[idx]
        level_num = int(level.get("level", 0) or 0)
        available = level_available_balls(level)
        manipulated = level_manipulated_balls(level)
        correct = int(level.get("correct", 0) or 0)
        errors = int(level.get("errors", 0) or 0)
        time_s = float(level.get("time", 0) or 0)
        non_manipulated = max(available - manipulated, 0)
        precision = safe_div(correct, manipulated)
        success = safe_div(correct, available)
        completion = safe_div(manipulated, available)
        error_rate = safe_div(errors, manipulated)
        speed = safe_div(manipulated, time_s / 60.0) if time_s > 0 else 0

        level_rows.append({
            "Niveau": label,
            "LevelNumber": level_num,
            "Main": level.get("selectedHand", data.get("selectedHand", "")),
            "Cote paniers": level.get("basketSide", data.get("basketSide", "")),
            "Disponibles": available,
            "Manipulees": manipulated,
            "Non manipulees": non_manipulated,
            "Correctes": correct,
            "Erreurs": errors,
            "Temps (s)": round(time_s, 1),
            "Temps": seconds_to_min_sec(time_s),
            "Reussite globale (%)": percent(success),
            "Precision tri (%)": percent(precision),
            "Realisation (%)": percent(completion),
            "Taux erreur (%)": percent(error_rate),
            "Vitesse (balles/min)": round(speed, 2),
            "Accuracy JSON (%)": percent(level.get("accuracy", precision)),
        })

        available_by_color = {}
        for c in level.get("colorStats", []) or []:
            color = c.get("color", "Inconnue")
            av = color_available(c)
            manip = color_manipulated(c)
            corr = int(c.get("correct", 0) or 0)
            err = int(c.get("errors", 0) or 0)
            non_manip = max(av - manip, 0)
            available_by_color[color] = av

            color_rows.append({
                "Niveau": label,
                "Couleur": color,
                "Disponibles": av,
                "Manipulees": manip,
                "Non manipulees": non_manip,
                "Correctes": corr,
                "Erreurs": err,
                "Realisation (%)": percent(safe_div(manip, av)),
                "Reussite globale (%)": percent(safe_div(corr, av)),
                "Precision tri (%)": percent(safe_div(corr, manip)),
                "Taux erreur (%)": percent(safe_div(err, manip)),
            })

        for b in level.get("basketStats", []) or []:
            basket_color = b.get("basketColor", "Inconnu")
            expected = available_by_color.get(basket_color, 0)
            attempts = int(b.get("attempts", 0) or 0)
            corr = int(b.get("correct", 0) or 0)
            err = int(b.get("errors", 0) or 0)
            missing = max(expected - corr, 0)
            extra = max(attempts - expected, 0)

            basket_rows.append({
                "Niveau": label,
                "Panier": basket_color,
                "Distance": b.get("distance", ""),
                "Hauteur": b.get("height", ""),
                "Côté": b.get("side", ""),
                "Attendues": expected,
                "Recues": attempts,
                "Correctes": corr,
                "Erreurs": err,
                "Manquantes": missing,
                "Sur-reception": extra,
                "Taux atteinte (%)": percent(safe_div(corr, expected)),
                "Purete (%)": percent(safe_div(corr, attempts)),
                "Taux erreur (%)": percent(safe_div(err, attempts)),
            })

    df_levels = pd.DataFrame(level_rows)
    df_colors = pd.DataFrame(color_rows)
    df_baskets = pd.DataFrame(basket_rows)

    return df_levels, df_colors, df_baskets


def aggregate_motor(df_baskets, column):
    if df_baskets.empty or column not in df_baskets.columns:
        return pd.DataFrame()
    df = df_baskets.groupby(column)[["Attendues", "Recues", "Correctes", "Erreurs", "Manquantes", "Sur-reception"]].sum().reset_index()
    df["Taux atteinte (%)"] = (df["Correctes"] / df["Attendues"].replace(0, pd.NA) * 100).fillna(0).round(1)
    df["Purete (%)"] = (df["Correctes"] / df["Recues"].replace(0, pd.NA) * 100).fillna(0).round(1)
    df["Taux erreur (%)"] = (df["Erreurs"] / df["Recues"].replace(0, pd.NA) * 100).fillna(0).round(1)
    return df


def create_clinical_notes(df_levels, df_colors, df_baskets):
    notes = []
    if df_levels.empty:
        return ["Aucun niveau exploitable n'a ete trouve dans le fichier JSON."]

    total_available = int(df_levels["Disponibles"].sum())
    total_manipulated = int(df_levels["Manipulees"].sum())
    total_correct = int(df_levels["Correctes"].sum())
    total_errors = int(df_levels["Erreurs"].sum())
    total_unmanipulated = int(df_levels["Non manipulees"].sum())

    global_success = percent(safe_div(total_correct, total_available))
    global_précision = percent(safe_div(total_correct, total_manipulated))
    global_completion = percent(safe_div(total_manipulated, total_available))

    if global_précision >= 90:
        notes.append(f"La précision de tri est élevée ({global_précision}%), ce qui indique que les balles manipulées sont majoritairement placées correctement.")
    elif global_précision >= 75:
        notes.append(f"La précision de tri est acceptable ({global_précision}%), avec des erreurs localisées à analyser par couleur et par panier.")
    else:
        notes.append(f"La précision de tri est faible ({global_précision}%), ce qui peut traduire des difficultés d'association couleur-panier, d'attention ou de contrôle moteur.")

    if global_completion < 90:
        notes.append(f"Le taux de réalisation global est incomplet ({global_completion}%) : {total_unmanipulated} balle(s) disponible(s) n'ont pas été manipulée(s).")
    else:
        notes.append(f"Le taux de réalisation global est satisfaisant ({global_completion}%), avec une couverture suffisante de la tâche.")

    if total_errors > 0:
        notes.append(f"La session contient {total_errors} erreur(s), à interpréter avec la cartographie par couleur et par panier.")
    else:
        notes.append("Aucune erreur de tri n'a été détectée sur les balles manipulees.")

    # Most difficult level by global success.
    worst_level = df_levels.sort_values(["Reussite globale (%)", "Precision tri (%)"]).iloc[0]
    notes.append(
        f"Le niveau le plus sensible est {worst_level['Niveau']} : réussite globale {worst_level['Reussite globale (%)']}%, "
        f"précision {worst_level['Precision tri (%)']}%, réalisation {worst_level['Realisation (%)']}%."
    )

    if not df_colors.empty:
        color_global = df_colors.groupby("Couleur")[["Disponibles", "Manipulees", "Correctes", "Erreurs", "Non manipulees"]].sum().reset_index()
        color_global["Reussite globale (%)"] = (color_global["Correctes"] / color_global["Disponibles"].replace(0, pd.NA) * 100).fillna(0).round(1)
        color_global["Precision tri (%)"] = (color_global["Correctes"] / color_global["Manipulees"].replace(0, pd.NA) * 100).fillna(0).round(1)
        worst_color = color_global.sort_values(["Reussite globale (%)", "Precision tri (%)"]).iloc[0]
        notes.append(
            f"La couleur la plus fragile est {worst_color['Couleur']} : réussite globale {worst_color['Reussite globale (%)']}%, "
            f"précision {worst_color['Precision tri (%)']}%, erreurs {int(worst_color['Erreurs'])}."
        )

    if not df_baskets.empty:
        critical = df_baskets[
            (df_baskets["Purete (%)"] < 80) |
            (df_baskets["Taux atteinte (%)"] < 80) |
            (df_baskets["Erreurs"] >= 2) |
            (df_baskets["Manquantes"] >= 2)
        ]
        if not critical.empty:
            notes.append(f"{len(critical)} panier(s) nécessitent une attention particuliere selon les critères de pureté, atteinte, erreurs ou balles manquantes.")
        else:
            notes.append("Aucun panier ne depasse les seuils d'alerte definis pour cette analyse.")

    return notes


def generate_clinical_pdf(json_file, patient_info=None, output_dir=None):
    json_path = get_json_path(json_file)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if patient_info is None:
        patient_info = {}

    patient_from_json = data.get("patientName", "Inconnu")
    patient_firstname = patient_info.get("firstname", "")
    patient_lastname = patient_info.get("lastname", "")
    full_patient_name = f"{patient_firstname} {patient_lastname}".strip() or patient_from_json
    patient_birthdate = format_birthdate(patient_info.get("birthdate", ""))
    therapist_name = patient_info.get("therapist", "")
    formatted_date = format_session_date(data.get("sessionDate", ""))
    selected_hand = data.get("selectedHand", "")
    basket_side = data.get("basketSide", "")

    df_levels, df_colors, df_baskets = normalize_data(data)
    if df_levels.empty:
        raise ValueError("Le fichier JSON ne contient aucun niveau exploitable.")

    total_available = int(df_levels["Disponibles"].sum())
    total_correct = int(df_levels["Correctes"].sum())
    total_errors = int(df_levels["Erreurs"].sum())
    total_manipulated = int(df_levels["Manipulees"].sum())
    total_unmanipulated = int(df_levels["Non manipulees"].sum())
    total_time = float(df_levels["Temps (s)"].sum())

    global_success = percent(safe_div(total_correct, total_available))
    global_précision = percent(safe_div(total_correct, total_manipulated))
    global_completion = percent(safe_div(total_manipulated, total_available))
    global_error_rate = percent(safe_div(total_errors, total_manipulated))
    global_speed = round(safe_div(total_manipulated, total_time / 60.0), 2) if total_time > 0 else 0

    # Aggregations
    df_distance = aggregate_motor(df_baskets, "Distance")
    df_height = aggregate_motor(df_baskets, "Hauteur")
    df_side = aggregate_motor(df_baskets, "Côté")


    motor_conclusions = []
    
    if not df_distance.empty:
        worst_distance = df_distance.sort_values(
            ["Taux atteinte (%)", "Purete (%)", "Taux erreur (%)"],
            ascending=[True, True, False]
        ).iloc[0]
        
        motor_conclusions.append(
            f"La distance la plus difficile est {worst_distance['Distance']} : "
            f"taux d'atteinte {worst_distance['Taux atteinte (%)']}%, "
            f"pureté {worst_distance['Purete (%)']}%, "
            f"taux d'erreur {worst_distance['Taux erreur (%)']}%."
        )
        
    if not df_height.empty:
        worst_height = df_height.sort_values(
            ["Taux atteinte (%)", "Purete (%)", "Taux erreur (%)"],
            ascending=[True, True, False]
        ).iloc[0]
        
        motor_conclusions.append(
            f"La hauteur la plus difficile est {worst_height['Hauteur']} : "
            f"taux d'atteinte {worst_height['Taux atteinte (%)']}%, "
            f"pureté {worst_height['Purete (%)']}%, "
            f"taux d'erreur {worst_height['Taux erreur (%)']}%."
        )
        
    if not df_side.empty:
        worst_side = df_side.sort_values(
            ["Taux atteinte (%)", "Purete (%)", "Taux erreur (%)"],
            ascending=[True, True, False]
        ).iloc[0]
        
        motor_conclusions.append(
            f"Le côté le plus difficile est {worst_side['Côté']} : "
            f"taux d'atteinte {worst_side['Taux atteinte (%)']}%, "
            f"pureté {worst_side['Purete (%)']}%, "
            f"taux d'erreur {worst_side['Taux erreur (%)']}%."
        )

    df_color_global = df_colors.groupby("Couleur")[["Disponibles", "Manipulees", "Non manipulees", "Correctes", "Erreurs"]].sum().reset_index() if not df_colors.empty else pd.DataFrame()
    if not df_color_global.empty:
        df_color_global["Reussite globale (%)"] = (df_color_global["Correctes"] / df_color_global["Disponibles"].replace(0, pd.NA) * 100).fillna(0).round(1)
        df_color_global["Precision tri (%)"] = (df_color_global["Correctes"] / df_color_global["Manipulees"].replace(0, pd.NA) * 100).fillna(0).round(1)
        df_color_global["Realisation (%)"] = (df_color_global["Manipulees"] / df_color_global["Disponibles"].replace(0, pd.NA) * 100).fillna(0).round(1)

    attention_baskets = df_baskets[
        (df_baskets["Purete (%)"] < 80) |
        (df_baskets["Taux atteinte (%)"] < 80) |
        (df_baskets["Erreurs"] >= 2) |
        (df_baskets["Manquantes"] >= 2)
    ].copy() if not df_baskets.empty else pd.DataFrame()

    clinical_notes = create_clinical_notes(df_levels, df_colors, df_baskets)

    if output_dir is None:
        output_dir = os.getcwd()
    os.makedirs(output_dir, exist_ok=True)

    clean_patient = clean_filename(full_patient_name)
    pdf_name = f"rapport_clinique_ball_sorting_v2_{clean_patient}.pdf"
    pdf_path = os.path.join(output_dir, pdf_name)

    styles = make_paragraph_styles()

    with tempfile.TemporaryDirectory() as tmpdir:
        chart_paths = {}

        # Charts
        chart_paths["level_success"] = os.path.join(tmpdir, "level_success.png")
        save_bar_chart(
            df_levels["Niveau"].tolist(), df_levels["Reussite globale (%)"].tolist(),
            "Reussite globale par niveau", "Reussite globale (%)",
            chart_paths["level_success"], color=PALETTE["primary"], ylim=(0, 100)
        )
        chart_paths["level_précision"] = os.path.join(tmpdir, "level_précision.png")
        save_bar_chart(
            df_levels["Niveau"].tolist(), df_levels["Precision tri (%)"].tolist(),
            "Precision de tri par niveau", "Precision (%)",
            chart_paths["level_précision"], color=PALETTE["secondary"], ylim=(0, 100)
        )
        chart_paths["level_completion"] = os.path.join(tmpdir, "level_completion.png")
        save_bar_chart(
            df_levels["Niveau"].tolist(), df_levels["Realisation (%)"].tolist(),
            "Taux de réalisation par niveau", "Realisation (%)",
            chart_paths["level_completion"], color=PALETTE["warning"], ylim=(0, 100)
        )
        chart_paths["level_errors"] = os.path.join(tmpdir, "level_errors.png")
        save_bar_chart(
            df_levels["Niveau"].tolist(), df_levels["Erreurs"].tolist(),
            "Erreurs par niveau", "Nombre d'erreurs",
            chart_paths["level_errors"], color=PALETTE["danger"]
        )
        if not df_color_global.empty:
            chart_paths["color_global"] = os.path.join(tmpdir, "color_global.png")
            save_grouped_bar_chart(
                df_color_global, "Couleur", ["Disponibles", "Manipulees", "Correctes", "Erreurs"],
                "Profil global par couleur", "Nombre de balles", chart_paths["color_global"]
            )
            chart_paths["color_errors_heatmap"] = os.path.join(tmpdir, "color_errors_heatmap.png")
            save_heatmap(df_colors, "Niveau", "Couleur", "Erreurs", "Cartographie des erreurs par couleur et niveau", chart_paths["color_errors_heatmap"])

        for name, df, col in [("distance", df_distance, "Distance"), ("height", df_height, "Hauteur"), ("side", df_side, "Côté")]:
            if not df.empty:
                p = os.path.join(tmpdir, f"motor_{name}.png")
                save_grouped_bar_chart(df, col, ["Taux atteinte (%)", "Purete (%)", "Taux erreur (%)"],
                                       f"Performance selon {col.lower()}", "Pourcentage (%)", p)
                chart_paths[f"motor_{name}"] = p

        # PDF document
        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            rightMargin=1.25 * cm,
            leftMargin=1.25 * cm,
            topMargin=1.25 * cm,
            bottomMargin=1.25 * cm,
        )
        story = []

        # Cover header: logos if available.
        logo_app_path = os.path.join("assets", "Logo-APP.png")
        logo_enp_path = os.path.join("assets", "Logo-ENP.png")
        left_logo = Image(logo_app_path, width=2.5 * cm, height=2.5 * cm) if os.path.exists(logo_app_path) else Paragraph(APP_NAME, styles["SectionTitle"])
        right_logo = Image(logo_enp_path, width=2.5 * cm, height=2.5 * cm) if os.path.exists(logo_enp_path) else Paragraph("ENP Alger", styles["SectionTitle"])
        header_table = Table([[left_logo, "", right_logo]], colWidths=[4 * cm, 9 * cm, 4 * cm])
        header_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 30))

        story.append(Paragraph("RAPPORT CLINIQUE", styles["CoverTitle"]))
        story.append(Paragraph("Ball Sorting Game", styles["SectionTitle"]))
        story.append(Paragraph("Rééducation fonctionnelle du membre supérieur", styles["SubTitle"]))
        story.append(Spacer(1, 24))

        cover_data = [
            ["Patient", full_patient_name],
            ["Date de naissance", patient_birthdate],
            ["Thérapeute", therapist_name],
            ["Date de session", formatted_date],
            ["Main sélectionnée", selected_hand],
            ["Disposition des paniers", basket_side],
        ]
        cover_table = Table(cover_data, colWidths=[5.2 * cm, 11.5 * cm], hAlign="CENTER")
        cover_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(PALETTE["primary_light"])),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(PALETTE["primary"])),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#AAB7B8")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(cover_table)
        story.append(Spacer(1, 20))
        story.append(Paragraph(
            "Ce rapport présente les performances de tri, la réalisation de la tâche, la précision des placements et la localisation des erreurs selon les couleurs, les paniers et les contraintes spatiales.",
            styles["SmallMuted"]
        ))
        story.append(PageBreak())

        # Summary
        story.append(Paragraph("1. Synthèse clinique", styles["SectionTitle"]))
        kpis = [
            ("Balles disponibles", total_available),
            ("Balles manipulées", f"{total_manipulated} / {total_available}"),
            ("Balles non manipulées", total_unmanipulated),
            ("Correctes", f"{total_correct} / {total_available}"),
            ("Erreurs", f"{total_errors} / {total_manipulated}"),
            ("Réussite globale", f"{global_success}%"),
            ("Précision de tri", f"{global_précision}%"),
            ("Réalisation", f"{global_completion}%"),
            ("Taux d'erreur", f"{global_error_rate}%"),
            ("Vitesse moyenne", f"{global_speed} balles/min"),
            ("Temps total", seconds_to_min_sec(total_time)),
            ("Accuracy JSON", f"{percent(data.get('totalAccuracy', safe_div(total_correct, total_manipulated)))}%"),
        ]
        story.append(kpi_table(kpis, styles, columns=4))
        story.append(Spacer(1, 12))
        story.append(Paragraph("Lecture des indicateurs", styles["SubTitle"]))
        metric_definitions = [
            "Réussite globale = balles correctes / balles disponibles. Elle tient compte des balles non réalisées.",
            "Précision de tri = balles correctes / balles manipulées. Elle correspond à la qualité du tri parmi les balles effectivement traitées.",
            "Réalisation = balles manipulées / balles disponibles. Elle mesure l'avancement complet de la tâche.",
            "Pureté d'un panier = balles correctes reçues / total des balles reçues par ce panier.",
        ]
        for item in metric_definitions:
            story.append(Paragraph(f"- {item}", styles["BulletSmall"]))
        story.append(Spacer(1, 12))

        story.append(Paragraph("Interprétation automatique", styles["SubTitle"]))
        for note in clinical_notes:
            story.append(Paragraph(f"- {note}", styles["BulletSmall"]))
        story.append(PageBreak())

        # Detailed per level
        story.append(Paragraph("2. Résultats détaillés par niveau", styles["SectionTitle"]))
        for _, row in df_levels.iterrows():
            level_num = int(row["LevelNumber"])
            story.append(KeepTogether([
                Paragraph(LEVEL_TITLES.get(level_num, f"Niveau {level_num}") + f" - {row['Niveau'].split(' - ')[-1]}", styles["SubTitle"]),
                Paragraph(LEVEL_OBJECTIVES.get(level_num, ""), styles["Small"]),
                Spacer(1, 6),
            ]))

            img_path = find_level_image(level_num)
            if img_path:
                story.append(Image(img_path, width=15.5 * cm, height=7.8 * cm))
                story.append(Spacer(1, 8))

            level_den = int(row["Disponibles"])
            level_summary = [
                ["Balles\ndisponibles", "Balles\nmanipulées", "Balles non\nmanipulées", "Correctes", "Erreurs", "Réussite\nglobale", "Précision\nde tri", "Taux de\nréalisation", "Temps", "Vitesse"],
                [
                    ratio_text(row["Disponibles"], level_den),
                    ratio_text(row["Manipulees"], level_den),
                    ratio_text(row["Non manipulees"], level_den),
                    ratio_text(row["Correctes"], level_den),
                    ratio_text(row["Erreurs"], level_den),
                    f"{row['Reussite globale (%)']}%", f"{row['Precision tri (%)']}%", f"{row['Realisation (%)']}%",
                    row["Temps"], row["Vitesse (balles/min)"]
                ]
            ]
            story.append(styled_table(level_summary, header_bg=PALETTE["primary"], font_size=5.9))
            story.append(Spacer(1, 8))

            # Color stats for the level
            level_colors = df_colors[df_colors["Niveau"] == row["Niveau"]]
            if not level_colors.empty:
                story.append(Paragraph("Statistiques par couleur", styles["SubTitle"]))
                color_table_data = [["Couleur", "Balles\ndisponibles", "Balles\nmanipulées", "Balles non\nmanipulées", "Correctes", "Erreurs", "Réalisation", "Réussite\nglobale", "Précision\nde tri", "Taux\nd'erreur"]]
                for _, c in level_colors.iterrows():
                    color_den = int(c["Disponibles"])
                    color_manip = int(c["Manipulees"])
                    color_table_data.append([
                        c["Couleur"],
                        ratio_text(c["Disponibles"], color_den),
                        ratio_text(c["Manipulees"], color_den),
                        ratio_text(c["Non manipulees"], color_den),
                        ratio_text(c["Correctes"], color_den),
                        ratio_text(c["Erreurs"], color_den),
                        f"{c['Realisation (%)']}%", f"{c['Reussite globale (%)']}%", f"{c['Precision tri (%)']}%", f"{c['Taux erreur (%)']}%"
                    ])
                story.append(styled_table(color_table_data, header_bg=PALETTE["secondary"],
                                          col_widths=[1.55*cm, 1.55*cm, 1.55*cm, 1.7*cm, 1.35*cm, 1.2*cm, 1.35*cm, 1.45*cm, 1.35*cm, 1.25*cm],
                                          font_size=4.9))
                story.append(Spacer(1, 8))

            # Basket stats for the level
            level_baskets = df_baskets[df_baskets["Niveau"] == row["Niveau"]]
            if not level_baskets.empty:
                story.append(Paragraph("Statistiques par panier", styles["SubTitle"]))
                basket_table_data = [["Panier", "Distance", "Hauteur", "Côté", "Balles\nattendues", "Balles\nreçues", "Bonne couleur\nreçue", "Mauvaise couleur\nreçue", "Balles\nmanquantes", "Taux\nd'atteinte", "Pureté"]]
                for _, b in level_baskets.iterrows():
                    expected = int(b["Attendues"])
                    received = int(b["Recues"])
                    basket_table_data.append([
                        b["Panier"], b["Distance"], b["Hauteur"], b["Côté"],
                        str(expected),
                        ratio_text(received, expected),
                        ratio_text(b["Correctes"], expected),
                        ratio_text(b["Erreurs"], received),
                        ratio_text(b["Manquantes"], expected),
                        f"{b['Taux atteinte (%)']}%", f"{b['Purete (%)']}%"
                    ])
                story.append(styled_table(basket_table_data, header_bg=PALETTE["danger"],
                                          col_widths=[1.35*cm, 1.2*cm, 1.15*cm, 1.05*cm, 1.45*cm, 1.35*cm, 1.55*cm, 1.75*cm, 1.45*cm, 1.35*cm, 1.1*cm],
                                          font_size=4.55))
                story.append(Spacer(1, 8))

                # Local interpretation
                story.append(Paragraph("Interprétation du niveau", styles["SubTitle"]))
                all_targets_ok = (
                    float(level_baskets["Taux atteinte (%)"].min()) >= 100
                    and float(level_baskets["Purete (%)"].min()) >= 100
                    and int(level_baskets["Erreurs"].sum()) == 0
                    and int(level_baskets["Manquantes"].sum()) == 0
                )

                if all_targets_ok:
                    story.append(Paragraph(
                        "- Toutes les cibles ont été atteintes correctement. Aucun panier ne présente de difficulté particulière sur ce niveau.",
                        styles["BulletSmall"]
                    ))
                else:
                    worst_att = level_baskets.sort_values(["Taux atteinte (%)", "Purete (%)"]).iloc[0]
                    most_err = level_baskets.sort_values(["Erreurs", "Manquantes"], ascending=False).iloc[0]
                    story.append(Paragraph(
                        f"- Cible la moins atteinte : panier {worst_att['Panier']} ({worst_att['Distance']}, {worst_att['Hauteur']}, {worst_att['Côté']}) avec {worst_att['Taux atteinte (%)']}% d'atteinte et {worst_att['Purete (%)']}% de pureté.",
                        styles["BulletSmall"]
                    ))
                    if int(most_err["Erreurs"]) > 0:
                        story.append(Paragraph(
                            f"- Panier recevant le plus de mauvaises couleurs : {most_err['Panier']} avec {int(most_err['Erreurs'])} erreur(s) reçue(s).",
                            styles["BulletSmall"]
                        ))
                    else:
                        story.append(Paragraph("- Aucun panier n'a reçu de balle de mauvaise couleur sur ce niveau.", styles["BulletSmall"]))
                        
            story.append(PageBreak())

        # Global visual analysis
        story.append(Paragraph("3. Analyse graphique globale", styles["SectionTitle"]))
        for key in ["level_success", "level_précision", "level_completion", "level_errors"]:
            if key in chart_paths and os.path.exists(chart_paths[key]):
                story.append(Image(chart_paths[key], width=15.8 * cm, height=8.7 * cm))
                story.append(Spacer(1, 8))
        story.append(PageBreak())

        story.append(Paragraph("4. Analyse par couleur", styles["SectionTitle"]))
        if not df_color_global.empty:
            color_global_table = [["Couleur", "Dispo.", "Manip.", "Non manip.", "Correctes", "Erreurs", "Réal.", "Réussite", "Précision"]]
            for _, c in df_color_global.iterrows():
                color_global_table.append([
                    c["Couleur"], int(c["Disponibles"]), int(c["Manipulees"]), int(c["Non manipulees"]), int(c["Correctes"]), int(c["Erreurs"]),
                    f"{c['Realisation (%)']}%", f"{c['Reussite globale (%)']}%", f"{c['Precision tri (%)']}%"
                ])
            story.append(styled_table(color_global_table, header_bg=PALETTE["secondary"], font_size=6.4))
            story.append(Spacer(1, 10))
            if os.path.exists(chart_paths.get("color_global", "")):
                story.append(Image(chart_paths["color_global"], width=15.8 * cm, height=8.7 * cm))
                story.append(Spacer(1, 8))
            if os.path.exists(chart_paths.get("color_errors_heatmap", "")):
                story.append(Image(chart_paths["color_errors_heatmap"], width=15.8 * cm, height=8.7 * cm))
        else:
            story.append(Paragraph("Aucune statistique par couleur n'est disponible.", styles["Small"]))
        story.append(PageBreak())

        # Motor analysis
        story.append(Paragraph("5. Analyse motrice spatiale", styles["SectionTitle"]))
        for title, df, col, chart_key in [
            ("Performance selon la distance", df_distance, "Distance", "motor_distance"),
            ("Performance selon la hauteur", df_height, "Hauteur", "motor_height"),
            ("Performance selon le côté", df_side, "Côté", "motor_side"),
        ]:
            if df.empty:
                continue
            story.append(Paragraph(title, styles["SubTitle"]))
            motor_table = [[col, "Balles\nattendues", "Balles\nreçues", "Correctes\nreçues", "Erreurs\nreçues", "Balles\nmanquantes", "Taux\nd'atteinte", "Pureté", "Taux\nd'erreur"]]
            for _, r in df.iterrows():
                expected = int(r["Attendues"])
                received = int(r["Recues"])
                motor_table.append([
                    r[col],
                    str(expected),
                    ratio_text(received, expected),
                    ratio_text(r["Correctes"], expected),
                    ratio_text(r["Erreurs"], received),
                    ratio_text(r["Manquantes"], expected),
                    f"{r['Taux atteinte (%)']}%", f"{r['Purete (%)']}%", f"{r['Taux erreur (%)']}%"
                ])
            story.append(styled_table(motor_table, header_bg=PALETTE["purple"], font_size=5.1))
            story.append(Spacer(1, 8))
            if chart_key in chart_paths and os.path.exists(chart_paths[chart_key]):
                story.append(Image(chart_paths[chart_key], width=15.6 * cm, height=8.3 * cm))
                story.append(Spacer(1, 10))
                
        if motor_conclusions:
            story.append(Spacer(1, 10))
            story.append(Paragraph("Conclusion motrice spatiale", styles["SubTitle"]))
                
            for conclusion in motor_conclusions:
                story.append(Paragraph(f"- {conclusion}", styles["BulletSmall"]))


        story.append(PageBreak())

        # Attention baskets
        story.append(Paragraph("6. Points d'attention", styles["SectionTitle"]))
        story.append(Paragraph(
            "Les paniers ci-dessous sont signalés lorsque la pureté est inférieure a 80%, le taux d'atteinte est inférieur a 80%, le nombre d'erreurs est supérieur ou égal a 2, ou lorsqu'au moins deux balles attendues sont manquantes.",
            styles["Small"]
        ))
        story.append(Spacer(1, 8))
        if not attention_baskets.empty:
            attention_table = [["Niveau", "Panier", "Distance", "Hauteur", "Côté", "Balles\nattendues", "Balles\nreçues", "Bonne couleur\nreçue", "Mauvaise couleur\nreçue", "Balles\nmanquantes", "Atteinte", "Pureté"]]
            for _, b in attention_baskets.iterrows():
                expected = int(b["Attendues"])
                received = int(b["Recues"])
                attention_table.append([
                    b["Niveau"], b["Panier"], b["Distance"], b["Hauteur"], b["Côté"],
                    str(expected), ratio_text(received, expected), ratio_text(b["Correctes"], expected), ratio_text(b["Erreurs"], received),
                    ratio_text(b["Manquantes"], expected), f"{b['Taux atteinte (%)']}%", f"{b['Purete (%)']}%"
                ])
            story.append(styled_table(attention_table, header_bg=PALETTE["danger"],
                                      col_widths=[2.2*cm, 1.35*cm, 1.05*cm, 1.05*cm, 1.05*cm, 0.9*cm, 0.9*cm, 0.9*cm, 0.85*cm, 0.9*cm, 1.15*cm, 1.05*cm],
                                      font_size=5.5))
        else:
            story.append(Paragraph("Aucun point d'attention critique selon les seuils définis.", styles["Small"]))

        story.append(Spacer(1, 14))
        story.append(Paragraph("Conclusion automatique", styles["SubTitle"]))
        for note in clinical_notes:
            story.append(Paragraph(f"- {note}", styles["BulletSmall"]))

        doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)

    return pdf_path


if __name__ == "__main__":
    # Example usage in VS Code terminal:
    # python ball_sorting_report_v2.py new.json
    import sys
    json_arg = sys.argv[1] if len(sys.argv) > 1 else "new.json"
    output = generate_clinical_pdf(json_arg, patient_info={
        "firstname": "",
        "lastname": "",
        "birthdate": "",
        "therapist": "",
    }, output_dir=os.getcwd())
    print(output)

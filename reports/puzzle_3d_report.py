import json
import os
import math
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import matplotlib.patches as mpatches

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT


GRAPH_DIR = "assembly_graphs"

DEFAULT_GAME_DESCRIPTION = (
    "Assembly Stacking est un exercice de rééducation fonctionnelle du membre supérieur réalisé en réalité mixte. "
    "Le patient observe un modèle d'empilement, manipule les pieces avec la main sélectionnée, puis les place dans l'ordre attendu afin de reproduire l'assemblage. "
    "L'exercice sollicite la coordination œil-main, la planification motrice, la précision spatiale et le respect d'une séquence d'action."
)

DEFAULT_GAME_IMAGE_PATHS = [
    os.path.join("assets", "assembly_stacking_1.png"),
    os.path.join("assets", "assembly_stacking_2.png"),
    os.path.join("assets", "assembly_stacking_3.png"),
    os.path.join("assets", "assembly_stacking_4.png"),
]


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def safe_div(num, den):
    den = safe_float(den)
    if den == 0:
        return 0.0
    return safe_float(num) / den


def pct(value):
    return round(safe_float(value), 1)


def ratio_pct(num, den):
    return round(safe_div(num, den) * 100, 1)


def parse_date(value):
    if not value:
        return "Non renseignee"
    value = str(value)
    for fmt in ["%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"]:
        try:
            return datetime.strptime(value, fmt).strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            pass
    return value


def parse_birthdate(value):
    if not value:
        return ""
    value = str(value)
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
        try:
            return datetime.strptime(value, fmt).strftime("%d-%m-%Y")
        except Exception:
            pass
    return value


def seconds_to_min_sec(seconds):
    seconds = safe_float(seconds)
    minutes = int(seconds // 60)
    sec = int(seconds % 60)
    return f"{minutes} min {sec} s"


def seconds_per_piece(duration, pieces):
    if pieces <= 0:
        return 0
    return round(safe_float(duration) / pieces, 2)


def clean_filename(value):
    value = str(value).strip() or "patient"
    return value.replace(" ", "_").replace("/", "_").replace("\\", "_")


def format_hand(value):
    value = str(value).strip().lower()
    if value == "left":
        return "Main gauche"
    if value == "right":
        return "Main droite"
    return value.capitalize() if value else "Non specifiee"


def format_result(value):
    value = str(value).strip().lower()
    mapping = {
        "correct assembly": "Assemblage correct",
        "wrong or incomplete assembly": "Assemblage incorrect ou incomplet",
        "no pieces placed": "Aucune pièce placée",
    }
    return mapping.get(value, str(value) if value else "Non specifie")


def p(text, style):
    return Paragraph(str(text), style)


def q_to_y_degrees(rotation):
    y = safe_float(rotation.get("y", 0))
    w = safe_float(rotation.get("w", 1))
    angle = math.degrees(2 * math.atan2(y, w))
    # Normalisation dans [-180, 180]
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return round(angle, 1)


def height_level(index, total):
    if total <= 0:
        return "-"
    rank = index + 1
    if rank <= math.ceil(total / 3):
        return "Base"
    if rank <= math.ceil(2 * total / 3):
        return "Milieu"
    return "Sommet"


def side_label(layer_name):
    layer = str(layer_name)
    if layer == "LeftHandOnly" or layer == "RightHandOnly":
        return "Côté thérapeutique"
    return "Côté opposé / libre"


def order_match_score(expected_order, placed_order):
    if not expected_order:
        return 0, 0, 0.0
    total = len(expected_order)
    correct = 0
    for i in range(total):
        if i < len(placed_order) and placed_order[i] == expected_order[i]:
            correct += 1
    return correct, total, ratio_pct(correct, total)


def classify_validation(validation, total_pieces, expected_order, is_final=False):
    placed = safe_int(validation.get("placedPieces", 0))
    total = safe_int(validation.get("totalPieces", total_pieces), total_pieces)
    if total <= 0:
        total = total_pieces
    missing = safe_int(validation.get("missingPieces", max(total - placed, 0)))
    correct = safe_int(validation.get("correctPositions", 0))
    wrong = safe_int(validation.get("wrongPositions", 0))
    accuracy = pct(validation.get("accuracyPercent", ratio_pct(correct, total)))
    is_correct = bool(validation.get("isCorrect", False))
    placed_order = validation.get("placedOrder", []) or []
    seq_correct, seq_total, seq_accuracy = order_match_score(expected_order, placed_order)

    if placed == 0:
        vtype = "Validation prématurée"
    elif placed < total:
        vtype = "Validation partielle"
    elif is_correct:
        vtype = "Validation finale correcte" if is_final else "Validation complète correcte"
    else:
        vtype = "Validation complète incorrecte"

    return {
        "attempt": validation.get("attemptNumber", ""),
        "time": parse_date(validation.get("validationTime", "")),
        "type": vtype,
        "placed": placed,
        "total": total,
        "missing": missing,
        "correct": correct,
        "wrong": wrong,
        "accuracy": accuracy,
        "séquence_accuracy": seq_accuracy,
        "séquence_correct": seq_correct,
        "placed_order": placed_order,
        "is_correct": is_correct,
        "is_final": is_final,
        "result": format_result(validation.get("result", "")),
    }


def validation_metrics(data):
    total_pieces = safe_int(data.get("totalPieces", 0))
    expected_order = data.get("expectedOrder", []) or []
    history = data.get("validationHistory", []) or []

    if not history:
        # Fallback pour anciens exports sans historique
        history = [{
            "attemptNumber": 1,
            "validationTime": data.get("endTime", ""),
            "isCorrect": data.get("isCorrect", False),
            "result": data.get("result", ""),
            "totalPieces": total_pieces,
            "placedPieces": data.get("placedPieces", 0),
            "missingPieces": data.get("missingPieces", 0),
            "correctPositions": data.get("correctPositions", 0),
            "wrongPositions": data.get("wrongPositions", 0),
            "accuracyPercent": data.get("accuracyPercent", 0),
            "placedOrder": data.get("placedOrder", []),
        }]

    final_index = len(history) - 1
    interprétéd = [classify_validation(v, total_pieces, expected_order, i == final_index) for i, v in enumerate(history)]

    evaluated_positions = sum(max(v["total"], 0) for v in interprétéd)
    cumulative_correct = sum(v["correct"] for v in interprétéd)
    cumulative_wrong = sum(v["wrong"] for v in interprétéd)
    cumulative_missing = sum(v["missing"] for v in interprétéd)
    cumulative_placed = sum(v["placed"] for v in interprétéd)

    global_accuracy = ratio_pct(cumulative_correct, evaluated_positions)
    global_séquence_accuracy = ratio_pct(sum(v["séquence_correct"] for v in interprétéd), evaluated_positions)
    final = interprétéd[-1]
    best = max(interprétéd, key=lambda v: v["accuracy"])
    worst = min(interprétéd, key=lambda v: v["accuracy"])

    premature = sum(1 for v in interprétéd if "prématurée" in v["type"])
    partial = sum(1 for v in interprétéd if "partielle" in v["type"])
    complete_incorrect = sum(1 for v in interprétéd if v["type"] == "Validation complète incorrecte")
    complete_correct = sum(1 for v in interprétéd if "correcte" in v["type"] and v["placed"] >= v["total"])

    return {
        "validations": interprétéd,
        "count": len(interprétéd),
        "evaluated_positions": evaluated_positions,
        "cumulative_correct": cumulative_correct,
        "cumulative_wrong": cumulative_wrong,
        "cumulative_missing": cumulative_missing,
        "cumulative_placed": cumulative_placed,
        "global_accuracy": global_accuracy,
        "global_séquence_accuracy": global_séquence_accuracy,
        "final": final,
        "best": best,
        "worst": worst,
        "premature": premature,
        "partial": partial,
        "complete_incorrect": complete_incorrect,
        "complete_correct": complete_correct,
    }


def setup_styles():
    styles = getSampleStyleSheet()

    # Style general : texte justifie, sans italique.
    styles["Normal"].fontName = "Helvetica"
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 12
    styles["Normal"].alignment = TA_JUSTIFY
    styles["Normal"].spaceAfter = 5

    # Titres droits, proches de l'ancienne version du rapport.
    styles["Title"].fontName = "Helvetica-Bold"
    styles["Title"].fontSize = 18
    styles["Title"].leading = 22
    styles["Title"].alignment = TA_CENTER
    styles["Title"].spaceAfter = 10

    styles["Heading2"].fontName = "Helvetica-Bold"
    styles["Heading2"].fontSize = 14
    styles["Heading2"].leading = 17
    styles["Heading2"].alignment = TA_LEFT
    styles["Heading2"].spaceBefore = 6
    styles["Heading2"].spaceAfter = 8

    styles["Heading3"].fontName = "Helvetica-Bold"
    styles["Heading3"].fontSize = 10.5
    styles["Heading3"].leading = 13
    styles["Heading3"].alignment = TA_LEFT
    styles["Heading3"].spaceBefore = 8
    styles["Heading3"].spaceAfter = 5

    styles.add(ParagraphStyle(
        name="Small",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.2,
        leading=10.5,
        alignment=TA_JUSTIFY,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Tiny",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=8.5,
        alignment=TA_CENTER,
        spaceAfter=0,
    ))
    styles.add(ParagraphStyle(
        name="Caption",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10.2,
        alignment=TA_JUSTIFY,
        textColor=colors.HexColor("#555555"),
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="Box",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        alignment=TA_JUSTIFY,
        backColor=colors.HexColor("#F4F6F7"),
        borderColor=colors.HexColor("#D5D8DC"),
        borderWidth=0.5,
        borderPadding=7,
        spaceBefore=4,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="CenteredTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    ))
    return styles


def styled_table(data, header_color="#D6EAF8", text_color="#1B4F72", font_size=8, col_widths=None):
    table = Table(data, repeatRows=1, colWidths=col_widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(text_color)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def add_cover_page(story, styles, full_patient_name, patient_birthdate, therapist_name, session_date):
    logo_app_path = os.path.join("frontend", "assets", "Logo-APP.png")
    logo_enp_path = os.path.join("frontend", "assets", "Logo-ENP.png")

    left_logo = Image(logo_app_path, width=3 * cm, height=3 * cm) if os.path.exists(logo_app_path) else Paragraph("PhoeniXR", styles["Heading2"])
    right_logo = Image(logo_enp_path, width=3 * cm, height=3 * cm) if os.path.exists(logo_enp_path) else Paragraph("ENP", styles["Heading2"])

    header_table = Table([[left_logo, "", right_logo]], colWidths=[4 * cm, 9 * cm, 4 * cm])
    header_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    story.append(header_table)
    story.append(Spacer(1, 18))
    story.append(Paragraph("RAPPORT CLINIQUE", styles["Title"]))
    story.append(Paragraph("Assembly Stacking", styles["Heading2"]))
    story.append(Paragraph("Rééducation fonctionnelle du membre supérieur", styles["Heading3"]))
    story.append(Spacer(1, 30))

    cover_data = [
        ["Patient", full_patient_name],
        ["Date de naissance", patient_birthdate],
        ["Therapeute", therapist_name],
        ["Date de session", session_date],
    ]
    cover_table = Table(cover_data, colWidths=[5 * cm, 10 * cm])
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


def add_game_presentation(story, styles, game_description=None, game_images=None):
    game_description = game_description or DEFAULT_GAME_DESCRIPTION
    game_images = game_images if game_images is not None else DEFAULT_GAME_IMAGE_PATHS
    existing = [path for path in game_images[:4] if os.path.exists(path)]

    story.append(Paragraph("Présentation du jeu", styles["Heading2"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(game_description, styles["Normal"]))

    if existing:
        story.append(Spacer(1, 12))
        story.append(Paragraph("Illustrations de l'exercice", styles["Heading3"]))
        rows = []
        cells = [Image(path, width=7.2 * cm, height=4.2 * cm) for path in existing]
        for i in range(0, len(cells), 2):
            rows.append([cells[i], cells[i + 1] if i + 1 < len(cells) else ""])
        image_table = Table(rows, colWidths=[7.6 * cm, 7.6 * cm])
        image_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(image_table)
    else:
        story.append(Spacer(1, 12))
        story.append(Paragraph("Les illustrations du jeu peuvent etre integrees automatiquement lorsque les captures sont disponibles dans le dossier assets.", styles["Caption"]))

    story.append(PageBreak())


def ensure_graph_dir(output_dir):
    graph_dir = os.path.join(output_dir, GRAPH_DIR)
    os.makedirs(graph_dir, exist_ok=True)
    return graph_dir


def save_validation_progress_chart(validations, output_dir):
    graph_dir = ensure_graph_dir(output_dir)
    path = os.path.join(graph_dir, "validation_progress.png")
    labels = [f"Essai {v['attempt']}" for v in validations]
    values = [v["accuracy"] for v in validations]

    plt.figure(figsize=(8, 4.2))
    bars = plt.bar(labels, values)
    if bars:
        bars[-1].set_alpha(1.0)
        for b in bars[:-1]:
            b.set_alpha(0.45)
    plt.ylim(0, 105)
    plt.ylabel("Précision (%)")
    plt.title("Progression des validations", fontsize=13, fontweight="bold")
    plt.grid(axis="y", linestyle="--", alpha=0.35)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()
    return path



def validation_cell_status(expected_order, placed_order, rank_index):
    """Return 1 for correct, 0 for incorrect, -1 for missing."""
    if rank_index >= len(expected_order):
        return -1
    if rank_index >= len(placed_order):
        return -1
    return 1 if placed_order[rank_index] == expected_order[rank_index] else 0


def save_validation_conformity_map(data, validations, output_dir):
    """Create a compact heatmap showing where errors occur in each validation."""
    graph_dir = ensure_graph_dir(output_dir)
    path = os.path.join(graph_dir, "validation_conformity_map.png")
    expected_order = data.get("expectedOrder", []) or []
    total_pieces = safe_int(data.get("totalPieces", len(expected_order))) or len(expected_order)
    total_ranks = max(total_pieces, len(expected_order), 1)

    matrix = []
    row_labels = []
    for v in validations:
        placed_order = v.get("placed_order", []) or []
        row = []
        for rank in range(total_ranks):
            row.append(validation_cell_status(expected_order, placed_order, rank))
        matrix.append(row)
        row_labels.append(f"Essai {v.get('attempt', '')}")

    if not matrix:
        matrix = [[-1] * total_ranks]
        row_labels = ["Aucun essai"]

    fig_height = max(2.6, 0.55 * len(matrix) + 1.7)
    plt.figure(figsize=(8.4, fig_height))
    cmap = ListedColormap(["#C7CCD1", "#E57373", "#81C784"])
    norm = BoundaryNorm([-1.5, -0.5, 0.5, 1.5], cmap.N)
    plt.imshow(matrix, cmap=cmap, norm=norm, aspect="auto")

    plt.xticks(range(total_ranks), [str(i + 1) for i in range(total_ranks)], fontsize=8)
    plt.yticks(range(len(row_labels)), row_labels, fontsize=8)
    plt.xlabel("Rang dans la séquence")
    plt.title("Carte de conformité des validations", fontsize=12, fontweight="bold")

    # Draw grid lines for readability
    ax = plt.gca()
    ax.set_xticks([x - 0.5 for x in range(1, total_ranks)], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(row_labels))], minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.0)
    ax.tick_params(which="minor", bottom=False, left=False)

    legend_items = [
        mpatches.Patch(color="#81C784", label="Conforme"),
        mpatches.Patch(color="#E57373", label="Non conforme"),
        mpatches.Patch(color="#C7CCD1", label="Non placé"),
    ]
    plt.legend(handles=legend_items, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, fontsize=8, frameon=False)
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches="tight")
    plt.close()
    return path


def save_motor_engagement_chart(data, output_dir):
    graph_dir = ensure_graph_dir(output_dir)
    path = os.path.join(graph_dir, "motor_engagement.png")
    labels = ["Côté thérapeutique", "Côté opposé / libre"]
    values = [pct(data.get("therapeuticSideRatio", 0)), pct(data.get("oppositeSideRatio", 0))]
    plt.figure(figsize=(7.5, 4.0))
    plt.bar(labels, values)
    plt.ylim(0, 100)
    plt.ylabel("Ratio (%)")
    plt.title("Répartition de l'engagement moteur", fontsize=13, fontweight="bold")
    plt.grid(axis="y", linestyle="--", alpha=0.35)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()
    return path


def build_summary_text(vm, data):
    final = vm["final"]
    if vm["global_accuracy"] >= 90:
        perf = "La performance sur l'ensemble des validations est elevee."
    elif vm["global_accuracy"] >= 70:
        perf = "La performance globale est correcte, avec une progression visible au cours de la session."
    else:
        perf = "La performance globale reste fragile et doit etre relue avec l'historique des validations."

    if final["is_correct"]:
        final_txt = "La derniere validation est correcte, ce qui indique que le patient finit par reproduire le modèle attendu."
    else:
        final_txt = "La derniere validation n'est pas correcte ; le niveau doit etre consolide avant d'augmenter la difficulté."

    return f"{perf} {final_txt} Le score global de session tient compte de toutes les validations enregistrées, et non uniquement de la validation finale."


def plural_fr(n, singular, plural=None):
    if plural is None:
        plural = singular + "s"
    return singular if safe_int(n) in (0, 1) else plural


def first_exploitable_validation(validations):
    for v in validations:
        if v.get("placed", 0) > 0:
            return v
    return validations[0] if validations else None


def accuracy_level_sentence(value, label="La précision globale"):
    value = safe_float(value)
    if value >= 90:
        return f"{label} est élevée ({value}%)."
    if value >= 70:
        return f"{label} est correcte mais perfectible ({value}%)."
    if value >= 50:
        return f"{label} est modérée ({value}%) et nécessite une consolidation."
    return f"{label} est faible ({value}%) et indique une tâche encore difficile."


def performance_variation(validations):
    if not validations:
        return 0
    values = [safe_float(v.get("accuracy", 0)) for v in validations]
    return round(max(values) - min(values), 1)


def build_results_interpretation(vm, data):
    final = vm["final"]
    validations = vm["validations"]
    first = first_exploitable_validation(validations)
    gap = round(final["accuracy"] - vm["global_accuracy"], 1)
    progression = round(final["accuracy"] - first["accuracy"], 1) if first else 0
    variation = performance_variation(validations)

    parts = []
    parts.append(
        f"La précision globale de session est de {vm['global_accuracy']}%, calculée sur l'ensemble des validations. "
        f"La précision finale est de {final['accuracy']}%."
    )

    if final["is_correct"] and gap >= 10:
        parts.append(
            "Le score final est supérieur au score global : le patient parvient à corriger l'assemblage au cours de la session, mais la performance n'est pas encore totalement stable d'un essai à l'autre."
        )
    elif final["is_correct"] and vm["global_accuracy"] >= 90:
        parts.append(
            "Le score global et le score final sont tous deux élevés, ce qui indique une performance stable et une bonne maîtrise de la tâche."
        )
    elif not final["is_correct"]:
        parts.append(
            "La validation finale reste non conforme au modèle attendu ; la tâche doit être consolidée avant d'augmenter la difficulté."
        )
    else:
        parts.append(
            "La validation finale est correcte, mais le score global invite à poursuivre le travail de stabilisation avant de complexifier l'exercice."
        )

    if progression > 10:
        parts.append(f"La progression entre la première validation exploitable et la validation finale est positive (+{progression} points).")
    elif progression < -10:
        parts.append(f"La performance diminue entre la première validation exploitable et la validation finale ({progression} points), ce qui peut évoquer une fatigue, une perte d'attention ou une stratégie moins efficace.")
    else:
        parts.append("La performance reste globalement proche entre la première validation exploitable et la validation finale.")

    if variation >= 30:
        parts.append(f"L'amplitude des scores entre validations est importante ({variation} points), ce qui traduit une performance fluctuante.")
    elif variation >= 15:
        parts.append(f"L'amplitude des scores est modérée ({variation} points), suggérant quelques variations de précision au cours de la session.")
    else:
        parts.append(f"L'amplitude des scores est faible ({variation} points), ce qui suggère une performance relativement stable.")

    return parts


def build_validation_interpretation(vm):
    validations = vm["validations"]
    final = vm["final"]
    count = vm["count"]
    parts = []

    parts.append(
        f"La session comporte {count} {plural_fr(count, 'validation')}. "
        f"Parmi elles : {vm['premature']} {plural_fr(vm['premature'], 'validation prématurée')}, "
        f"{vm['partial']} {plural_fr(vm['partial'], 'validation partielle')} et "
        f"{vm['complete_incorrect']} {plural_fr(vm['complete_incorrect'], 'validation complète incorrecte')}."
    )

    if vm["partial"] > 0:
        parts.append("Les validations partielles signalent des validations réalisées avant la fin de l'assemblage ; elles peuvent refléter une vérification intermédiaire, une hésitation ou une consigne de fin d'exercice à clarifier.")
    if vm["complete_incorrect"] > 0:
        parts.append("Les validations complètes incorrectes montrent que l'ensemble des pièces a été placé, mais que la séquence ou certaines positions devaient encore être corrigées.")
    if vm["premature"] > 0:
        parts.append("Les validations prématurées doivent être distinguées de la performance motrice principale, surtout lorsqu'aucune pièce n'était placée.")

    if final["is_correct"]:
        parts.append(f"La validation finale est correcte avec une précision de {final['accuracy']}%. Le patient atteint donc le modèle attendu en fin de session.")
    else:
        parts.append(f"La validation finale n'est pas correcte ; la précision finale est de {final['accuracy']}%. Le niveau reste à consolider.")

    if vm["count"] > 2 and final["is_correct"] and vm["global_accuracy"] < final["accuracy"]:
        parts.append("Le nombre de validations nécessaires avant la réussite finale constitue un indicateur important à suivre lors des prochaines séances.")

    return parts



def rank_zone(rank, total):
    if total <= 0:
        return "la séquence"
    if rank <= math.ceil(total / 3):
        return "le début de la séquence"
    if rank <= math.ceil(2 * total / 3):
        return "le milieu de la séquence"
    return "la fin de la séquence"


def final_sequence_errors(expected_order, placed_order):
    errors = []
    total = len(expected_order)
    for i in range(total):
        expected = expected_order[i]
        placed = placed_order[i] if i < len(placed_order) else None
        if placed != expected:
            errors.append({
                "rank": i + 1,
                "expected": expected,
                "placed": placed,
                "status": "manquante" if placed is None else "incorrecte",
            })
    return errors


def recurrent_error_ranks(validations, expected_order):
    """Counts rank errors across non-premature validations."""
    total = len(expected_order)
    counts = [0] * total
    considered = 0
    for v in validations:
        placed_order = v.get("placed_order", []) or []
        if len(placed_order) == 0:
            continue
        considered += 1
        for i in range(total):
            if i >= len(placed_order) or placed_order[i] != expected_order[i]:
                counts[i] += 1
    if considered == 0:
        return []
    ranked = [(i + 1, c) for i, c in enumerate(counts) if c > 0]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def build_error_explanation(vm, data):
    expected_order = data.get("expectedOrder", []) or []
    final_order = data.get("placedOrder", []) or (vm["final"].get("placed_order", []) or [])
    errors = final_sequence_errors(expected_order, final_order)
    total = len(expected_order)
    parts = []

    if not expected_order:
        return ["L'ordre attendu n'est pas disponible dans le fichier JSON ; l'analyse détaillée des erreurs de séquence ne peut pas être réalisée."]

    if len(errors) == 0:
        parts.append("La séquence finale correspond entièrement au modèle attendu : aucune erreur de rang n'est détectée dans l'assemblage final.")
    else:
        first = errors[0]
        zone = rank_zone(first["rank"], total)
        placed_text = "aucune pièce placée" if first["placed"] is None else f"Pièce {first['placed']}"
        parts.append(
            f"L'assemblage final contient {len(errors)} erreur(s) de séquence sur {total} rangs. "
            f"La première erreur apparaît au rang {first['rank']} ({zone}) : la pièce attendue était Pièce {first['expected']}, alors que la pièce placée est {placed_text}."
        )

        error_ranks = ", ".join(str(e["rank"]) for e in errors[:6])
        if len(errors) > 6:
            error_ranks += ", ..."
        parts.append(
            f"Les rangs concernés par les erreurs finales sont : {error_ranks}. Cette information aide à localiser la partie de la séquence où la conformité au modèle diminue."
        )

    recurring = recurrent_error_ranks(vm["validations"], expected_order)
    if recurring:
        max_count = recurring[0][1]
        most_common = [str(rank) for rank, count in recurring if count == max_count]
        parts.append(
            f"Sur l'ensemble des validations exploitables, les rangs les plus souvent problématiques sont : {', '.join(most_common)}. "
            "La carte de conformité permet de visualiser si ces erreurs disparaissent, persistent ou se déplacent entre les essais."
        )
    else:
        parts.append("Les validations exploitables ne montrent pas de rang d'erreur récurrent." )

    return parts


def build_final_clinical_points(vm, data):
    parts = []
    final = vm["final"]
    variation = performance_variation(vm["validations"])
    parts.append(
        f"La précision globale de session est de {vm['global_accuracy']}%, tandis que la précision finale est de {final['accuracy']}%. "
        "Le score global reflète l'ensemble du déroulement de la session ; le score final décrit l'état de l'assemblage lors de la dernière validation."
    )
    if final["is_correct"]:
        if vm["global_accuracy"] >= 90 and variation < 15:
            parts.append("La session présente une performance globalement stable et une validation finale conforme.")
        else:
            parts.append("La validation finale est conforme, mais les validations précédentes montrent que la réussite a nécessité des ajustements ou des corrections intermédiaires.")
    else:
        parts.append("La validation finale n'est pas conforme au modèle attendu ; l'analyse des rangs d'erreur permet de préciser où la séquence se dégrade.")

    if vm["premature"] > 0:
        parts.append("Les validations prématurées sont conservées dans l'historique, mais elles doivent être séparées de l'évaluation de précision motrice lorsqu'aucune pièce n'était placée.")
    if vm["partial"] > 0:
        parts.append("Les validations partielles signalent des essais validés avant la complétion de la pile et peuvent renseigner sur la compréhension de la consigne ou la stratégie de contrôle.")
    if vm["complete_incorrect"] > 0:
        parts.append("Les validations complètes incorrectes montrent que la difficulté porte davantage sur l'ordre ou la conformité des positions que sur la capacité à placer toutes les pièces.")

    return parts


def build_dynamic_recommendations(vm):
    final = vm["final"]
    variation = performance_variation(vm["validations"])
    recs = []

    if final["is_correct"] and vm["global_accuracy"] >= 90 and variation < 15 and vm["count"] <= 2:
        recs.extend([
            "Augmenter progressivement la difficulté si la performance reste stable sur plusieurs sessions.",
            "Introduire un modèle plus long, des orientations plus variées ou une contrainte temporelle légère.",
            "Vérifier que la précision reste élevée dès les premières validations.",
        ])
    elif final["is_correct"] and vm["global_accuracy"] >= 70:
        recs.extend([
            "Maintenir le niveau actuel afin de stabiliser la précision globale avant d'augmenter la difficulté.",
            "Travailler la vérification de l'ordre des pièces avant validation pour réduire les essais intermédiaires.",
            "Suivre le nombre de validations nécessaires : l'objectif est d'obtenir une réussite finale avec moins d'essais.",
        ])
    elif final["is_correct"]:
        recs.extend([
            "Conserver un niveau de difficulté similaire et renforcer le feedback pendant la tâche.",
            "Fractionner la consigne ou guider davantage la vérification de la séquence.",
            "Attendre une amélioration de la précision globale avant de complexifier l'exercice.",
        ])
    else:
        recs.extend([
            "Simplifier temporairement la tâche : réduire le nombre de pièces ou la complexité du modèle.",
            "Renforcer le guidage visuel et le feedback avant la validation.",
            "Répéter le même niveau jusqu'à stabilisation de la précision globale et amélioration de la validation finale.",
        ])

    if vm["partial"] > 0:
        recs.append("Clarifier la consigne de validation : le bouton doit être utilisé lorsque l'assemblage est terminé, sauf consigne contraire du thérapeute.")
    if vm["complete_incorrect"] > 0:
        recs.append("Ajouter une étape de contrôle visuel avant validation afin d'aider le patient à repérer les erreurs de séquence ou de position.")
    if variation >= 30:
        recs.append("Surveiller la stabilité attentionnelle, car les scores varient fortement entre les validations.")

    # Deduplicate while preserving order and keep concise
    unique = []
    for r in recs:
        if r not in unique:
            unique.append(r)
    return unique[:6]


def build_dynamic_conclusion(vm, data):
    final = vm["final"]
    variation = performance_variation(vm["validations"])

    if final["is_correct"] and vm["global_accuracy"] >= 90 and variation < 15:
        main = "La session indique une bonne maîtrise de l'assemblage, avec une précision globale élevée et une validation finale correcte."
    elif final["is_correct"]:
        main = "La session se termine par une validation finale correcte, mais la précision globale montre que la réussite a nécessité des ajustements au cours de l'exercice."
    else:
        main = "La session ne se termine pas par une validation conforme ; la tâche reste à consolider avant progression."

    details = (
        f"La précision globale est de {vm['global_accuracy']}% sur {vm['count']} {plural_fr(vm['count'], 'validation')}, "
        f"tandis que la précision finale est de {final['accuracy']}%. "
    )

    if vm["complete_incorrect"] > 0 or vm["partial"] > 0:
        details += "Les validations intermédiaires apportent une information clinique utile sur les corrections, hésitations ou contrôles réalisés avant le résultat final."
    else:
        details += "L'historique ne montre pas de difficulté majeure entre les validations enregistrées."

    return main + " " + details


def generate_assembly_stacking_pdf(json_file, patient_info=None, output_dir=".", game_description=None, game_images=None):
    if patient_info is None:
        patient_info = {}
    os.makedirs(output_dir, exist_ok=True)

    if not isinstance(json_file, str):
        if hasattr(json_file, "name"):
            json_path = json_file.name
        else:
            raise ValueError("Format de fichier JSON non reconnu.")
    else:
        json_path = json_file

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    styles = setup_styles()

    first_name = patient_info.get("firstname", "")
    last_name = patient_info.get("lastname", "")
    full_patient_name = f"{first_name} {last_name}".strip() or data.get("patientName", "Non renseigne")
    patient_birthdate = parse_birthdate(patient_info.get("birthdate", "")) or "Non renseignee"
    therapist_name = patient_info.get("therapist", "") or "Non renseigne"
    session_date = parse_date(data.get("startTime", data.get("sessionDate", "")))

    clean_patient = clean_filename(full_patient_name)
    pdf_name = os.path.join(output_dir, f"rapport_clinique_assembly_stacking_v13_{clean_patient}.pdf")

    vm = validation_metrics(data)
    validations = vm["validations"]
    final = vm["final"]
    total_pieces = safe_int(data.get("totalPieces", final["total"]))
    placed_details = data.get("placedPieceDetails", []) or []
    expected_order = data.get("expectedOrder", []) or []
    final_placed_order = data.get("placedOrder", []) or final.get("placedOrder", []) or []
    final_seq_correct, final_seq_total, final_seq_accuracy = order_match_score(expected_order, final_placed_order)

    doc = SimpleDocTemplate(
        pdf_name,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
    )
    story = []

    # Page 1 - cover
    add_cover_page(story, styles, full_patient_name, patient_birthdate, therapist_name, session_date)

    # Page 2 - game presentation
    add_game_presentation(story, styles, game_description, game_images)

    # Page 3 - concise clinical summary
    story.append(Paragraph("Synthèse clinique", styles["Heading2"]))
    story.append(Paragraph(
        "Le score global de session est calculé sur l'ensemble des validations enregistrées. La validation finale est détaillée séparément afin de présenter l'état final de l'assemblage.",
        styles["Box"],
    ))
    story.append(Spacer(1, 10))

    overview = [
        ["Exercice", "Main", "Durée", "Validations", "Précision globale", "Résultat final"],
        [
            data.get("exerciseName", "Assembly Stacking"),
            format_hand(data.get("selectedHand", "")),
            seconds_to_min_sec(data.get("durationSeconds", 0)),
            vm["count"],
            f"{vm['global_accuracy']}%",
            p(format_result(data.get("result", "")), styles["Tiny"]),
        ],
    ]
    story.append(Paragraph("Tableau 1 - Vue d'ensemble de la session", styles["Heading3"]))
    story.append(styled_table(overview, font_size=7.4, col_widths=[2.8*cm, 2.2*cm, 2.0*cm, 1.8*cm, 2.6*cm, 4.3*cm]))
    story.append(Spacer(1, 8))

    validation_balance = [
        ["Positions évaluées", "Correctes cumulées", "Erreurs cumulées", "Manquantes cumulées", "Meilleure validation", "Validation finale"],
        [
            vm["evaluated_positions"],
            f"{vm['cumulative_correct']} / {vm['evaluated_positions']}",
            vm["cumulative_wrong"],
            vm["cumulative_missing"],
            f"Essai {vm['best']['attempt']} - {vm['best']['accuracy']}%",
            f"Essai {final['attempt']} - {final['accuracy']}%",
        ],
    ]
    story.append(Paragraph("Tableau 2 - Bilan cumulé des validations", styles["Heading3"]))
    story.append(styled_table(validation_balance, header_color="#D5F5E3", text_color="#145A32", font_size=7.5,
                              col_widths=[2.8*cm, 2.9*cm, 2.5*cm, 2.8*cm, 3.0*cm, 3.0*cm]))
    story.append(Spacer(1, 8))

    final_table = [
        [
            p("Pièces finales", styles["Tiny"]),
            p("Positions finales<br/>correctes", styles["Tiny"]),
            p("Positions finales<br/>fausses", styles["Tiny"]),
            p("Séquence finale", styles["Tiny"]),
            p("Temps moyen<br/>par pièce", styles["Tiny"]),
            p("Annulations", styles["Tiny"]),
        ],
        [
            f"{safe_int(data.get('placedPieces', 0))} / {total_pieces}",
            f"{safe_int(data.get('correctPositions', 0))} / {total_pieces}",
            safe_int(data.get("wrongPositions", 0)),
            f"{final_seq_accuracy}%",
            f"{seconds_per_piece(data.get('durationSeconds', 0), max(total_pieces, 1))} s",
            safe_int(data.get("undoCount", 0)),
        ],
    ]
    story.append(Paragraph("Tableau 3 - Résultat final", styles["Heading3"]))
    story.append(styled_table(final_table, header_color="#EBDEF0", text_color="#512E5F", font_size=7.5,
                              col_widths=[2.5*cm, 3.3*cm, 3.1*cm, 2.4*cm, 3.0*cm, 2.2*cm]))
    story.append(Spacer(1, 8))

    motor_table = [
        ["Pièces côté thérapeutique", "Ratio thérapeutique", "Pièces côté opposé", "Ratio opposé"],
        [
            safe_int(data.get("therapeuticSidePieceCount", 0)),
            f"{pct(data.get('therapeuticSideRatio', 0))}%",
            safe_int(data.get("oppositeSidePieceCount", 0)),
            f"{pct(data.get('oppositeSideRatio', 0))}%",
        ],
    ]
    story.append(Paragraph("Tableau 4 - Engagement moteur", styles["Heading3"]))
    story.append(styled_table(motor_table, header_color="#FADBD8", text_color="#922B21", font_size=8,
                              col_widths=[4.0*cm, 3.5*cm, 4.0*cm, 3.5*cm]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Interprétation clinique des résultats", styles["Heading3"]))
    for sentence in build_results_interpretation(vm, data):
        story.append(Paragraph(f"- {sentence}", styles["Normal"]))
        story.append(Spacer(1, 4))
    story.append(PageBreak())

    # Page 4 - validations interprétéd
    story.append(Paragraph("Analyse des validations", styles["Heading2"]))
    story.append(Paragraph(
        "Cette page presente toutes les validations de la session. Elle permet d'observer la progression, les essais intermédiaires et la validation finale sans réduire le score au dernier essai uniquement.",
        styles["Normal"],
    ))
    story.append(Spacer(1, 10))

    validation_rows = [["Essai", "Type", "Pièces", "Correctes", "Fausses", "Manquantes", "Précision"]]
    for v in validations:
        validation_rows.append([
            v["attempt"],
            p(v["type"], styles["Tiny"]),
            f"{v['placed']} / {v['total']}",
            f"{v['correct']} / {v['total']}",
            v["wrong"],
            v["missing"],
            f"{v['accuracy']}%",
        ])
    story.append(styled_table(validation_rows, font_size=7,
                              col_widths=[1.4*cm, 4.2*cm, 2.0*cm, 2.2*cm, 1.8*cm, 2.1*cm, 2.2*cm]))
    story.append(Spacer(1, 10))

    val_chart = save_validation_progress_chart(validations, output_dir)
    story.append(Paragraph("Figure 1 - Progression des validations", styles["Heading3"]))
    story.append(Image(val_chart, width=15.2 * cm, height=5.3 * cm))
    story.append(Spacer(1, 6))

    conformity_map = save_validation_conformity_map(data, validations, output_dir)
    story.append(Paragraph("Figure 2 - Carte de conformité des validations", styles["Heading3"]))
    story.append(Paragraph(
        "Cette carte compare, pour chaque validation, la pièce placée à chaque rang avec la pièce attendue. Elle permet de localiser les erreurs sans ajouter un tableau supplémentaire.",
        styles["Caption"],
    ))
    story.append(Image(conformity_map, width=15.2 * cm, height=5.2 * cm))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Interprétation clinique des validations", styles["Heading3"]))
    for sentence in build_validation_interpretation(vm):
        story.append(Paragraph(f"- {sentence}", styles["Normal"]))
        story.append(Spacer(1, 4))
    story.append(Spacer(1, 12))

    # Final assembly and motor engagement
    story.append(Paragraph("Analyse de l'assemblage final", styles["Heading2"]))
    story.append(Spacer(1, 8))

    piece_rows = [["Rang", "Pièce attendue", "Pièce finale", "Statut", "Côté sollicité", "Niveau"]]
    for i, detail in enumerate(placed_details):
        expected = detail.get("expectedPieceIndex", expected_order[i] if i < len(expected_order) else "")
        placed = detail.get("pieceIndex", "")
        status = "Conforme" if detail.get("isCorrectPosition", False) else "Non conforme"
        piece_rows.append([
            i + 1,
            f"Piece {expected}",
            f"Piece {placed}",
            status,
            p(side_label(detail.get("layerName", "")), styles["Tiny"]),
            height_level(i, len(placed_details)),
        ])
    story.append(styled_table(piece_rows, header_color="#D6EAF8", text_color="#1B4F72", font_size=7,
                              col_widths=[1.2*cm, 2.8*cm, 2.8*cm, 2.2*cm, 3.4*cm, 2.2*cm]))
    story.append(Spacer(1, 10))

    motor_chart = save_motor_engagement_chart(data, output_dir)
    story.append(Paragraph("Répartition de l'engagement moteur", styles["Heading3"]))
    story.append(Image(motor_chart, width=14.5 * cm, height=7.2 * cm))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"L'engagement moteur est réparti entre {pct(data.get('therapeuticSideRatio', 0))}% côté thérapeutique et {pct(data.get('oppositeSideRatio', 0))}% côté opposé ou libre.",
        styles["Box"],
    ))
    story.append(PageBreak())

    # Page 6 - Final clinical analysis
    story.append(Paragraph("Analyse clinique finale", styles["Heading2"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Lecture clinique des résultats", styles["Heading3"]))
    for sentence in build_final_clinical_points(vm, data):
        story.append(Paragraph(f"- {sentence}", styles["Normal"]))
        story.append(Spacer(1, 5))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Analyse des erreurs de séquence", styles["Heading3"]))
    for sentence in build_error_explanation(vm, data):
        story.append(Paragraph(f"- {sentence}", styles["Normal"]))
        story.append(Spacer(1, 5))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Conclusion clinique", styles["Heading3"]))
    story.append(Paragraph(build_dynamic_conclusion(vm, data), styles["Normal"]))

    story.append(Spacer(1, 14))
    story.append(Paragraph("Remarque méthodologique", styles["Heading3"]))
    story.append(Paragraph(
        "Ce rapport est généré à partir des données enregistrées pendant la session. Il constitue un support d'aide à l'analyse clinique et doit être interprété par le thérapeute selon le contexte du patient et les objectifs de rééducation.",
        styles["Caption"],
    ))

    doc.build(story)
    return pdf_name

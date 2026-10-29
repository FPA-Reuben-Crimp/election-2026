import csv
import html
import math
from datetime import date, timedelta
from pathlib import Path
from statistics import median


DATA_FILE = Path(__file__).with_name("polls.csv")
OUTPUT_FILE = Path(__file__).with_name("polls.svg")
COALITION_DATA_FILE = Path(__file__).with_name("coalition-polls.csv")
COALITION_OUTPUT_FILE = Path(__file__).with_name("coalition-trends.svg")

PARTIES = [
    ("NAT", "nat_pct", "#00529B"),
    ("LAB", "lab_pct", "#C8102E"),
    ("GRN", "green_pct", "#00843D"),
    ("ACT", "act_pct", "#B28A00"),
    ("NZF", "nz_first_pct", "#6D7075"),
    ("TPM", "te_pati_maori_pct", "#805B46"),
    ("OPP", "opportunity_pct", "#007F7B"),
    ("OTH", "others_pct", "#39424E"),
]

PARTY_LABEL_COLORS = {
    "NAT": PARTIES[0][2],
    "LAB": PARTIES[1][2],
    "GRN": PARTIES[2][2],
    "ACT": PARTIES[3][2],
    "NZF": PARTIES[4][2],
    "OPP": PARTIES[6][2],
}

SERIES = PARTIES

COALITIONS = [
    (
        "LAB + GRN + OPP",
        "lab_green_opportunity_pct",
        ("lab_pct", "green_pct", "opportunity_pct"),
        "#E69F00",
    ),
    (
        "LAB + GRN + NZF",
        "lab_green_nz_first_pct",
        ("lab_pct", "green_pct", "nz_first_pct"),
        "#009E73",
    ),
    (
        "LAB + GRN + OPP + NZF",
        "lab_green_opportunity_nz_first_pct",
        ("lab_pct", "green_pct", "opportunity_pct", "nz_first_pct"),
        "#D55E00",
    ),
    (
        "NAT + ACT + NZF",
        "nat_nz_first_act_pct",
        ("nat_pct", "act_pct", "nz_first_pct"),
        "#56B4E9",
    ),
    (
        "NAT + ACT + OPP",
        "nat_act_opportunity_pct",
        ("nat_pct", "act_pct", "opportunity_pct"),
        "#CC79A7",
    ),
    (
        "NAT + NZF + OPP",
        "nat_nz_first_opportunity_pct",
        ("nat_pct", "nz_first_pct", "opportunity_pct"),
        "#4D4D4D",
    ),
    (
        "NAT + ACT + NZF + OPP",
        "nat_act_nz_first_opportunity_pct",
        ("nat_pct", "act_pct", "nz_first_pct", "opportunity_pct"),
        "#332288",
    ),
]

KEY_DATES = [
    (date(2026, 10, 26), "Advance voting opens", "26 Oct, 9 am", "#C75B12"),
    (date(2026, 11, 7), "Voting closes", "7 Nov, 7 pm", "#C0266B"),
]
COALITION_START_DATE = date(2026, 1, 1)
COALITION_Y_MIN = 30
COALITION_Y_MAX = 65

WIDTH = 1280
HEIGHT = 760
LEFT = 108
TOP = 105
PLOT_WIDTH = 820
PLOT_HEIGHT = 500


def svg_text(x, y, text, size=14, color="#263238", anchor="start", extra=""):
    return (
        f'<text x="{x}" y="{y}" font-family="DejaVu Sans, sans-serif" '
        f'font-size="{size}" fill="{color}" text-anchor="{anchor}" {extra}>'
        f"{html.escape(str(text))}</text>"
    )


def svg_coalition_text(x, y, label, size=14, prefix=""):
    segments = [f'<tspan fill="#263238">{html.escape(prefix)}</tspan>']
    for index, party in enumerate(label.split(" + ")):
        if index:
            segments.append('<tspan fill="#263238"> + </tspan>')
        color = PARTY_LABEL_COLORS.get(party, "#263238")
        segments.append(f'<tspan fill="{color}">{html.escape(party)}</tspan>')
    return (
        f'<text x="{x}" y="{y}" font-family="DejaVu Sans, sans-serif" '
        f'font-size="{size}" text-anchor="start">{"".join(segments)}</text>'
    )


def date_ticks(first_year, last_year):
    ticks = []
    for year in range(first_year, last_year + 1):
        for month in (1, 7):
            ticks.append(date(year, month, 1))
    return ticks


def month_ticks(first_date, last_date):
    year = first_date.year
    month = first_date.month
    ticks = []
    while True:
        tick = date(year, month, 1)
        if tick > last_date:
            return ticks
        if tick >= first_date:
            ticks.append(tick)
        month += 1
        if month == 13:
            year += 1
            month = 1


def lowess(points, evaluation_points=None, fraction=0.35, robust_iterations=3):
    points = sorted(points)
    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]
    count = len(points)
    target_values = sorted(set(x_values).union(evaluation_points or ()))
    neighbor_count = max(2, min(count, math.ceil(fraction * count)))
    robust_weights = [1.0] * count
    fitted = [0.0] * len(target_values)

    for iteration in range(robust_iterations + 1):
        for index, target_x in enumerate(target_values):
            distances = [abs(value - target_x) for value in x_values]
            ordered_distances = sorted(distances)
            bandwidth = ordered_distances[neighbor_count - 1]
            if bandwidth == 0:
                bandwidth = next((value for value in ordered_distances if value > 0), 1.0)

            weighted = []
            for x_value, y_value, distance, robust_weight in zip(
                x_values, y_values, distances, robust_weights
            ):
                ratio = distance / bandwidth
                spatial_weight = (1 - ratio**3) ** 3 if ratio < 1 else 0.0
                weighted.append((x_value - target_x, y_value, spatial_weight * robust_weight))

            sum_weight = sum(weight for _, _, weight in weighted)
            sum_dx = sum(dx * weight for dx, _, weight in weighted)
            sum_dy = sum(y * weight for _, y, weight in weighted)
            sum_dx2 = sum(dx * dx * weight for dx, _, weight in weighted)
            sum_dxy = sum(dx * y * weight for dx, y, weight in weighted)
            determinant = sum_weight * sum_dx2 - sum_dx * sum_dx

            if sum_weight == 0:
                fitted[index] = y_values[index]
            elif abs(determinant) < 1e-12:
                fitted[index] = sum_dy / sum_weight
            else:
                fitted[index] = (sum_dy * sum_dx2 - sum_dx * sum_dxy) / determinant

        if iteration == robust_iterations:
            break

        fitted_by_x = dict(zip(target_values, fitted))
        residuals = [actual - fitted_by_x[x_value] for x_value, actual in zip(x_values, y_values)]
        scale = 6 * median(abs(residual) for residual in residuals)
        if scale == 0:
            robust_weights = [1.0] * count
        else:
            robust_weights = []
            for residual in residuals:
                ratio = abs(residual) / scale
                robust_weights.append((1 - ratio**2) ** 2 if ratio < 1 else 0.0)

    return list(zip(target_values, fitted))


def append_trend(parts, points, first_date, date_span, y_position, color):
    if len(points) < 2:
        return

    last_observed_day = max(day for day, _ in points)
    voting_day = (KEY_DATES[-1][0] - first_date).days
    trend_points = lowess(points, evaluation_points=[voting_day])
    supported_trend = [point for point in trend_points if point[0] <= last_observed_day]
    trend_tail = [supported_trend[-1]] + [
        point for point in trend_points if point[0] > last_observed_day
    ]

    def svg_points(trend):
        return " ".join(
            f"{LEFT + day / date_span * PLOT_WIDTH:.2f},"
            f"{y_position(max(COALITION_Y_MIN, min(COALITION_Y_MAX, value))):.2f}"
            for day, value in trend
        )

    parts.append(
        f'<polyline points="{svg_points(supported_trend)}" fill="none" stroke="{color}" '
        'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" '
        'stroke-opacity="0.92"/>'
    )
    parts.append(
        f'<polyline points="{svg_points(trend_tail)}" fill="none" stroke="{color}" '
        'stroke-width="2.5" stroke-dasharray="3 2" stroke-linejoin="round" '
        'stroke-linecap="round" stroke-opacity="0.92"/>'
    )


def render_coalition_chart(polls):
    all_polls = polls
    polls = [row for row in all_polls if row["plot_date"] >= COALITION_START_DATE]
    first_date = COALITION_START_DATE
    last_date = max(
        max(row["plot_date"] for row in polls), KEY_DATES[-1][0] + timedelta(days=14)
    )
    date_span = (last_date - first_date).days

    def x_position(day):
        return LEFT + (day - first_date).days / date_span * PLOT_WIDTH

    def y_position(value):
        return TOP + PLOT_HEIGHT - (value - COALITION_Y_MIN) / (
            COALITION_Y_MAX - COALITION_Y_MIN
        ) * PLOT_HEIGHT

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
        f'height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        svg_text(LEFT, 44, "Potential coalition party-vote trends", 28, "#17212B"),
        svg_text(
            LEFT,
            72,
            "Jan 2026 onward; named-party sums with solid LOWESS and dashed extensions to voting day.",
            15,
            "#5D6872",
        ),
    ]

    for value in range(COALITION_Y_MIN, COALITION_Y_MAX + 1, 5):
        y = y_position(value)
        parts.append(
            f'<line x1="{LEFT}" y1="{y:.1f}" '
            f'x2="{LEFT + PLOT_WIDTH}" y2="{y:.1f}" '
            'stroke="#DCE2E7" stroke-width="1"/>'
        )
        parts.append(svg_text(LEFT - 14, y + 5, f"{value}%", 13, "#59636E", "end"))

    for tick in month_ticks(first_date, last_date):
        x = x_position(tick)
        parts.append(
            f'<line x1="{x:.1f}" y1="{TOP}" '
            f'x2="{x:.1f}" y2="{TOP + PLOT_HEIGHT}" '
            'stroke="#EEF1F3" stroke-width="1"/>'
        )
        parts.append(
            svg_text(x, TOP + PLOT_HEIGHT + 25, tick.strftime("%b %Y"), 12, "#59636E", "middle")
        )

    parts.extend(
        [
            f'<line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" '
            f'y2="{TOP + PLOT_HEIGHT}" stroke="#59636E" stroke-width="1.5"/>',
            f'<line x1="{LEFT}" y1="{TOP + PLOT_HEIGHT}" '
            f'x2="{LEFT + PLOT_WIDTH}" y2="{TOP + PLOT_HEIGHT}" '
            'stroke="#59636E" stroke-width="1.5"/>',
            svg_text(
                28,
                TOP + PLOT_HEIGHT / 2,
                "Combined party vote",
                14,
                "#263238",
                "middle",
                'transform="rotate(-90 28 355)"',
            ),
        ]
    )

    for event_date, _, _, color in KEY_DATES:
        x = x_position(event_date)
        parts.append(
            f'<line x1="{x:.1f}" y1="{TOP}" '
            f'x2="{x:.1f}" y2="{TOP + PLOT_HEIGHT}" '
            f'stroke="{color}" stroke-width="2" stroke-dasharray="6 5"/>'
        )

    for label, column, _, color in COALITIONS:
        points = [
            ((row["plot_date"] - first_date).days, float(row[column]))
            for row in polls
            if row[column]
        ]
        append_trend(parts, points, first_date, date_span, y_position, color)

    point_count = 0
    for label, column, _, color in COALITIONS:
        for row in polls:
            if not row[column]:
                continue
            value = float(row[column])
            x = x_position(row["plot_date"])
            y = y_position(value)
            tooltip = html.escape(
                f"{row['date_label']} | {row['pollster']} | {label}: {value:g}%"
            )
            parts.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.1" '
                f'fill="{color}" fill-opacity="0.78" stroke="#FFFFFF" '
                f'stroke-width="0.4"><title>{tooltip}</title></circle>'
            )
            point_count += 1

    legend_x = LEFT + PLOT_WIDTH + 48
    latest_values = {}
    for label, column, _, _ in COALITIONS:
        available = [row for row in polls if row[column]]
        latest = max(available, key=lambda row: row["date_sort"])
        latest_values[column] = float(latest[column])
    ranked_coalitions = sorted(
        COALITIONS, key=lambda coalition: latest_values[coalition[1]], reverse=True
    )
    legend_order = (1, 4, 2, 3, 5, 6, 7)
    legend_group_gap = 16

    parts.append(svg_text(legend_x, TOP + 4, "LATEST OBSERVED POLL", 12, "#69737C"))
    for index, rank in enumerate(legend_order):
        label, column, _, color = ranked_coalitions[rank - 1]
        y = TOP + 36 + index * 34 + (legend_group_gap if index >= 4 else 0)
        parts.append(
            f'<circle cx="{legend_x + 7}" cy="{y - 5}" r="5" fill="{color}"/>'
        )
        parts.append(
            svg_coalition_text(legend_x + 22, y, label, 12, prefix=f"{rank}. ")
        )
        parts.append(
            svg_text(legend_x + 284, y, f"{latest_values[column]:.1f}%", 12, "#263238", "end")
        )

    key_dates_y = TOP + 36 + len(COALITIONS) * 34 + legend_group_gap + 12
    parts.append(svg_text(legend_x, key_dates_y, "KEY DATES", 12, "#69737C"))
    for index, (_, label, date_label, color) in enumerate(KEY_DATES):
        y = key_dates_y + 34 + index * 48
        parts.append(
            f'<line x1="{legend_x}" y1="{y - 5}" x2="{legend_x + 16}" '
            f'y2="{y - 5}" stroke="{color}" stroke-width="2" '
            'stroke-dasharray="6 5"/>'
        )
        parts.append(svg_text(legend_x + 24, y, label, 13, "#263238"))
        parts.append(svg_text(legend_x + 24, y + 17, date_label, 12, "#69737C"))

    parts.append(
        svg_text(
            LEFT,
            HEIGHT - 25,
            "Party-vote sums are not seat projections; polls missing a component are omitted.",
            12,
            "#69737C",
        )
    )
    parts.append("</svg>")
    COALITION_OUTPUT_FILE.write_text("\n".join(parts) + "\n", encoding="utf-8")

    columns = ["date_sort", "date_label", "pollster"] + [column for _, column, _, _ in COALITIONS]
    with COALITION_DATA_FILE.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=columns)
        writer.writeheader()
        writer.writerows(
            {column: row.get(column, "") for column in columns} for row in all_polls
        )

    print(f"Wrote {COALITION_OUTPUT_FILE.name}: {len(COALITIONS)} arrangements, {point_count} points")


def main():
    with DATA_FILE.open(newline="", encoding="utf-8") as source:
        polls = [
            row
            for row in csv.DictReader(source)
            if row["record_type"] == "poll"
        ]

    if not polls:
        raise ValueError("No poll records found in polls.csv")

    for row in polls:
        row["plot_date"] = date.fromisoformat(row["date_sort"])
        for _, result, components, _ in COALITIONS:
            values = [row.get(component, "").strip() for component in components]
            row[result] = f"{sum(map(float, values)):.2f}" if all(values) else ""

    first_date = min(row["plot_date"] for row in polls)
    last_date = max(
        max(row["plot_date"] for row in polls), KEY_DATES[-1][0] + timedelta(days=14)
    )
    y_max = math.ceil(
        max(float(row[column]) for row in polls for _, column, _ in SERIES if row[column].strip())
        / 10
    ) * 10
    date_span = (last_date - first_date).days
    if date_span <= 0:
        raise ValueError("Poll records need at least two distinct dates")

    def x_position(day):
        return LEFT + (day - first_date).days / date_span * PLOT_WIDTH

    def y_position(value):
        return TOP + PLOT_HEIGHT - value / y_max * PLOT_HEIGHT

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
        f'height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        svg_text(LEFT, 44, "New Zealand party vote polling", 28, "#17212B"),
        svg_text(
            LEFT,
            72,
            "Raw polls and coalition approximations; solid LOWESS, dashed extensions to voting day.",
            15,
            "#5D6872",
        ),
    ]

    for value in range(0, y_max + 1, 10):
        y = y_position(value)
        parts.append(
            f'<line x1="{LEFT}" y1="{y:.1f}" '
            f'x2="{LEFT + PLOT_WIDTH}" y2="{y:.1f}" '
            'stroke="#DCE2E7" stroke-width="1"/>'
        )
        parts.append(svg_text(LEFT - 14, y + 5, f"{value}%", 13, "#59636E", "end"))

    for tick in date_ticks(first_date.year, last_date.year):
        if first_date <= tick <= last_date:
            x = x_position(tick)
            parts.append(
                f'<line x1="{x:.1f}" y1="{TOP}" '
                f'x2="{x:.1f}" y2="{TOP + PLOT_HEIGHT}" '
                'stroke="#EEF1F3" stroke-width="1"/>'
            )
            parts.append(
                svg_text(x, TOP + PLOT_HEIGHT + 25, tick.strftime("%b %Y"), 13, "#59636E", "middle")
            )

    parts.extend(
        [
            f'<line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" '
            f'y2="{TOP + PLOT_HEIGHT}" stroke="#59636E" stroke-width="1.5"/>',
            f'<line x1="{LEFT}" y1="{TOP + PLOT_HEIGHT}" '
            f'x2="{LEFT + PLOT_WIDTH}" y2="{TOP + PLOT_HEIGHT}" '
            'stroke="#59636E" stroke-width="1.5"/>',
            svg_text(
                28,
                TOP + PLOT_HEIGHT / 2,
                "Party vote",
                14,
                "#263238",
                "middle",
                'transform="rotate(-90 28 355)"',
            ),
        ]
    )

    for event_date, _, _, color in KEY_DATES:
        x = x_position(event_date)
        parts.append(
            f'<line x1="{x:.1f}" y1="{TOP}" '
            f'x2="{x:.1f}" y2="{TOP + PLOT_HEIGHT}" '
            f'stroke="{color}" stroke-width="2" stroke-dasharray="6 5"/>'
        )

    for label, column, color in SERIES:
        points = [
            ((row["plot_date"] - first_date).days, float(row[column]))
            for row in polls
            if row[column].strip()
        ]
        if len(points) < 2:
            continue
        last_observed_day = max(day for day, _ in points)
        voting_day = (KEY_DATES[-1][0] - first_date).days
        trend_points = lowess(points, evaluation_points=[voting_day])
        supported_trend = [point for point in trend_points if point[0] <= last_observed_day]
        trend_tail = [supported_trend[-1]] + [
            point for point in trend_points if point[0] > last_observed_day
        ]

        def svg_points(trend):
            return " ".join(
                f"{LEFT + day / date_span * PLOT_WIDTH:.2f},"
                f"{y_position(max(0, min(y_max, value))):.2f}"
                for day, value in trend
            )

        parts.append(
            f'<polyline points="{svg_points(supported_trend)}" fill="none" stroke="{color}" '
            'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" '
            'stroke-opacity="0.92"/>'
        )
        parts.append(
            f'<polyline points="{svg_points(trend_tail)}" fill="none" stroke="{color}" '
            'stroke-width="2.5" stroke-dasharray="3 2" stroke-linejoin="round" '
            'stroke-linecap="round" stroke-opacity="0.92"/>'
        )

    point_count = 0
    for label, column, color in SERIES:
        for row in polls:
            raw_value = row[column].strip()
            if not raw_value:
                continue
            value = float(raw_value)
            if not 0 <= value <= y_max:
                raise ValueError(f"Unexpected {label} value outside 0-{y_max}: {value}")
            x = x_position(row["plot_date"])
            y = y_position(value)
            tooltip = html.escape(
                f"{row['date_label']} | {row['pollster']} | {label}: {value:g}%"
            )
            parts.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.1" '
                f'fill="{color}" fill-opacity="0.78" stroke="#FFFFFF" '
                f'stroke-width="0.4"><title>{tooltip}</title></circle>'
            )
            point_count += 1

    legend_x = LEFT + PLOT_WIDTH + 48
    parts.append(svg_text(legend_x, TOP + 4, "PARTY POLLS", 12, "#69737C"))
    for index, (label, _, color) in enumerate(SERIES):
        y = TOP + 36 + index * 34
        parts.append(
            f'<circle cx="{legend_x + 7}" cy="{y - 5}" r="5" fill="{color}"/>'
        )
        parts.append(svg_text(legend_x + 22, y, label, 14, color))

    key_dates_y = TOP + 36 + len(SERIES) * 34 + 12
    parts.append(svg_text(legend_x, key_dates_y, "KEY DATES", 12, "#69737C"))
    for index, (_, label, date_label, color) in enumerate(KEY_DATES):
        y = key_dates_y + 34 + index * 48
        parts.append(
            f'<line x1="{legend_x}" y1="{y - 5}" x2="{legend_x + 16}" '
            f'y2="{y - 5}" stroke="{color}" stroke-width="2" '
            'stroke-dasharray="6 5"/>'
        )
        parts.append(svg_text(legend_x + 24, y, label, 13, "#263238"))
        parts.append(svg_text(legend_x + 24, y + 17, date_label, 12, "#69737C"))

    parts.append(
        svg_text(
            LEFT,
            HEIGHT - 25,
            "Source: Wikipedia opinion polling table, retrieved 29 Oct 2026.",
            12,
            "#69737C",
        )
    )
    parts.append("</svg>")

    OUTPUT_FILE.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE.name}: {len(polls)} polls, {point_count} points")
    render_coalition_chart(polls)


if __name__ == "__main__":
    main()
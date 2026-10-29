import csv
import html
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ELECTORATE_FILE = ROOT / "electorate-seat-projections.csv"
CONTESTABILITY_FILE = ROOT / "electorate-contestability.csv"
OUTPUT_FILE = ROOT / "electorate-forecast-matrix.svg"

PARTY_COLORS = {
    "National": "#00529B",
    "Labour": "#C8102E",
    "Green": "#00843D",
    "ACT": "#B28A00",
    "New Zealand First": "#6D7075",
    "Te Pati Maori": "#805B46",
    "Opportunity": "#007F7B",
    "Te Tai Tokerau": "#CC79A7",
    "Independent": "#39424E",
}
PARTY_LABELS = {
    "National": "NAT",
    "Labour": "LAB",
    "Green": "GRN",
    "ACT": "ACT",
    "New Zealand First": "NZF",
    "Te Pati Maori": "TPM",
    "Opportunity": "OPP",
    "Te Tai Tokerau": "TTT",
    "Independent": "IND",
}
METHOD_LABELS = {
    "2026_local_poll": "2026 local poll",
    "incumbent_hold": "Incumbent hold",
    "2023_same_name_winner": "2023 same-name winner",
    "manual_fallback": "Manual fallback",
}

WIDTH = 1800
LEFT = 28
RIGHT = 1770
ROW_HEIGHT = 22


def svg_text(x, y, value, size=12, color="#263238", anchor="start"):
    return (
        f'<text x="{x}" y="{y}" font-family="DejaVu Sans, sans-serif" '
        f'font-size="{size}" fill="{color}" text-anchor="{anchor}">'
        f"{html.escape(str(value))}</text>"
    )


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def normalize_electorate(value):
    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def load_matrix():
    forecasts = read_rows(ELECTORATE_FILE)
    polls = {
        normalize_electorate(row["electorate"]): row
        for row in read_rows(CONTESTABILITY_FILE)
    }
    for row in forecasts:
        row["poll"] = polls.get(normalize_electorate(row["electorate"]))

    groups = [
        (
            "2026 LOCAL POLLS",
            [row for row in forecasts if row["poll"]],
            lambda row: (
                float(row["poll"]["lead_pp"]),
                row["electorate"],
            ),
        ),
        (
            "NO LOCAL POLL · INCUMBENT HOLD",
            [
                row
                for row in forecasts
                if not row["poll"] and row["forecast_method"] == "incumbent_hold"
            ],
            lambda row: row["electorate"],
        ),
        (
            "NO LOCAL POLL · 2023 WINNER",
            [row for row in forecasts if row["forecast_method"] == "2023_same_name_winner"],
            lambda row: row["electorate"],
        ),
        (
            "NO LOCAL POLL · MANUAL FALLBACK",
            [row for row in forecasts if row["forecast_method"] == "manual_fallback"],
            lambda row: row["electorate"],
        ),
    ]
    for _, rows, key in groups:
        rows.sort(key=key)
    return forecasts, groups


def poll_summary(row):
    poll = row["poll"]
    if not poll:
        return "No local electorate poll in saved data"
    if poll["tied_parties"]:
        result = f"Tie: {poll['tied_parties']} {float(poll['leader_pct']):.1f}%"
    else:
        result = (
            f"{poll['leader_party']} {float(poll['leader_pct']):.1f}% over "
            f"{poll['runnerup_party']} {float(poll['runnerup_pct']):.1f}% "
            f"(+{float(poll['lead_pp']):.1f} pp)"
        )
    sample = f"n={poll['sample_n']}" if poll["sample_n"] else "sample n/a"
    return f"{poll['date_label']} · {poll['pollster']} · {result} · {sample}"


def render(forecasts, groups):
    row_count = sum(len(rows) for _, rows, _ in groups)
    height = 254 + row_count * ROW_HEIGHT + len(groups) * 28
    methods = Counter(row["forecast_method"] for row in forecasts)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        svg_text(LEFT, 44, "Electorate forecast: party and evidence", 27, "#17212B"),
        svg_text(
            LEFT,
            74,
            "One row per electorate. Poll margins show measured contestability; fallback rows are assumptions, not polling.",
            14,
            "#5D6872",
        ),
        svg_text(
            LEFT,
            101,
            "Forecast methods: "
            + " · ".join(
                f"{METHOD_LABELS[method]} {count}"
                for method, count in sorted(methods.items())
            ),
            12,
            "#4E5963",
        ),
        svg_text(LEFT, 130, "FORECAST PARTY", 10, "#69737C"),
    ]

    legend_x = 190
    for index, (party, color) in enumerate(PARTY_COLORS.items()):
        x = legend_x + index * 175
        parts.append(f'<circle cx="{x + 5}" cy="126" r="5" fill="{color}"/>')
        parts.append(svg_text(x + 16, 130, party, 11, "#4E5963"))

    for x, label in ((LEFT, "ELECTORATE"), (360, "MODEL PARTY"), (625, "LOCAL POLL SIGNAL"), (1420, "ASSIGNMENT BASIS")):
        parts.append(svg_text(x, 164, label, 10, "#69737C"))

    y = 191
    for heading, rows, _ in groups:
        parts.append(
            f'<line x1="{LEFT}" y1="{y + 5}" x2="{RIGHT}" y2="{y + 5}" '
            'stroke="#DCE2E7" stroke-width="1"/>'
        )
        parts.append(svg_text(LEFT, y, f"{heading} ({len(rows)})", 11, "#35424B"))
        y += 20

        for row in rows:
            y += ROW_HEIGHT
            party = row["predicted_party"]
            color = PARTY_COLORS.get(party, "#39424E")
            parts.append(svg_text(LEFT, y, row["electorate"], 12, "#263238"))
            parts.append(f'<circle cx="366" cy="{y - 4}" r="5" fill="{color}"/>')
            parts.append(
                svg_text(378, y, PARTY_LABELS.get(party, party), 11, "#263238")
            )
            parts.append(svg_text(625, y, poll_summary(row), 11, "#4E5963"))
            method = row["forecast_method"]
            if row["poll"] and method != "2026_local_poll":
                basis = "Poll tie; incumbent baseline"
            else:
                basis = METHOD_LABELS[method]
            parts.append(svg_text(1420, y, basis, 11, "#59636E"))

    parts.extend(
        [
            svg_text(
                LEFT,
                height - 43,
                "Latest local electorate poll shown where available; 55 electorates have no 2026 local poll in the saved source.",
                11,
                "#5D6872",
            ),
            svg_text(
                LEFT,
                height - 23,
                "Forecasts use current incumbent holds, same-name 2023 winners, or documented manual fallbacks for unpolled seats.",
                11,
                "#5D6872",
            ),
            "</svg>",
        ]
    )
    OUTPUT_FILE.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main():
    forecasts, groups = load_matrix()
    if len(forecasts) != 71:
        raise ValueError(f"Expected 71 electorates, found {len(forecasts)}")
    render(forecasts, groups)
    print(f"Wrote {OUTPUT_FILE.name}: {len(forecasts)} electorates")


if __name__ == "__main__":
    main()

import csv
import html
import math
from pathlib import Path

from mmp_projection import project_mmp


DATA_FILE = Path(__file__).with_name("polls.csv")
OUTPUT_FILE = Path(__file__).with_name("overhang-sensitivity.svg")
SUMMARY_FILE = Path(__file__).with_name("overhang-sensitivity.csv")

PARTIES = [
    ("National", "nat_pct", "#00529B"),
    ("Labour", "lab_pct", "#C8102E"),
    ("Green", "green_pct", "#00843D"),
    ("ACT", "act_pct", "#B28A00"),
    ("New Zealand First", "nz_first_pct", "#6D7075"),
    ("Te Pati Maori", "te_pati_maori_pct", "#805B46"),
    ("Opportunity", "opportunity_pct", "#007F7B"),
]

BASELINE_ELECTORATE_SEATS = {"Te Pati Maori": 1}
WIDTH = 1320
HEIGHT = 820
LEFT = 300
TOP = 190
PLOT_WIDTH = 650
ROW_HEIGHT = 56


def text(x, y, value, size=14, color="#263238", anchor="start", extra=""):
    return (
        f'<text x="{x}" y="{y}" font-family="DejaVu Sans, sans-serif" '
        f'font-size="{size}" fill="{color}" text-anchor="{anchor}" {extra}>'
        f"{html.escape(str(value))}</text>"
    )


def latest_poll():
    with DATA_FILE.open(newline="", encoding="utf-8") as source:
        polls = [row for row in csv.DictReader(source) if row["record_type"] == "poll"]
    if not polls:
        raise ValueError("No poll records found in polls.csv")
    return max(polls, key=lambda row: row["date_sort"])


def sensitivity_rows(poll):
    votes = {
        label: float(poll[column])
        for label, column, _ in PARTIES
    }
    rows = []

    for label, _, color in PARTIES:
        electorate_seats = dict(BASELINE_ELECTORATE_SEATS)
        electorate_seats[label] = max(1, electorate_seats.get(label, 0))
        result = project_mmp(votes, electorate_seats)
        party = result["parties"][label]
        entitlement = party["proportional_entitlement"]
        rows.append(
            {
                "party": label,
                "party_vote_pct": party["party_vote_pct"],
                "entitlement": entitlement,
                "first_overhang_at": entitlement + 1,
                "list_seats_at_one_win": party["list_seats"],
                "color": color,
            }
        )

    return sorted(rows, key=lambda row: row["first_overhang_at"])


def write_summary(poll, rows):
    columns = [
        "poll_date",
        "pollster",
        "scenario_party",
        "party_vote_pct",
        "proportional_entitlement",
        "first_overhang_at_electorate_wins",
        "list_seats_at_one_electorate_win",
        "assumption",
    ]
    with SUMMARY_FILE.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "poll_date": poll["date_label"],
                    "pollster": poll["pollster"],
                    "scenario_party": row["party"],
                    "party_vote_pct": row["party_vote_pct"],
                    "proportional_entitlement": row["entitlement"],
                    "first_overhang_at_electorate_wins": row["first_overhang_at"],
                    "list_seats_at_one_electorate_win": row["list_seats_at_one_win"],
                    "assumption": (
                        "Te Pati Maori qualifies with one electorate seat; "
                        f"{row['party']} is the focal party in this scenario."
                    ),
                }
            )


def render(poll, rows):
    maximum = max(row["first_overhang_at"] for row in rows)
    x_max = max(40, math.ceil(maximum / 5) * 5)
    plot_bottom = TOP + ROW_HEIGHT * len(rows)

    def x_position(seats):
        return LEFT + seats / x_max * PLOT_WIDTH

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
        f'height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        text(32, 48, "When could an overhang begin?", 28, "#17212B"),
        text(
            32,
            79,
            f"Party-vote base: {poll['pollster']}, {poll['date_label']}. "
            "TPM qualifies via one electorate; each row varies one party's wins.",
            15,
            "#5D6872",
        ),
    ]

    parts.extend(
        [
            f'<circle cx="38" cy="122" r="6" fill="#263238"/>',
            text(52, 127, "Proportional seat entitlement", 13, "#4E5963"),
            '<polygon points="280,115 287,122 280,129 273,122" fill="#263238"/>',
            text(294, 127, "First electorate-seat count causing overhang", 13, "#4E5963"),
        ]
    )

    for seats in range(0, x_max + 1, 5):
        x = x_position(seats)
        parts.append(
            f'<line x1="{x:.1f}" y1="{TOP - 12}" '
            f'x2="{x:.1f}" y2="{plot_bottom}" '
            'stroke="#E5E9EC" stroke-width="1"/>'
        )
        parts.append(text(x, plot_bottom + 25, seats, 12, "#59636E", "middle"))

    eligibility_x = x_position(1)
    parts.append(
        f'<line x1="{eligibility_x:.1f}" y1="{TOP - 12}" '
        f'x2="{eligibility_x:.1f}" y2="{plot_bottom}" '
        'stroke="#8A6D3B" stroke-width="1.5" stroke-dasharray="4 4"/>'
    )
    parts.append(text(eligibility_x + 5, TOP - 20, "1 win qualifies <5% party", 11, "#775B2A"))

    for index, row in enumerate(rows):
        y = TOP + index * ROW_HEIGHT + 22
        entitlement_x = x_position(row["entitlement"])
        overhang_x = x_position(row["first_overhang_at"])
        parts.append(text(28, y - 3, row["party"], 14, "#263238"))
        share_label = (
            f"{row['party_vote_pct']:.1f}% party vote"
        )
        parts.append(text(28, y + 15, share_label, 11, "#69737C"))
        parts.append(
            f'<line x1="{LEFT}" y1="{y:.1f}" x2="{overhang_x:.1f}" '
            f'y2="{y:.1f}" stroke="{row["color"]}" stroke-width="7" '
            'stroke-opacity="0.24" stroke-linecap="round"/>'
        )
        parts.append(
            f'<circle cx="{entitlement_x:.1f}" cy="{y:.1f}" r="6" '
            f'fill="{row["color"]}" stroke="#FFFFFF" stroke-width="1.5">'
            f'<title>{row["entitlement"]} proportional seats</title></circle>'
        )
        parts.append(
            f'<polygon points="{overhang_x:.1f},{y - 7:.1f} '
            f'{overhang_x + 7:.1f},{y:.1f} {overhang_x:.1f},{y + 7:.1f} '
            f'{overhang_x - 7:.1f},{y:.1f}" fill="{row["color"]}">'
            f'<title>Overhang begins at {row["first_overhang_at"]} electorate seats</title>'
            '</polygon>'
        )
        parts.append(
            text(
                1000,
                y + 5,
                f"{row['entitlement']} entitled  →  overhang at {row['first_overhang_at']}",
                13,
                "#263238",
            )
        )

    parts.extend(
        [
            text(
                LEFT + PLOT_WIDTH / 2,
                plot_bottom + 58,
                "Electorate seats won by the party",
                14,
                "#263238",
                "middle",
            ),
            text(
                32,
                HEIGHT - 44,
                "Illustrative sensitivity, not seat forecasts: other parties' electorate wins are set to zero in each row.",
                12,
                "#5D6872",
            ),
            text(
                32,
                HEIGHT - 24,
                "Other parties are aggregated in the poll; they are not modeled as one party. Add a party's own vote share to analyze it.",
                12,
                "#5D6872",
            ),
            "</svg>",
        ]
    )
    OUTPUT_FILE.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main():
    poll = latest_poll()
    rows = sensitivity_rows(poll)
    render(poll, rows)
    write_summary(poll, rows)
    print(f"Wrote {OUTPUT_FILE.name} and {SUMMARY_FILE.name}: {len(rows)} parties")


if __name__ == "__main__":
    main()
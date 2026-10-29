import csv
import html
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
POLL_FILE = ROOT / "electorate-polls.csv"
FORECAST_FILE = ROOT / "electorate-seat-projections.csv"
OUTPUT_FILE = ROOT / "electorate-contestability.svg"
SUMMARY_FILE = ROOT / "electorate-contestability.csv"

PARTY_COLORS = {
    "NAT": "#00529B",
    "LAB": "#C8102E",
    "GRN": "#00843D",
    "ACT": "#B28A00",
    "NZF": "#6D7075",
    "TPM": "#805B46",
    "OPP": "#007F7B",
    "TTT": "#CC79A7",
    "IND": "#39424E",
}

WIDTH = 1440
LEFT = 320
PLOT_WIDTH = 650
RIGHT = LEFT + PLOT_WIDTH + 28
TOP = 218
ROW_HEIGHT = 42
MAX_SHARE = 60


def svg_text(x, y, value, size=13, color="#263238", anchor="start"):
    return (
        f'<text x="{x}" y="{y}" font-family="DejaVu Sans, sans-serif" '
        f'font-size="{size}" fill="{color}" text-anchor="{anchor}">'
        f"{html.escape(str(value))}</text>"
    )


def latest_poll_results():
    with POLL_FILE.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))

    polls = defaultdict(list)
    for row in rows:
        if row["vote_type"] == "electorate_vote" and row["share_pct"].strip():
            polls[(row["electorate"], row["poll_id"])].append(row)

    by_electorate = defaultdict(list)
    for (electorate, _), poll_rows in polls.items():
        by_electorate[electorate].append(poll_rows)

    latest = []
    for electorate, groups in by_electorate.items():
        latest_date = max(group[0]["plot_date"] for group in groups)
        same_date = [group for group in groups if group[0]["plot_date"] == latest_date]
        poll_rows = max(
            same_date,
            key=lambda group: max(int(row["sample_n"] or 0) for row in group),
        )
        ranked = sorted(poll_rows, key=lambda row: float(row["share_pct"]), reverse=True)
        top_share = float(ranked[0]["share_pct"])
        top_parties = {
            row["party"] for row in ranked if float(row["share_pct"]) == top_share
        }
        tied = len(top_parties) > 1
        runner = next(
            (row for row in ranked if float(row["share_pct"]) < top_share),
            None,
        )
        runner_share = top_share if tied else float(runner["share_pct"]) if runner else top_share
        latest.append(
            {
                "electorate": electorate,
                "date_label": poll_rows[0]["date_label"],
                "pollster": poll_rows[0]["pollster"],
                "sample_n": poll_rows[0]["sample_n"],
                "leader_party": ranked[0]["party"] if not tied else "Tie",
                "tied_parties": " / ".join(sorted(top_parties)) if tied else "",
                "leader_pct": top_share,
                "runnerup_party": runner["party"] if runner and not tied else "",
                "runnerup_pct": runner_share,
                "lead_pp": 0.0 if tied else round(top_share - runner_share, 1),
            }
        )

    with FORECAST_FILE.open(newline="", encoding="utf-8") as source:
        forecast = {row["electorate"]: row for row in csv.DictReader(source)}

    for row in latest:
        estimate = forecast.get(row["electorate"], {})
        row["model_party"] = estimate.get("predicted_party", "")
        row["forecast_method"] = estimate.get("forecast_method", "")
    return sorted(latest, key=lambda row: (row["lead_pp"], row["electorate"]))


def write_summary(rows):
    fields = [
        "rank_by_poll_margin",
        "electorate",
        "date_label",
        "pollster",
        "sample_n",
        "leader_party",
        "tied_parties",
        "leader_pct",
        "runnerup_party",
        "runnerup_pct",
        "lead_pp",
        "model_party",
        "forecast_method",
    ]
    with SUMMARY_FILE.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        for rank, row in enumerate(rows, 1):
            writer.writerow({"rank_by_poll_margin": rank, **row})


def render(rows):
    height = TOP + ROW_HEIGHT * len(rows) + 115

    def x_position(share):
        return LEFT + share / MAX_SHARE * PLOT_WIDTH

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        svg_text(28, 44, "Closest electorate races in available 2026 polls", 27, "#17212B"),
        svg_text(
            28,
            74,
            "Latest electorate-vote poll per seat; endpoints are the top two party-affiliated candidates.",
            14,
            "#5D6872",
        ),
        svg_text(28, 107, "PARTY COLORS", 11, "#69737C"),
    ]

    legend = [(party, color) for party, color in PARTY_COLORS.items()]
    for index, (party, color) in enumerate(legend):
        column = index % 5
        row = index // 5
        x = 28 + column * 250
        y = 129 + row * 22
        parts.append(f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{color}"/>')
        parts.append(svg_text(x + 16, y, party, 11, "#4E5963"))

    for share in range(0, MAX_SHARE + 1, 10):
        x = x_position(share)
        parts.append(
            f'<line x1="{x:.1f}" y1="{TOP - 16}" x2="{x:.1f}" '
            f'y2="{TOP + ROW_HEIGHT * len(rows)}" stroke="#E5E9EC" stroke-width="1"/>'
        )
        parts.append(svg_text(x, TOP + ROW_HEIGHT * len(rows) + 21, f"{share}%", 11, "#59636E", "middle"))

    for index, row in enumerate(rows):
        y = TOP + index * ROW_HEIGHT + 16
        leader_x = x_position(row["leader_pct"])
        runner_x = x_position(row["runnerup_pct"])
        leader_color = PARTY_COLORS.get(row["leader_party"], "#39424E")
        runner_color = PARTY_COLORS.get(row["runnerup_party"], "#39424E")

        parts.append(svg_text(28, y, row["electorate"], 13, "#263238"))
        parts.append(
            svg_text(28, y + 14, f"{row['date_label']} · {row['pollster']}", 9, "#69737C")
        )
        if not row["tied_parties"]:
            parts.append(
                f'<line x1="{runner_x:.1f}" y1="{y - 3}" x2="{leader_x:.1f}" y2="{y - 3}" '
                'stroke="#ADB6BE" stroke-width="2"/>'
            )
            parts.append(
                f'<circle cx="{runner_x:.1f}" cy="{y - 3}" r="5.5" fill="{runner_color}" '
                'stroke="#FFFFFF" stroke-width="1.5">'
                f'<title>{row["runnerup_party"]} {row["runnerup_pct"]:.1f}%</title></circle>'
            )
        parts.append(
            f'<circle cx="{leader_x:.1f}" cy="{y - 3}" r="5.5" fill="{leader_color}" '
            'stroke="#FFFFFF" stroke-width="1.5">'
            f'<title>{row["leader_party"]} {row["leader_pct"]:.1f}%</title></circle>'
        )
        lead_label = (
            f"Tie: {row['tied_parties']} {row['leader_pct']:.1f}%"
            if row["tied_parties"]
            else
            f"{row['leader_party']} {row['leader_pct']:.1f} vs "
            f"{row['runnerup_party']} {row['runnerup_pct']:.1f}"
        )
        parts.append(svg_text(RIGHT, y - 4, lead_label, 11, "#263238"))
        model = f"model: {row['model_party']}" if row["model_party"] else "model: unassigned"
        parts.append(
            svg_text(RIGHT, y + 11, f"lead {row['lead_pp']:.1f} pp · {model}", 10, "#69737C")
        )

    chart_bottom = TOP + ROW_HEIGHT * len(rows)
    parts.extend(
        [
            svg_text(LEFT + PLOT_WIDTH / 2, chart_bottom + 47, "Electorate-vote share", 13, "#263238", "middle"),
            svg_text(
                28,
                height - 42,
                f"Shows {len(rows)} electorates with local polls; the other 55 seat estimates rely on fallback assumptions.",
                11,
                "#5D6872",
            ),
            svg_text(
                28,
                height - 22,
                "Poll lead is not a win probability; sample sizes and field dates vary. Only latest poll per electorate shown.",
                11,
                "#5D6872",
            ),
            "</svg>",
        ]
    )
    OUTPUT_FILE.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main():
    rows = latest_poll_results()
    if not rows:
        raise ValueError("No electorate-vote poll rows were found")
    write_summary(rows)
    render(rows)
    print(f"Wrote {OUTPUT_FILE.name} and {SUMMARY_FILE.name}: {len(rows)} polled electorates")


if __name__ == "__main__":
    main()
import csv
import html
import json
import math
import re
import urllib.parse
import urllib.request
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from mmp_projection import project_mmp


ROOT = Path(__file__).resolve().parent
PARTY_POLL_FILE = ROOT / "polls.csv"
ELECTORATE_POLL_FILE = ROOT / "electorate-polls.csv"
ELECTORATE_OUTPUT_FILE = ROOT / "electorate-seat-projections.csv"
COALITION_OUTPUT_FILE = ROOT / "coalition-mp-projections.csv"
CHART_OUTPUT_FILE = ROOT / "coalition-mp-projections.svg"
MMP_BREAKDOWN_OUTPUT_FILE = ROOT / "mmp-seat-breakdown.csv"
OVERHANG_CHART_OUTPUT_FILE = ROOT / "overhang-explanation.svg"

CANDIDATE_PAGE = "Candidates in the 2026 New Zealand general election by electorate"
RESULTS_PAGE = "2023 New Zealand general election"
CANDIDATE_URL = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(CANDIDATE_PAGE.replace(' ', '_'))}"
RESULTS_URL = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(RESULTS_PAGE.replace(' ', '_'))}"
RETRIEVED = date.today().isoformat()

PARTY_VOTE_COLUMNS = {
    "National": "nat_pct",
    "Labour": "lab_pct",
    "Green": "green_pct",
    "ACT": "act_pct",
    "New Zealand First": "nz_first_pct",
    "Te Pati Maori": "te_pati_maori_pct",
    "Opportunity": "opportunity_pct",
}

PARTY_ALIASES = {
    "NAT": "National",
    "National": "National",
    "LAB": "Labour",
    "Labour": "Labour",
    "GRN": "Green",
    "Green": "Green",
    "ACT": "ACT",
    "NZF": "New Zealand First",
    "New Zealand First": "New Zealand First",
    "TPM": "Te Pati Maori",
    "Te Pāti Māori": "Te Pati Maori",
    "Te Pati Maori": "Te Pati Maori",
    "OPP": "Opportunity",
    "Opportunity": "Opportunity",
    "TTT": "Te Tai Tokerau",
    "Te Tai Tokerau": "Te Tai Tokerau",
    "IND": "Independent",
    "Independent": "Independent",
}

WINNER_COLOR_TO_PARTY = {
    "#00529f": "National",
    "#d82a20": "Labour",
    "#b2001a": "Te Pati Maori",
    "#098137": "Green",
    "#fde401": "ACT",
}

PREVIOUS_NAME_ALIASES = {
    "Mount Albert": "Mt Albert",
    "Mount Roskill": "Mt Roskill",
}

MANUAL_FALLBACKS = {
    "Port Waikato": (
        "National",
        "National held the electorate after the 2023 Port Waikato by-election; "
        "the 2023 general-election electorate vote was cancelled.",
    ),
    "Waitākere": (
        "National",
        "Provisional predecessor-seat assumption: the 2026 roster lists the "
        "retiring National MP for New Lynn under Waitākere.",
    ),
}

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

COALITION_SCENARIOS = [
    (
        "LAB + GRN + OPP + TPM",
        ("Labour", "Green", "Opportunity", "Te Pati Maori"),
        "#8654A3",
    ),
    ("LAB + GRN + NZF", ("Labour", "Green", "New Zealand First"), "#D55E00"),
    (
        "LAB + GRN + OPP + NZF",
        ("Labour", "Green", "Opportunity", "New Zealand First"),
        "#B2182B",
    ),
    ("NAT + ACT + NZF", ("National", "ACT", "New Zealand First"), "#56B4E9"),
    (
        "NAT + ACT + NZF + OPP",
        ("National", "ACT", "New Zealand First", "Opportunity"),
        "#332288",
    ),
]


def normalize_name(value):
    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def fetch_page(title, section=None):
    params = {"action": "parse", "page": title, "prop": "text", "format": "json"}
    if section is not None:
        params["section"] = str(section)
    request = urllib.request.Request(
        "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params),
        headers={"User-Agent": "Mozilla/5.0 election-analysis contact=local"},
    )
    payload = json.load(urllib.request.urlopen(request, timeout=30))
    return BeautifulSoup(payload["parse"]["text"]["*"], "html.parser")


def extract_roster(soup):
    roster = {}
    for heading in soup.find_all("h3"):
        electorate = heading.get_text(" ", strip=True)
        if electorate in {"General electorates", "Māori electorates", "Notes", "References"}:
            continue

        table = heading.find_next("table")
        if table is None:
            continue

        electorate_type = "Maori" if electorate.startswith("Te Tai") or electorate in {
            "Hauraki-Waikato",
            "Ikaroa-Rāwhiti",
            "Tāmaki Makaurau",
            "Waiariki",
        } else "General"
        incumbent_party = ""
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) < 3:
                continue
            if "#cff" in cells[2].get("style", "").lower():
                candidate_party = cells[1].get_text(" ", strip=True)
                incumbent_party = PARTY_ALIASES.get(candidate_party, candidate_party)
                break

        roster[normalize_name(electorate)] = {
            "electorate": electorate,
            "electorate_type": electorate_type,
            "incumbent_party": incumbent_party,
        }

    if not 65 <= len(roster) <= 75:
        raise ValueError(f"Unexpected 2026 electorate roster size: {len(roster)}")
    return roster


def extract_previous_winners(soup):
    table = soup.find("table")
    if table is None:
        raise ValueError("Could not find 2023 electorate results table")

    winners = {}
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 3:
            continue
        winning_cell_index = next(
            (
                index
                for index, cell in enumerate(cells)
                if "font-weight:bold" in cell.get("style", "").lower()
            ),
            None,
        )
        if winning_cell_index is None or winning_cell_index == 0:
            continue

        party_marker = next(
            (
                cells[index].get("style", "").lower()
                for index in range(winning_cell_index - 1, -1, -1)
                if "background" in cells[index].get("style", "").lower()
            ),
            "",
        )
        color_match = re.search(r"background(?:-color)?\s*:\s*(#[0-9a-f]+)", party_marker)
        if not color_match:
            continue
        party = WINNER_COLOR_TO_PARTY.get(color_match.group(1))
        electorate = cells[0].get_text(" ", strip=True)
        if party and electorate:
            winners[normalize_name(electorate)] = party

    if len(winners) < 65:
        raise ValueError(f"Only parsed {len(winners)} 2023 electorate winners")
    return winners


def latest_electorate_poll_leaders():
    with ELECTORATE_POLL_FILE.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))

    by_electorate_and_poll = {}
    for row in rows:
        if row["vote_type"] != "electorate_vote" or not row["share_pct"]:
            continue
        electorate_key = normalize_name(row["electorate"])
        by_electorate_and_poll.setdefault(electorate_key, {}).setdefault(
            row["poll_id"], []
        ).append(row)

    leaders = {}
    for electorate_key, polls in by_electorate_and_poll.items():
        latest_date = max(
            max(row["plot_date"] for row in poll_rows) for poll_rows in polls.values()
        )
        latest_polls = [
            poll_rows
            for poll_rows in polls.values()
            if max(row["plot_date"] for row in poll_rows) == latest_date
        ]
        latest = max(
            latest_polls,
            key=lambda poll_rows: max(int(row["sample_n"] or 0) for row in poll_rows),
        )
        high_share = max(float(row["share_pct"]) for row in latest)
        top_parties = {
            PARTY_ALIASES.get(row["party"], row["party"])
            for row in latest
            if float(row["share_pct"]) == high_share
        }
        leaders[electorate_key] = {
            "party": next(iter(top_parties)) if len(top_parties) == 1 else "",
            "poll_date": latest[0]["date_label"],
            "pollster": latest[0]["pollster"],
            "leader_share_pct": high_share,
            "poll_id": latest[0]["poll_id"],
            "tie": len(top_parties) > 1,
        }
    return leaders


def latest_party_vote():
    with PARTY_POLL_FILE.open(newline="", encoding="utf-8") as source:
        polls = [
            row for row in csv.DictReader(source) if row["record_type"] == "poll"
        ]
    latest = max(polls, key=lambda row: row["date_sort"])
    votes = {
        party: float(latest[column])
        for party, column in PARTY_VOTE_COLUMNS.items()
        if latest[column].strip()
    }
    return latest, votes


def predict_electorates(roster, previous_winners, poll_leaders):
    manual = {
        normalize_name("Port Waikato"): (
            "National",
            "Manual baseline: National won the 2023 Port Waikato by-election after "
            "the general-election electorate vote was cancelled.",
        ),
        normalize_name("Waitākere"): (
            "National",
            "Manual baseline: successor-seat assumption based on the retiring "
            "National MP for New Lynn listed under Waitākere.",
        ),
    }
    predictions = []
    for key, seat in roster.items():
        local_poll = poll_leaders.get(key)
        prior_key = key
        for current_name, prior_name in PREVIOUS_NAME_ALIASES.items():
            if normalize_name(current_name) == key:
                prior_key = normalize_name(prior_name)
                break
        prior_party = previous_winners.get(prior_key, "")

        if local_poll and not local_poll["tie"]:
            winner = local_poll["party"]
            method = "2026_local_poll"
            note = "Latest available 2026 electorate-vote poll leader."
        elif seat["incumbent_party"]:
            winner = seat["incumbent_party"]
            method = "incumbent_hold"
            note = "Unpolled seat held by current incumbent party."
            if local_poll and local_poll["tie"]:
                note = "Latest local poll tied; used current incumbent party."
        elif prior_party:
            winner = prior_party
            method = "2023_same_name_winner"
            note = "No incumbent marker or decisive local poll; held 2023 winner."
        elif key in manual:
            winner, note = manual[key]
            method = "manual_fallback"
        else:
            raise ValueError(f"No forecast baseline available for {seat['electorate']}")

        predictions.append(
            {
                **seat,
                "predicted_party": winner,
                "forecast_method": method,
                "poll_date": local_poll["poll_date"] if local_poll else "",
                "pollster": local_poll["pollster"] if local_poll else "",
                "poll_leader_share_pct": local_poll["leader_share_pct"]
                if local_poll
                else "",
                "incumbent_party": seat["incumbent_party"],
                "2023_same_name_winner": prior_party,
                "assumption": note,
            }
        )

    return predictions


def coalition_results(party_vote, electorate_predictions):
    direct_seats = Counter(row["predicted_party"] for row in electorate_predictions)
    projection = project_mmp(party_vote, direct_seats)
    majority = projection["parliament_size"] // 2 + 1
    rows = []
    for label, parties, color in COALITION_SCENARIOS:
        member_seats = {
            party: projection["parties"].get(party, {}).get("total_seats", 0)
            for party in parties
        }
        seats = sum(member_seats.values())
        rows.append(
            {
                "scenario": label,
                "parties": parties,
                "party_seats": member_seats,
                "projected_mps": seats,
                "overhang_mps": sum(
                    projection["parties"].get(party, {}).get("overhang_seats", 0)
                    for party in parties
                ),
                "majority_threshold": majority,
                "parliament_size": projection["parliament_size"],
                "majority": seats >= majority,
                "color": color,
            }
        )
    rows.sort(key=lambda row: (-row["projected_mps"], row["scenario"]))
    return projection, rows


def write_electorate_csv(poll, predictions):
    fields = [
        "electorate",
        "electorate_type",
        "predicted_party",
        "forecast_method",
        "poll_date",
        "pollster",
        "poll_leader_share_pct",
        "incumbent_party",
        "2023_same_name_winner",
        "assumption",
        "party_vote_poll_date",
        "party_vote_pollster",
        "source_candidate_page",
        "source_electorate_poll_page",
        "retrieved_date",
    ]
    with ELECTORATE_OUTPUT_FILE.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        for row in predictions:
            writer.writerow(
                {
                    **{field: row.get(field, "") for field in fields},
                    "party_vote_poll_date": poll["date_label"],
                    "party_vote_pollster": poll["pollster"],
                    "source_candidate_page": CANDIDATE_URL,
                    "source_electorate_poll_page": RESULTS_URL,
                    "retrieved_date": RETRIEVED,
                }
            )


def write_coalition_csv(poll, electorate_predictions, projection, scenarios):
    fields = [
        "rank_by_seats",
        "scenario",
        "parties",
        "projected_mps",
        "overhang_mps_in_coalition",
        "majority_threshold",
        "parliament_size",
        "majority",
        "party_vote_poll_date",
        "party_vote_pollster",
        "seat_forecast_basis",
        "overhang_total",
    ]
    methods = Counter(row["forecast_method"] for row in electorate_predictions)
    basis = "; ".join(f"{method}={count}" for method, count in sorted(methods.items()))
    with COALITION_OUTPUT_FILE.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        for rank, row in enumerate(scenarios, 1):
            writer.writerow(
                {
                    "rank_by_seats": rank,
                    "scenario": row["scenario"],
                    "parties": " + ".join(row["parties"]),
                    "projected_mps": row["projected_mps"],
                    "overhang_mps_in_coalition": row["overhang_mps"],
                    "majority_threshold": row["majority_threshold"],
                    "parliament_size": row["parliament_size"],
                    "majority": row["majority"],
                    "party_vote_poll_date": poll["date_label"],
                    "party_vote_pollster": poll["pollster"],
                    "seat_forecast_basis": basis,
                    "overhang_total": projection["overhang_seats"],
                }
            )


def svg_text(x, y, value, size=14, color="#263238", anchor="start"):
    return (
        f'<text x="{x}" y="{y}" font-family="DejaVu Sans, sans-serif" '
        f'font-size="{size}" fill="{color}" text-anchor="{anchor}">'
        f"{html.escape(str(value))}</text>"
    )


def render_coalition_chart(poll, electorate_predictions, projection, scenarios):
    width = 1480
    height = 760
    left = 300
    top = 190
    plot_width = 760
    row_height = 42
    plot_bottom = top + row_height * len(scenarios)
    majority = scenarios[0]["majority_threshold"]
    x_max = max(80, math.ceil(max(row["projected_mps"] for row in scenarios) / 10) * 10)

    def x_position(seats):
        return left + seats / x_max * plot_width

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        svg_text(32, 48, "Rough electorate and coalition seat scenarios", 28, "#17212B"),
        svg_text(
            32,
            78,
            "Stacked bars are party seats; dashed line is majority. Order is by MPs, not probability.",
            15,
            "#5D6872",
        ),
        svg_text(32, 111, "PARTY SEAT SEGMENTS", 11, "#69737C"),
    ]

    for index, (party, color) in enumerate(PARTY_COLORS.items()):
        column = index % 5
        row = index // 5
        x = 32 + column * 265
        y = 132 + row * 25
        parts.append(
            f'<rect x="{x}" y="{y - 10}" width="11" height="11" fill="{color}"/>'
        )
        parts.append(svg_text(x + 17, y, party, 11, "#4E5963"))

    for seats in range(0, x_max + 1, 10):
        x = x_position(seats)
        parts.append(
            f'<line x1="{x:.1f}" y1="{top - 22}" x2="{x:.1f}" y2="{plot_bottom}" '
            'stroke="#E5E9EC" stroke-width="1"/>'
        )
        parts.append(svg_text(x, plot_bottom + 25, seats, 12, "#59636E", "middle"))

    majority_x = x_position(majority)
    parts.append(
        f'<line x1="{majority_x:.1f}" y1="{top - 22}" '
        f'x2="{majority_x:.1f}" y2="{plot_bottom}" '
        'stroke="#252525" stroke-width="2" stroke-dasharray="6 4"/>'
    )
    parts.append(svg_text(majority_x + 6, top - 28, f"Majority: {majority}", 12, "#252525"))

    for index, scenario in enumerate(scenarios):
        y = top + index * row_height + 18
        parts.append(svg_text(24, y + 4, scenario["scenario"], 14, "#263238"))
        x = left
        for party in scenario["parties"]:
            seats = scenario["party_seats"][party]
            segment_width = seats / x_max * plot_width
            color = PARTY_COLORS.get(party, "#59636E")
            parts.append(
                f'<rect x="{x:.2f}" y="{y - 10}" width="{segment_width:.2f}" height="20" '
                f'fill="{color}"><title>{party}: {seats} seats</title></rect>'
            )
            if segment_width > 34:
                parts.append(
                    svg_text(x + segment_width / 2, y + 4, seats, 11, "#FFFFFF", "middle")
                )
            x += segment_width

        suffix = "MAJORITY" if scenario["majority"] else f"short {majority - scenario['projected_mps']}"
        overhang = (
            f"; {scenario['overhang_mps']} OH"
            if scenario["overhang_mps"]
            else ""
        )
        parts.append(
            svg_text(
                left + plot_width + 22,
                y + 4,
                f"{scenario['projected_mps']} MPs{overhang}  {suffix}",
                13,
                "#263238",
            )
        )

    method_counts = Counter(row["forecast_method"] for row in electorate_predictions)
    methods_text = ", ".join(f"{count} {method}" for method, count in sorted(method_counts.items()))
    parts.extend(
        [
            svg_text(
                24,
                plot_bottom + 58,
                f"Electorate assignments: {methods_text}.",
                12,
                "#4E5963",
            ),
            svg_text(
                24,
                height - 46,
                "Overhang is included in MPs and Parliament size. TPM qualifies via its projected electorate win;",
                12,
                "#5D6872",
            ),
            svg_text(
                24,
                height - 26,
                "sub-5% parties are excluded as coalition partners; aggregate 'Others' is not modeled as a party.",
                12,
                "#5D6872",
            ),
            "</svg>",
        ]
    )
    CHART_OUTPUT_FILE.write_text("\n".join(parts) + "\n", encoding="utf-8")


def write_mmp_breakdown_csv(poll, projection):
    fields = [
        "party",
        "party_vote_pct",
        "qualified",
        "proportional_entitlement_120",
        "predicted_electorate_seats",
        "list_seats",
        "overhang_seats",
        "projected_total_mps",
        "party_vote_poll_date",
        "party_vote_pollster",
    ]
    rows = [
        (party, values)
        for party, values in projection["parties"].items()
        if values["party_vote_pct"] > 0 or values["electorate_seats"] > 0
    ]
    rows.sort(
        key=lambda item: (
            -item[1]["overhang_seats"],
            -item[1]["electorate_seats"],
            -item[1]["proportional_entitlement"],
            item[0],
        )
    )
    with MMP_BREAKDOWN_OUTPUT_FILE.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        for party, values in rows:
            writer.writerow(
                {
                    "party": party,
                    "party_vote_pct": values["party_vote_pct"],
                    "qualified": values["qualified"],
                    "proportional_entitlement_120": values["proportional_entitlement"],
                    "predicted_electorate_seats": values["electorate_seats"],
                    "list_seats": values["list_seats"],
                    "overhang_seats": values["overhang_seats"],
                    "projected_total_mps": values["total_seats"],
                    "party_vote_poll_date": poll["date_label"],
                    "party_vote_pollster": poll["pollster"],
                }
            )


def render_overhang_chart(poll, electorate_predictions, projection):
    parties = [
        (party, values)
        for party, values in projection["parties"].items()
        if values["party_vote_pct"] > 0 or values["electorate_seats"] > 0
    ]
    parties.sort(
        key=lambda item: (
            -item[1]["overhang_seats"],
            -item[1]["electorate_seats"],
            -item[1]["proportional_entitlement"],
        )
    )

    width = 1360
    height = 690
    left = 340
    top = 178
    plot_width = 545
    row_height = 44
    plot_bottom = top + row_height * len(parties)
    max_seats = max(
        max(values["proportional_entitlement"], values["electorate_seats"])
        for _, values in parties
    )
    x_max = max(50, ((max_seats + 9) // 10) * 10)

    def x_position(seats):
        return left + seats / x_max * plot_width

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        svg_text(32, 44, "Why an overhang appears in this scenario", 27, "#17212B"),
        svg_text(
            32,
            72,
            f"{poll['pollster']}, {poll['date_label']}: party-vote entitlement versus predicted electorate wins.",
            14,
            "#5D6872",
        ),
        '<rect x="32" y="98" width="14" height="10" fill="#69737C" fill-opacity="0.24"/>',
        svg_text(54, 108, "Proportional entitlement (120-seat MMP allocation)", 12, "#4E5963"),
        '<rect x="346" y="98" width="14" height="10" fill="#00529B"/>',
        svg_text(368, 108, "Predicted electorate seats", 12, "#4E5963"),
        '<rect x="595" y="98" width="14" height="10" fill="#C75B12"/>',
        svg_text(617, 108, "Overhang: electorate seats above entitlement", 12, "#4E5963"),
    ]

    for seats in range(0, x_max + 1, 10):
        x = x_position(seats)
        parts.append(
            f'<line x1="{x:.1f}" y1="{top - 14}" x2="{x:.1f}" y2="{plot_bottom}" '
            'stroke="#E5E9EC" stroke-width="1"/>'
        )
        parts.append(svg_text(x, plot_bottom + 22, seats, 11, "#59636E", "middle"))

    for index, (party, values) in enumerate(parties):
        y = top + index * row_height + 16
        entitlement = values["proportional_entitlement"]
        electorate = values["electorate_seats"]
        overhang = values["overhang_seats"]
        list_seats = values["list_seats"]
        color = PARTY_COLORS.get(party, "#39424E")

        parts.append(svg_text(28, y + 4, party, 14, "#263238"))
        parts.append(
            svg_text(28, y + 18, f"{values['party_vote_pct']:.1f}% party vote", 10, "#69737C")
        )
        parts.append(
            f'<rect x="{left}" y="{y - 7}" width="{x_position(entitlement) - left:.2f}" '
            f'height="14" fill="{color}" fill-opacity="0.24"/>'
        )
        if electorate:
            parts.append(
                f'<rect x="{left}" y="{y - 3}" width="{x_position(electorate) - left:.2f}" '
                f'height="6" fill="{color}"/>'
            )
        if overhang:
            parts.append(
                f'<rect x="{x_position(entitlement):.2f}" y="{y - 7}" '
                f'width="{x_position(electorate) - x_position(entitlement):.2f}" height="14" '
                'fill="#C75B12"/>'
            )
        parts.append(
            svg_text(
                left + plot_width + 20,
                y + 4,
                f"{entitlement} entitled  |  {electorate} electorate  |  "
                f"{list_seats} list  |  +{overhang} overhang",
                12,
                "#263238",
            )
        )

    methods = Counter(row["forecast_method"] for row in electorate_predictions)
    method_text = ", ".join(f"{method} {count}" for method, count in sorted(methods.items()))
    parts.extend(
        [
            svg_text(
                28,
                plot_bottom + 52,
                f"Electorate basis: {method_text}.",
                11,
                "#4E5963",
            ),
            svg_text(
                28,
                height - 42,
                f"120 proportional seats + {projection['overhang_seats']} overhang = "
                f"{projection['parliament_size']} projected MPs.",
                13,
                "#263238",
            ),
            svg_text(
                28,
                height - 22,
                "Overhang = max(0, electorate seats - proportional entitlement). Incumbent holds are a rough fallback, not polling.",
                11,
                "#5D6872",
            ),
            "</svg>",
        ]
    )
    OVERHANG_CHART_OUTPUT_FILE.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main():
    roster_soup = fetch_page(CANDIDATE_PAGE)
    results_soup = fetch_page(RESULTS_PAGE, section=38)
    roster = extract_roster(roster_soup)
    previous_winners = extract_previous_winners(results_soup)
    poll_leaders = latest_electorate_poll_leaders()
    electorate_predictions = predict_electorates(roster, previous_winners, poll_leaders)
    poll, party_vote = latest_party_vote()
    projection, scenarios = coalition_results(party_vote, electorate_predictions)

    write_electorate_csv(poll, electorate_predictions)
    write_coalition_csv(poll, electorate_predictions, projection, scenarios)
    write_mmp_breakdown_csv(poll, projection)
    render_coalition_chart(poll, electorate_predictions, projection, scenarios)
    render_overhang_chart(poll, electorate_predictions, projection)

    print(
        f"Wrote {ELECTORATE_OUTPUT_FILE.name} ({len(electorate_predictions)} seats), "
        f"{COALITION_OUTPUT_FILE.name}, {CHART_OUTPUT_FILE.name}, "
        f"{MMP_BREAKDOWN_OUTPUT_FILE.name}, and {OVERHANG_CHART_OUTPUT_FILE.name}; "
        f"projected Parliament {projection['parliament_size']} "
        f"({projection['overhang_seats']} overhang seats)."
    )


if __name__ == "__main__":
    main()
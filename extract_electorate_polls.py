import csv
import re
from datetime import date
from html import unescape
from pathlib import Path

from bs4 import BeautifulSoup


SOURCE_FILE = Path(__file__).with_name("page-source.html")
OUTPUT_FILE = Path(__file__).with_name("electorate-polls.csv")
SOURCE_URL = (
    "https://en.wikipedia.org/wiki/"
    "Opinion_polling_for_the_2026_New_Zealand_general_election"
)

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def clean_cell(cell):
    for element in cell.find_all(["sup", "style", "link"]):
        element.decompose()
    return re.sub(r"\s+", " ", unescape(cell.get_text(" ", strip=True))).strip()


def parse_dates(label):
    text = label.replace("–", "-").replace("—", "-").strip()
    year_match = re.search(r"\b(20\d{2})\b", text)
    if not year_match:
        return "", "", ""
    year = int(year_match.group(1))
    date_text = text[:year_match.start()].strip()

    span = re.fullmatch(
        r"(\d{1,2})\s*([A-Za-z]+)?\s*-\s*(\d{1,2})\s*([A-Za-z]+)",
        date_text,
    )
    if span:
        start_day, start_month, end_day, end_month = span.groups()
        end_month_number = MONTHS[end_month[:3].lower()]
        start_month_number = MONTHS[(start_month or end_month)[:3].lower()]
        start_date = date(year, start_month_number, int(start_day))
        end_year = year + (1 if end_month_number < start_month_number else 0)
        end_date = date(end_year, end_month_number, int(end_day))
        midpoint = start_date + (end_date - start_date) // 2
        return start_date.isoformat(), end_date.isoformat(), midpoint.isoformat()

    single_day = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)", date_text)
    if single_day:
        day, month = single_day.groups()
        observed_date = date(year, MONTHS[month[:3].lower()], int(day))
        iso_date = observed_date.isoformat()
        return iso_date, iso_date, iso_date

    month_only = re.fullmatch(r"([A-Za-z]+)", date_text)
    if month_only:
        month = MONTHS[month_only.group(1)[:3].lower()]
        start_date = date(year, month, 1)
        next_month = date(year + (month == 12), month % 12 + 1, 1)
        end_date = date.fromordinal(next_month.toordinal() - 1)
        midpoint = start_date + (end_date - start_date) // 2
        return "", "", midpoint.isoformat()

    return "", "", ""


def parse_number(value):
    normalized = value.replace(",", "").replace("%", "").strip()
    if not normalized or normalized in {"—", "–", "-", "N/a", "N/A", "Tie"}:
        return ""
    match = re.fullmatch(r"~?(-?\d+(?:\.\d+)?)", normalized)
    return float(match.group(1)) if match else ""


def main():
    soup = BeautifulSoup(SOURCE_FILE.read_text(encoding="utf-8"), "html.parser")
    root = soup.find("section", attrs={"data-mw-section-id": "4"})
    if root is None:
        raise ValueError("Could not find the Electorate polling section")

    fields = [
        "poll_id",
        "electorate",
        "electorate_type",
        "date_start",
        "date_end",
        "plot_date",
        "date_label",
        "pollster",
        "sample_n",
        "vote_type",
        "party",
        "share_pct",
        "share_raw",
        "lead_label",
        "lead_pp",
        "source_url",
    ]
    output = []

    for heading in root.find_all("h4"):
        section = heading.find_parent("section")
        table = section.find("table", recursive=False) if section else None
        if table is None:
            continue

        electorate = heading.get_text(" ", strip=True)
        previous_heading = heading.find_previous("h3")
        electorate_type = (
            "Maori"
            if previous_heading and "Māori" in previous_heading.get_text()
            else "General"
        )
        table_rows = table.find_all("tr")
        header_cells = table_rows[0].find_all("th", recursive=False)
        headers = [clean_cell(cell) for cell in header_cells]
        parties = headers[4:-1]
        current_poll = None
        poll_number = 0

        for row in table_rows[1:]:
            cells = row.find_all("td", recursive=False)
            values = [clean_cell(cell) for cell in cells]
            vote_index = next(
                (
                    index
                    for index, value in enumerate(values)
                    if value.lower().replace(" ", "")
                    in {"partyvote", "electoratevote"}
                ),
                None,
            )
            if vote_index is None:
                continue

            if vote_index >= 3:
                poll_number += 1
                date_label, pollster, sample = values[:3]
                start_date, end_date, plot_date = parse_dates(date_label)
                sample_match = re.search(r"\d[\d,]*", sample)
                current_poll = {
                    "poll_id": f"{electorate}-{poll_number}",
                    "electorate": electorate,
                    "electorate_type": electorate_type,
                    "date_start": start_date,
                    "date_end": end_date,
                    "plot_date": plot_date,
                    "date_label": date_label,
                    "pollster": pollster,
                    "sample_n": int(sample_match.group().replace(",", ""))
                    if sample_match
                    else "",
                }
            if current_poll is None:
                continue

            vote_label = values[vote_index].lower().replace(" ", "")
            vote_type = "party_vote" if vote_label == "partyvote" else "electorate_vote"
            shares = values[vote_index + 1 : -1]
            if len(shares) != len(parties):
                raise ValueError(
                    f"{electorate}: {vote_type} has {len(shares)} values "
                    f"for {len(parties)} party columns"
                )
            lead_label = values[-1]

            for party, raw_share in zip(parties, shares):
                output.append(
                    {
                        **current_poll,
                        "vote_type": vote_type,
                        "party": party,
                        "share_pct": parse_number(raw_share),
                        "share_raw": raw_share,
                        "lead_label": lead_label,
                        "lead_pp": parse_number(lead_label),
                        "source_url": SOURCE_URL,
                    }
                )

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)

    print(f"Wrote {OUTPUT_FILE.name}: {len(output)} party results")


if __name__ == "__main__":
    main()
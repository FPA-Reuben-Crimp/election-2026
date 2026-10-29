from math import isfinite


def project_mmp(party_vote_pct, electorate_seats, total_seats=120, threshold=5.0):
    if total_seats < 1:
        raise ValueError("total_seats must be positive")
    if threshold < 0 or threshold > 100:
        raise ValueError("threshold must be between 0 and 100")

    parties = list(dict.fromkeys([*party_vote_pct, *electorate_seats]))
    votes = {}
    electorate_wins = {}
    for party in parties:
        vote = float(party_vote_pct.get(party, 0))
        wins = electorate_seats.get(party, 0)
        if not isfinite(vote) or not 0 <= vote <= 100:
            raise ValueError(f"Invalid party-vote share for {party}: {vote}")
        if not isinstance(wins, int) or isinstance(wins, bool) or wins < 0:
            raise ValueError(f"Invalid electorate-seat count for {party}: {wins}")
        votes[party] = vote
        electorate_wins[party] = wins

    qualified = {
        party: votes[party] >= threshold or electorate_wins[party] > 0
        for party in parties
    }
    eligible_parties = [party for party in parties if qualified[party]]
    if not eligible_parties:
        raise ValueError("At least one party must qualify for seat allocation")

    proportional_seats = {party: 0 for party in parties}
    for _ in range(total_seats):
        winner = max(
            eligible_parties,
            key=lambda party: votes[party] / (2 * proportional_seats[party] + 1),
        )
        proportional_seats[winner] += 1

    party_results = {}
    for party in parties:
        entitlement = proportional_seats[party]
        direct = electorate_wins[party]
        overhang = max(0, direct - entitlement) if qualified[party] else 0
        party_results[party] = {
            "party_vote_pct": votes[party],
            "qualified": qualified[party],
            "proportional_entitlement": entitlement,
            "electorate_seats": direct,
            "list_seats": max(0, entitlement - direct) if qualified[party] else 0,
            "overhang_seats": overhang,
            "total_seats": max(entitlement, direct) if qualified[party] else 0,
        }

    overhang_total = sum(result["overhang_seats"] for result in party_results.values())
    return {
        "parties": party_results,
        "base_seats": total_seats,
        "overhang_seats": overhang_total,
        "parliament_size": total_seats + overhang_total,
        "threshold_pct": threshold,
    }
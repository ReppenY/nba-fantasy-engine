"""
Category monopoly detection.

Finds players who are rare elite providers in specific categories.
"Only 3 players in the league average 2+ BLK — you have 2 of them"

This reveals:
- Trade leverage (you control a scarce resource)
- Players who are irreplaceable in specific categories
- Categories where the talent pool is thin
"""
import pandas as pd
from dataclasses import dataclass, field

from fantasy_engine.analytics.zscores import ALL_CATS


@dataclass
class CategoryMonopoly:
    """A category where few players provide elite production."""
    category: str
    threshold: float           # The "elite" threshold (e.g., 2.0 BLK/game)
    elite_players: list[dict]  # [{name, team, fantasy_team, value, z_score}]
    total_elite: int
    you_own: int
    you_own_names: list[str]
    league_control_pct: float  # What % of elite providers you control


@dataclass
class PlayerMonopolyValue:
    """How monopolistic a player's contributions are."""
    name: str
    monopoly_cats: list[str]   # Categories where they're rare elite
    monopoly_score: float      # Higher = more irreplaceable
    replacement_difficulty: str # "impossible", "very_hard", "hard", "moderate"


# Thresholds for "elite" in each category (per-game raw stats)
ELITE_THRESHOLDS = {
    "blk": 1.5,    # Very few players average 1.5+ BLK
    "stl": 1.5,    # Few players average 1.5+ STL
    "ast": 7.0,    # True point guards
    "tpm": 3.0,    # Elite 3PT shooters
    "pts": 25.0,   # Scoring leaders
    "reb": 10.0,   # Double-digit rebounders
    "tov": 1.0,    # Very low TO (elite ball security) — lower = better
}

# Z-score thresholds for "elite" per category
ELITE_Z_THRESHOLDS = {
    "blk": 2.0,
    "stl": 2.0,
    "ast": 2.0,
    "tpm": 2.0,
    "pts": 2.0,
    "reb": 2.0,
    "fg_pct": 1.5,
    "ft_pct": 1.5,
    "tov": 1.5,   # z_tov > 1.5 means very few turnovers
}


def detect_monopolies(
    all_rostered_z: pd.DataFrame,
    my_roster_z: pd.DataFrame,
    my_team_name: str = "He Who Remains",
) -> list[CategoryMonopoly]:
    """
    Detect category monopolies across the league.

    For each category, find the "elite" producers and check
    how many you own vs how many exist.
    """
    monopolies = []
    my_names = set(my_roster_z["name"].str.lower()) if "name" in my_roster_z.columns else set()

    for cat in ALL_CATS:
        z_col = f"z_{cat}"
        if z_col not in all_rostered_z.columns:
            continue

        threshold = ELITE_Z_THRESHOLDS.get(cat, 2.0)

        # Find elite players
        elite = all_rostered_z[all_rostered_z[z_col] >= threshold].copy()
        if elite.empty:
            continue

        elite_list = []
        you_own = []
        for _, row in elite.sort_values(z_col, ascending=False).iterrows():
            name = row.get("name", "")
            fantasy_team = row.get("fantasy_team_name", "")
            raw_stat = row.get(cat, 0)
            z_val = row.get(z_col, 0)

            is_mine = name.lower() in my_names
            elite_list.append({
                "name": name,
                "nba_team": row.get("nba_team", ""),
                "fantasy_team": fantasy_team,
                "raw_value": round(float(raw_stat), 1),
                "z_score": round(float(z_val), 2),
                "is_mine": is_mine,
            })
            if is_mine:
                you_own.append(name)

        total = len(elite_list)
        own_count = len(you_own)
        control_pct = own_count / total if total > 0 else 0

        monopolies.append(CategoryMonopoly(
            category=cat,
            threshold=threshold,
            elite_players=elite_list,
            total_elite=total,
            you_own=own_count,
            you_own_names=you_own,
            league_control_pct=round(control_pct, 3),
        ))

    # Sort by scarcity (fewer elite players = more monopolistic)
    monopolies.sort(key=lambda m: m.total_elite)
    return monopolies


def detect_player_monopoly_value(
    all_rostered_z: pd.DataFrame,
    my_roster_z: pd.DataFrame,
) -> list[PlayerMonopolyValue]:
    """
    For each of my players, determine how monopolistic their contributions are.

    A player who's one of only 5 elite BLK providers in the league is
    harder to replace than a player who's one of 30 elite PTS scorers.
    """
    my_names = my_roster_z["name"].tolist() if "name" in my_roster_z.columns else []
    results = []

    for player_name in my_names:
        row = my_roster_z[my_roster_z["name"] == player_name]
        if row.empty:
            continue
        row = row.iloc[0]

        monopoly_cats = []
        total_score = 0

        for cat in ALL_CATS:
            z_col = f"z_{cat}"
            if z_col not in row.index:
                continue

            player_z = float(row.get(z_col, 0))
            threshold = ELITE_Z_THRESHOLDS.get(cat, 2.0)

            if player_z >= threshold:
                # Count how many players league-wide are at this level
                elite_count = (all_rostered_z[z_col] >= threshold).sum()
                if elite_count <= 15:  # Rare enough to matter
                    monopoly_cats.append(cat)
                    # Score: rarer = more monopolistic
                    total_score += (15 - elite_count) / 15

        if monopoly_cats:
            if total_score > 1.5:
                difficulty = "impossible"
            elif total_score > 1.0:
                difficulty = "very_hard"
            elif total_score > 0.5:
                difficulty = "hard"
            else:
                difficulty = "moderate"
        else:
            difficulty = "easy"

        results.append(PlayerMonopolyValue(
            name=player_name,
            monopoly_cats=monopoly_cats,
            monopoly_score=round(total_score, 2),
            replacement_difficulty=difficulty,
        ))

    results.sort(key=lambda p: p.monopoly_score, reverse=True)
    return results

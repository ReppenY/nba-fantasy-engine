"""
External data sources: Hashtag Basketball rankings.

Scrapes free 9-cat rankings and provides comparison against our z-scores.
"""
import requests
import pandas as pd
from io import StringIO
from dataclasses import dataclass


@dataclass
class ExternalRanking:
    rank: int
    name: str
    position: str
    team: str
    gp: int
    mpg: float
    fg_pct: float
    ft_pct: float
    tpm: float
    pts: float
    reb: float
    ast: float
    stl: float
    blk: float
    tov: float
    total_zscore: float  # Hashtag's z-score


@dataclass
class RankingComparison:
    name: str
    our_rank: int
    our_z: float
    external_rank: int
    external_z: float
    rank_diff: int       # Positive = we rank higher than experts
    z_diff: float
    signal: str          # "buy_low", "sell_high", "agree", "slight_diff"


def fetch_hashtag_rankings() -> list[ExternalRanking]:
    """
    Scrape Hashtag Basketball's free 9-cat rankings.

    Returns top ~200 players with their expert z-scores.
    """
    try:
        r = requests.get(
            "https://hashtagbasketball.com/fantasy-basketball-rankings",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r.raise_for_status()

        tables = pd.read_html(StringIO(r.text))

        # Find the rankings table (largest table with player data)
        rankings_df = None
        for t in tables:
            if len(t) > 50 and "PLAYER" in t.columns:
                rankings_df = t
                break

        if rankings_df is None:
            return []

        rankings = []
        for _, row in rankings_df.iterrows():
            try:
                # Parse FG% and FT% — format is "0.570  (10.1/17.7)"
                fg_str = str(row.get("FG%", "0"))
                fg_pct = float(fg_str.split("(")[0].strip()) if "(" in fg_str else float(fg_str)

                ft_str = str(row.get("FT%", "0"))
                ft_pct = float(ft_str.split("(")[0].strip()) if "(" in ft_str else float(ft_str)

                rankings.append(ExternalRanking(
                    rank=int(row.get("R#", 0)),
                    name=str(row.get("PLAYER", "")).strip(),
                    position=str(row.get("POS", "")),
                    team=str(row.get("TEAM", "")),
                    gp=int(row.get("GP", 0)),
                    mpg=float(row.get("MPG", 0)),
                    fg_pct=fg_pct,
                    ft_pct=ft_pct,
                    tpm=float(row.get("3PM", 0)),
                    pts=float(row.get("PTS", 0)),
                    reb=float(row.get("TREB", 0)),
                    ast=float(row.get("AST", 0)),
                    stl=float(row.get("STL", 0)),
                    blk=float(row.get("BLK", 0)),
                    tov=float(row.get("TO", 0)),
                    total_zscore=float(row.get("TOTAL", 0)),
                ))
            except (ValueError, TypeError):
                continue

        return rankings

    except Exception as e:
        print(f"  Hashtag Basketball fetch failed: {e}")
        return []


def compare_rankings(
    our_z_df: pd.DataFrame,
    external: list[ExternalRanking],
) -> list[RankingComparison]:
    """
    Compare our z-score rankings against Hashtag Basketball.

    Identifies:
    - Buy low: We rank much higher than experts (undervalued by consensus)
    - Sell high: Experts rank much higher than us (overvalued by stats)
    - Agree: Rankings align
    """
    from fantasy_engine.ingestion.fantrax_api import _normalize_name

    # Build our rankings
    our_sorted = our_z_df.sort_values("z_total", ascending=False).reset_index(drop=True)
    our_rank_map = {}
    our_z_map = {}
    for i, row in our_sorted.iterrows():
        name_norm = _normalize_name(row.get("name", ""))
        our_rank_map[name_norm] = i + 1
        our_z_map[name_norm] = row.get("z_total", 0)

    # Build external map
    ext_map = {}
    for er in external:
        name_norm = _normalize_name(er.name)
        ext_map[name_norm] = er

    # Compare
    comparisons = []
    for name_norm, ext in ext_map.items():
        our_rank = our_rank_map.get(name_norm)
        our_z = our_z_map.get(name_norm)

        if our_rank is None or our_z is None:
            continue

        rank_diff = ext.rank - our_rank  # Positive = we rank them higher
        z_diff = our_z - ext.total_zscore

        if rank_diff > 30:
            signal = "sell_high"  # Experts think they're better than we do
        elif rank_diff < -30:
            signal = "buy_low"   # We think they're better than experts
        elif abs(rank_diff) <= 10:
            signal = "agree"
        else:
            signal = "slight_diff"

        comparisons.append(RankingComparison(
            name=ext.name,
            our_rank=our_rank,
            our_z=round(our_z, 2),
            external_rank=ext.rank,
            external_z=ext.total_zscore,
            rank_diff=rank_diff,
            z_diff=round(z_diff, 2),
            signal=signal,
        ))

    comparisons.sort(key=lambda c: abs(c.rank_diff), reverse=True)
    return comparisons

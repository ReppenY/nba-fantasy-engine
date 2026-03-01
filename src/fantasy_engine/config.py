from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Fantrax
    fantrax_league_id: str = ""
    fantrax_cookie: str = ""
    fantrax_csv_dir: str = "./data/csv"

    # Ball Don't Lie
    bdl_api_key: str = ""

    # NBA API
    nba_api_delay: float = 0.6

    # Database
    db_url: str = "sqlite+aiosqlite:///./data/fantasy.db"
    db_sync_url: str = "sqlite:///./data/fantasy.db"

    # League settings
    my_team_id: str = ""
    salary_cap: float = 233.0
    roster_size: int = 36
    active_slots: int = 11
    season: str = "2025-26"

    position_slots: dict = {
        "PG": 1, "SG": 1, "SF": 1, "PF": 1, "C": 1,
        "G": 1, "F": 1, "Flx": 3,
    }

    model_config = {"env_file": ".env", "env_prefix": "FANTASY_", "extra": "ignore"}

from sqlalchemy import (
    Column, Integer, Float, String, Boolean, Date, DateTime,
    ForeignKey, UniqueConstraint, Index, Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fantrax_id = Column(String(20), unique=True, index=True)
    nba_api_id = Column(Integer, nullable=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    nba_team = Column(String(5))
    positions = Column(String(50))
    age = Column(Integer)

    stats = relationship("PlayerStats", back_populates="player")
    contracts = relationship("Contract", back_populates="player")
    roster_entries = relationship("RosterEntry", back_populates="player")


class PlayerStats(Base):
    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    season = Column(String(10))
    stat_type = Column(String(20))  # "season_avg", "last_7", "last_14", "last_30"
    as_of_date = Column(Date)

    games_played = Column(Integer, default=0)
    minutes = Column(Float, default=0.0)
    pts = Column(Float, default=0.0)
    reb = Column(Float, default=0.0)
    ast = Column(Float, default=0.0)
    stl = Column(Float, default=0.0)
    blk = Column(Float, default=0.0)
    tpm = Column(Float, default=0.0)
    fgm = Column(Float, default=0.0)
    fga = Column(Float, default=0.0)
    fg_pct = Column(Float, default=0.0)
    ftm = Column(Float, default=0.0)
    fta = Column(Float, default=0.0)
    ft_pct = Column(Float, default=0.0)
    tov = Column(Float, default=0.0)

    player = relationship("Player", back_populates="stats")

    __table_args__ = (
        UniqueConstraint("player_id", "season", "stat_type", "as_of_date"),
        Index("ix_stats_lookup", "player_id", "stat_type", "as_of_date"),
    )


class PlayerGameLog(Base):
    __tablename__ = "player_game_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    game_date = Column(Date, nullable=False)
    opponent = Column(String(5))
    home_away = Column(String(1))

    minutes = Column(Float)
    pts = Column(Float)
    reb = Column(Float)
    ast = Column(Float)
    stl = Column(Float)
    blk = Column(Float)
    tpm = Column(Float)
    fgm = Column(Float)
    fga = Column(Float)
    ftm = Column(Float)
    fta = Column(Float)
    tov = Column(Float)

    __table_args__ = (
        UniqueConstraint("player_id", "game_date"),
    )


class FantasyTeam(Base):
    __tablename__ = "fantasy_teams"

    id = Column(String(20), primary_key=True)
    name = Column(String(100))
    owner = Column(String(100), nullable=True)
    is_my_team = Column(Boolean, default=False)


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    fantasy_team_id = Column(String(20), ForeignKey("fantasy_teams.id"), nullable=True)
    salary = Column(Float, nullable=False)
    contract_year = Column(String(10))
    years_remaining = Column(Integer, nullable=True)
    is_expiring = Column(Boolean, default=False)

    player = relationship("Player", back_populates="contracts")


class RosterEntry(Base):
    __tablename__ = "roster_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fantasy_team_id = Column(String(20), ForeignKey("fantasy_teams.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    roster_slot = Column(String(10))
    status = Column(String(10))
    as_of_date = Column(Date)

    player = relationship("Player", back_populates="roster_entries")

    __table_args__ = (
        UniqueConstraint("fantasy_team_id", "player_id", "as_of_date"),
    )


class Matchup(Base):
    __tablename__ = "matchups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scoring_period = Column(Integer)
    team_a_id = Column(String(20), ForeignKey("fantasy_teams.id"))
    team_b_id = Column(String(20), ForeignKey("fantasy_teams.id"))
    season = Column(String(10))
    team_a_cats_won = Column(Integer, nullable=True)
    team_b_cats_won = Column(Integer, nullable=True)


class FreeAgent(Base):
    __tablename__ = "free_agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    as_of_date = Column(Date)
    salary = Column(Float, default=1.0)

    __table_args__ = (
        UniqueConstraint("player_id", "as_of_date"),
    )


class Injury(Base):
    __tablename__ = "injuries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    status = Column(String(20))
    description = Column(Text, nullable=True)
    return_date = Column(Date, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class NBAScheduleGame(Base):
    __tablename__ = "nba_schedule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_date = Column(Date)
    home_team = Column(String(5))
    away_team = Column(String(5))
    scoring_period = Column(Integer, nullable=True)

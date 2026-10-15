from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "ipl.db"


def build_database() -> Path:
    if not RAW_DIR.exists():
        raise FileNotFoundError(f"Raw data directory not found: {RAW_DIR}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        for csv_name in ["matches.csv", "deliveries.csv", "players.csv", "teams.csv", "venues.csv"]:
            csv_path = RAW_DIR / csv_name
            if not csv_path.exists():
                raise FileNotFoundError(f"Missing raw file: {csv_path}")
            table_name = csv_path.stem
            df = pd.read_csv(csv_path)
            df.to_sql(table_name, conn, if_exists="replace", index=False)

        conn.execute("DROP TABLE IF EXISTS matches_clean")
        conn.execute(
            """
            CREATE TABLE matches_clean AS
            SELECT
                match_id,
                COALESCE(NULLIF(TRIM(venue), ''), 'Unknown Venue') AS venue_clean,
                COALESCE(NULLIF(TRIM(city), ''), 'Unknown City') AS city_clean,
                CAST(season_id AS INTEGER) AS season_id,
                team1,
                team2,
                result,
                match_winner,
                player_of_match,
                toss_winner,
                toss_decision
            FROM matches
            """
        )

        conn.execute("DROP VIEW IF EXISTS v_ball")
        conn.execute(
            """
            CREATE VIEW v_ball AS
            SELECT
                d.*,
                CASE
                    WHEN d.over_number <= 5 THEN 'Powerplay'
                    WHEN d.over_number <= 14 THEN 'Middle'
                    ELSE 'Death'
                END AS phase,
                CASE
                    WHEN d.is_wide_ball = 0 AND d.is_no_ball = 0 THEN 1
                    ELSE 0
                END AS is_legal,
                d.total_runs - d.bye_runs - d.leg_bye_runs - d.penalty_runs AS bowler_runs,
                CASE
                    WHEN d.is_wicket = 1 AND d.wicket_kind NOT IN (
                        'run out', 'retired hurt', 'retired out', 'obstructing the field'
                    ) THEN 1
                    ELSE 0
                END AS bowler_wicket
            FROM deliveries d
            WHERE d.is_super_over = 0
            """
        )

        conn.execute("DROP VIEW IF EXISTS v_innings")
        conn.execute(
            """
            CREATE VIEW v_innings AS
            SELECT
                match_id,
                innings,
                MIN(batting_team) AS batting_team,
                MIN(bowling_team) AS bowling_team,
                SUM(total_runs) AS runs,
                SUM(is_wicket) AS wickets,
                SUM(is_legal) AS legal_balls
            FROM v_ball
            WHERE innings IN (1, 2)
            GROUP BY match_id, innings
            """
        )

        conn.execute("DROP VIEW IF EXISTS v_match_totals")
        conn.execute(
            """
            CREATE VIEW v_match_totals AS
            SELECT
                m.*,
                i1.runs AS first_innings_runs,
                i1.batting_team AS bat_first_team,
                CASE WHEN m.match_winner = i1.batting_team THEN 0 ELSE 1 END AS chase_won
            FROM matches_clean m
            JOIN v_innings i1
              ON i1.match_id = m.match_id
             AND i1.innings = 1
            WHERE m.result = 'win'
            """
        )

    return DB_PATH


if __name__ == "__main__":
    build_database()
    print(f"Built database at {DB_PATH}")

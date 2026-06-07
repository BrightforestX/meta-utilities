"""Load OASIS SQLite outputs into pandas dataframes for analysis.

OASIS persists the entire simulation to a single SQLite file. Tables include
(varies by platform): user, post, comment, like, dislike, follow, mute, trace.
The `trace` table holds the per-step action log — that is what we mine.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def list_tables(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]


def load_table(db_path: Path, name: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(f"SELECT * FROM {name}", conn)


def cascade_series(db_path: Path, post_id: int = 1) -> pd.Series:
    """Return I(t) — number of unique agents who have engaged with `post_id`
    by step t. 'Engaged' = liked, commented on, or reposted."""
    with sqlite3.connect(db_path) as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        frames = []
        for t in ("like", "comment", "repost"):
            if t in tables:
                frames.append(pd.read_sql_query(
                    f"SELECT user_id, post_id, created_at FROM {t}", conn
                ))
        if not frames:
            raise RuntimeError(f"No engagement tables in {db_path}")
        all_engage = pd.concat(frames, ignore_index=True)

    rel = all_engage[all_engage["post_id"] == post_id].copy()
    rel = rel.sort_values("created_at").drop_duplicates("user_id", keep="first")
    rel["step"] = pd.to_numeric(rel["created_at"], errors="coerce").fillna(0).astype(int)
    counts = rel.groupby("step").size().cumsum()
    return counts.reindex(range(counts.index.max() + 1 if len(counts) else 1), method="ffill").fillna(0)


def event_times(db_path: Path, post_id: int = 1) -> list[float]:
    """Flat list of event timestamps for Hawkes fitting."""
    with sqlite3.connect(db_path) as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        frames = []
        for t in ("like", "comment", "repost"):
            if t in tables:
                frames.append(pd.read_sql_query(
                    f"SELECT created_at FROM {t} WHERE post_id = {int(post_id)}", conn
                ))
    if not frames:
        return []
    df = pd.concat(frames, ignore_index=True)
    return sorted(pd.to_numeric(df["created_at"], errors="coerce").dropna().astype(float).tolist())


def engagement_outcomes(db_path: Path, post_id: int = 1) -> tuple[int, int]:
    """(successes, trials) for Bayesian A/B: trials = total users, successes
    = users who engaged with post_id."""
    with sqlite3.connect(db_path) as conn:
        n_users = int(conn.execute("SELECT COUNT(*) FROM user").fetchone()[0])
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        users = set()
        for t in ("like", "comment", "repost"):
            if t in tables:
                rows = conn.execute(
                    f"SELECT DISTINCT user_id FROM {t} WHERE post_id = ?", (post_id,)
                ).fetchall()
                users.update(r[0] for r in rows)
    return len(users), n_users

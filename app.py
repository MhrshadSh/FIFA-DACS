from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, url_for


app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key-change-me"

DATA_DIR = Path(__file__).parent / "data"
DATA_FILE = DATA_DIR / "league.json"


@dataclass
class Standing:
    name: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0
    points: int = 0


def empty_league() -> dict[str, Any]:
    return {"name": "", "players": [], "fixtures": []}


def load_league() -> dict[str, Any]:
    if not DATA_FILE.exists():
        return empty_league()

    with DATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_league(league: dict[str, Any]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(league, file, indent=2)


def normalize_players(raw_players: str) -> list[str]:
    players = []
    seen = set()

    for line in raw_players.splitlines():
        name = " ".join(line.strip().split())
        key = name.casefold()
        if name and key not in seen:
            players.append(name)
            seen.add(key)

    return players


def generate_fixtures(players: list[str]) -> list[dict[str, Any]]:
    fixtures = []
    round_number = 1

    for home_index, home_player in enumerate(players):
        for away_player in players[home_index + 1 :]:
            fixtures.append(
                {
                    "id": str(uuid4()),
                    "round": round_number,
                    "home": home_player,
                    "away": away_player,
                    "home_score": None,
                    "away_score": None,
                }
            )
            round_number += 1

    return fixtures


def calculate_table(league: dict[str, Any]) -> list[Standing]:
    table = {player: Standing(name=player) for player in league["players"]}

    for fixture in league["fixtures"]:
        home_score = fixture.get("home_score")
        away_score = fixture.get("away_score")
        if home_score is None or away_score is None:
            continue

        home = table[fixture["home"]]
        away = table[fixture["away"]]

        home.played += 1
        away.played += 1
        home.goals_for += home_score
        home.goals_against += away_score
        away.goals_for += away_score
        away.goals_against += home_score

        if home_score > away_score:
            home.won += 1
            away.lost += 1
            home.points += 3
        elif away_score > home_score:
            away.won += 1
            home.lost += 1
            away.points += 3
        else:
            home.drawn += 1
            away.drawn += 1
            home.points += 1
            away.points += 1

    for standing in table.values():
        standing.goal_difference = standing.goals_for - standing.goals_against

    return sorted(
        table.values(),
        key=lambda item: (
            item.points,
            item.goal_difference,
            item.goals_for,
            item.name.casefold(),
        ),
        reverse=True,
    )


def fixture_counts(league: dict[str, Any]) -> tuple[int, int]:
    played = sum(
        1
        for fixture in league["fixtures"]
        if fixture.get("home_score") is not None and fixture.get("away_score") is not None
    )
    return played, len(league["fixtures"])


@app.route("/")
def index():
    league = load_league()
    played, total = fixture_counts(league)
    return render_template(
        "index.html",
        league=league,
        standings=calculate_table(league),
        played=played,
        total=total,
    )


@app.route("/setup", methods=["GET", "POST"])
def setup():
    league = load_league()

    if request.method == "POST":
        league_name = request.form.get("league_name", "").strip()
        players = normalize_players(request.form.get("players", ""))

        if not league_name:
            flash("Give your league a name before creating fixtures.", "error")
        elif len(players) < 2:
            flash("Add at least two players to create a league.", "error")
        else:
            league = {
                "name": league_name,
                "players": players,
                "fixtures": generate_fixtures(players),
            }
            save_league(league)
            flash("League created and fixtures generated.", "success")
            return redirect(url_for("index"))

    return render_template("setup.html", league=league)


@app.route("/fixtures")
def fixtures():
    league = load_league()
    if not league["players"]:
        return redirect(url_for("setup"))

    return render_template("fixtures.html", league=league)


@app.route("/fixtures/<fixture_id>/result", methods=["POST"])
def save_result(fixture_id: str):
    league = load_league()
    fixture = next(
        (item for item in league["fixtures"] if item["id"] == fixture_id),
        None,
    )

    if fixture is None:
        flash("Fixture could not be found.", "error")
        return redirect(url_for("fixtures"))

    try:
        home_score = int(request.form.get("home_score", ""))
        away_score = int(request.form.get("away_score", ""))
        if home_score < 0 or away_score < 0:
            raise ValueError
    except ValueError:
        flash("Scores must be whole numbers of 0 or higher.", "error")
        return redirect(url_for("fixtures"))

    fixture["home_score"] = home_score
    fixture["away_score"] = away_score
    save_league(league)
    flash("Result saved and league table updated.", "success")
    return redirect(url_for("fixtures"))


@app.route("/fixtures/<fixture_id>/clear", methods=["POST"])
def clear_result(fixture_id: str):
    league = load_league()
    fixture = next(
        (item for item in league["fixtures"] if item["id"] == fixture_id),
        None,
    )

    if fixture is not None:
        fixture["home_score"] = None
        fixture["away_score"] = None
        save_league(league)
        flash("Result cleared.", "success")

    return redirect(url_for("fixtures"))


@app.route("/reset", methods=["POST"])
def reset():
    save_league(empty_league())
    flash("League reset. You can create a new one now.", "success")
    return redirect(url_for("setup"))


if __name__ == "__main__":
    app.run(debug=False)

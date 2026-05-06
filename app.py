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
DATA_FILE = DATA_DIR / "leagues.json"
OLD_DATA_FILE = DATA_DIR / "league.json"

LEAGUE_TYPES = {
    "1v1": "1v1",
    "2v2": "2v2",
}


@dataclass
class Standing:
    name: str
    players: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0
    points: int = 0


def empty_store() -> dict[str, Any]:
    return {"leagues": []}


def load_store() -> dict[str, Any]:
    if DATA_FILE.exists():
        with DATA_FILE.open("r", encoding="utf-8") as file:
            return json.load(file)

    if OLD_DATA_FILE.exists():
        with OLD_DATA_FILE.open("r", encoding="utf-8") as file:
            old_league = json.load(file)
        if old_league.get("players"):
            return {"leagues": [migrate_old_league(old_league)]}

    return empty_store()


def save_store(store: dict[str, Any]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(store, file, indent=2)


def migrate_old_league(old_league: dict[str, Any]) -> dict[str, Any]:
    participants = [
        {"id": str(uuid4()), "name": player, "players": [player]}
        for player in old_league.get("players", [])
    ]
    participant_ids = {participant["name"]: participant["id"] for participant in participants}
    fixtures = []

    for fixture in old_league.get("fixtures", []):
        if fixture.get("home") not in participant_ids or fixture.get("away") not in participant_ids:
            continue
        fixtures.append(
            {
                "id": str(uuid4()),
                "round": fixture.get("round", len(fixtures) + 1),
                "home_id": participant_ids[fixture["home"]],
                "away_id": participant_ids[fixture["away"]],
                "home_score": fixture.get("home_score"),
                "away_score": fixture.get("away_score"),
            }
        )

    return {
        "id": str(uuid4()),
        "name": old_league.get("name", "Imported League"),
        "type": "1v1",
        "participants": participants,
        "fixtures": fixtures,
    }


def get_league(store: dict[str, Any], league_id: str) -> dict[str, Any] | None:
    return next((league for league in store["leagues"] if league["id"] == league_id), None)


def normalize_name(value: str) -> str:
    return " ".join(value.strip().split())


def participant_label(participant: dict[str, Any]) -> str:
    return participant["name"]


def parse_1v1_participants(raw_players: str) -> list[dict[str, Any]]:
    participants = []
    seen = set()

    for line in raw_players.splitlines():
        name = normalize_name(line)
        key = name.casefold()
        if name and key not in seen:
            participants.append({"id": str(uuid4()), "name": name, "players": [name]})
            seen.add(key)

    return participants


def parse_2v2_participants(raw_teams: str) -> list[dict[str, Any]]:
    participants = []
    seen = set()

    for line in raw_teams.splitlines():
        names = [normalize_name(item) for item in line.replace("&", "/").split("/")]
        players = [name for name in names if name]
        if len(players) != 2:
            continue

        team_name = f"{players[0]} / {players[1]}"
        key = team_name.casefold()
        if key not in seen:
            participants.append({"id": str(uuid4()), "name": team_name, "players": players})
            seen.add(key)

    return participants


def parse_participants(league_type: str, raw_participants: str) -> list[dict[str, Any]]:
    if league_type == "2v2":
        return parse_2v2_participants(raw_participants)
    return parse_1v1_participants(raw_participants)


def build_participant(league_type: str, form: Any) -> dict[str, Any] | None:
    if league_type == "2v2":
        player_one = normalize_name(form.get("player_one", ""))
        player_two = normalize_name(form.get("player_two", ""))
        if not player_one or not player_two:
            return None
        return {
            "id": str(uuid4()),
            "name": f"{player_one} / {player_two}",
            "players": [player_one, player_two],
        }

    player_name = normalize_name(form.get("player_name", ""))
    if not player_name:
        return None
    return {"id": str(uuid4()), "name": player_name, "players": [player_name]}


def participant_exists(league: dict[str, Any], participant: dict[str, Any]) -> bool:
    new_key = participant["name"].casefold()
    return any(item["name"].casefold() == new_key for item in league["participants"])


def make_fixture(home_id: str, away_id: str, round_number: int) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "round": round_number,
        "home_id": home_id,
        "away_id": away_id,
        "home_score": None,
        "away_score": None,
    }


def generate_fixtures(participants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fixtures = []
    round_number = 1

    for home_index, home_participant in enumerate(participants):
        for away_participant in participants[home_index + 1 :]:
            fixtures.append(
                make_fixture(home_participant["id"], away_participant["id"], round_number)
            )
            round_number += 1

    return fixtures


def add_participant_fixtures(league: dict[str, Any], participant: dict[str, Any]) -> None:
    next_round = max((fixture["round"] for fixture in league["fixtures"]), default=0) + 1
    for opponent in league["participants"]:
        if opponent["id"] == participant["id"]:
            continue
        league["fixtures"].append(make_fixture(participant["id"], opponent["id"], next_round))
        next_round += 1


def participant_map(league: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {participant["id"]: participant for participant in league["participants"]}


def decorate_fixtures(league: dict[str, Any]) -> list[dict[str, Any]]:
    participants = participant_map(league)
    decorated = []

    for fixture in league["fixtures"]:
        home = participants.get(fixture["home_id"])
        away = participants.get(fixture["away_id"])
        if home is None or away is None:
            continue
        decorated.append({**fixture, "home": participant_label(home), "away": participant_label(away)})

    return decorated


def calculate_table(league: dict[str, Any]) -> list[Standing]:
    participants = participant_map(league)
    table = {
        participant_id: Standing(
            name=participant_label(participant),
            players=", ".join(participant["players"]),
        )
        for participant_id, participant in participants.items()
    }

    for fixture in league["fixtures"]:
        home_score = fixture.get("home_score")
        away_score = fixture.get("away_score")
        home_id = fixture.get("home_id")
        away_id = fixture.get("away_id")
        if (
            home_score is None
            or away_score is None
            or home_id not in table
            or away_id not in table
        ):
            continue

        home = table[home_id]
        away = table[away_id]

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
    store = load_store()
    league_cards = []

    for league in store["leagues"]:
        played, total = fixture_counts(league)
        league_cards.append(
            {
                "league": league,
                "played": played,
                "total": total,
                "leader": calculate_table(league)[0] if league["participants"] else None,
            }
        )

    return render_template("index.html", league_cards=league_cards)


@app.route("/leagues/new", methods=["GET", "POST"])
def setup():
    if request.method == "POST":
        store = load_store()
        league_name = normalize_name(request.form.get("league_name", ""))
        league_type = request.form.get("league_type", "1v1")
        raw_participants = request.form.get("participants", "")
        participants = parse_participants(league_type, raw_participants)

        if league_type not in LEAGUE_TYPES:
            flash("Choose a valid league type.", "error")
        elif not league_name:
            flash("Give your league a name before creating fixtures.", "error")
        elif len(participants) < 2:
            flash("Add at least two players or two 2v2 teams.", "error")
        else:
            league = {
                "id": str(uuid4()),
                "name": league_name,
                "type": league_type,
                "participants": participants,
                "fixtures": generate_fixtures(participants),
            }
            store["leagues"].append(league)
            save_store(store)
            flash("League created and fixtures generated.", "success")
            return redirect(url_for("league_table", league_id=league["id"]))

    return render_template("setup.html")


@app.route("/leagues/<league_id>")
def league_table(league_id: str):
    store = load_store()
    league = get_league(store, league_id)
    if league is None:
        flash("League could not be found.", "error")
        return redirect(url_for("index"))

    played, total = fixture_counts(league)
    return render_template(
        "league.html",
        league=league,
        standings=calculate_table(league),
        played=played,
        total=total,
    )


@app.route("/leagues/<league_id>/fixtures")
def fixtures(league_id: str):
    store = load_store()
    league = get_league(store, league_id)
    if league is None:
        flash("League could not be found.", "error")
        return redirect(url_for("index"))

    return render_template("fixtures.html", league=league, fixtures=decorate_fixtures(league))


@app.route("/leagues/<league_id>/fixtures/<fixture_id>/result", methods=["POST"])
def save_result(league_id: str, fixture_id: str):
    store = load_store()
    league = get_league(store, league_id)
    if league is None:
        flash("League could not be found.", "error")
        return redirect(url_for("index"))

    fixture = next(
        (item for item in league["fixtures"] if item["id"] == fixture_id),
        None,
    )

    if fixture is None:
        flash("Fixture could not be found.", "error")
        return redirect(url_for("fixtures", league_id=league_id))

    try:
        home_score = int(request.form.get("home_score", ""))
        away_score = int(request.form.get("away_score", ""))
        if home_score < 0 or away_score < 0:
            raise ValueError
    except ValueError:
        flash("Scores must be whole numbers of 0 or higher.", "error")
        return redirect(url_for("fixtures", league_id=league_id))

    fixture["home_score"] = home_score
    fixture["away_score"] = away_score
    save_store(store)
    flash("Result saved and league table updated.", "success")
    return redirect(url_for("fixtures", league_id=league_id))


@app.route("/leagues/<league_id>/fixtures/<fixture_id>/clear", methods=["POST"])
def clear_result(league_id: str, fixture_id: str):
    store = load_store()
    league = get_league(store, league_id)
    if league is None:
        flash("League could not be found.", "error")
        return redirect(url_for("index"))

    fixture = next(
        (item for item in league["fixtures"] if item["id"] == fixture_id),
        None,
    )

    if fixture is not None:
        fixture["home_score"] = None
        fixture["away_score"] = None
        save_store(store)
        flash("Result cleared.", "success")

    return redirect(url_for("fixtures", league_id=league_id))


@app.route("/leagues/<league_id>/participants", methods=["POST"])
def add_participant(league_id: str):
    store = load_store()
    league = get_league(store, league_id)
    if league is None:
        flash("League could not be found.", "error")
        return redirect(url_for("index"))

    participant = build_participant(league["type"], request.form)
    if participant is None:
        flash("Enter a valid player or 2v2 team.", "error")
    elif participant_exists(league, participant):
        flash("That player or team is already in this league.", "error")
    else:
        league["participants"].append(participant)
        add_participant_fixtures(league, participant)
        save_store(store)
        flash("Participant added with fresh fixtures.", "success")

    return redirect(url_for("league_table", league_id=league_id))


@app.route("/leagues/<league_id>/participants/<participant_id>/remove", methods=["POST"])
def remove_participant(league_id: str, participant_id: str):
    store = load_store()
    league = get_league(store, league_id)
    if league is None:
        flash("League could not be found.", "error")
        return redirect(url_for("index"))

    original_count = len(league["participants"])
    league["participants"] = [
        participant
        for participant in league["participants"]
        if participant["id"] != participant_id
    ]
    league["fixtures"] = [
        fixture
        for fixture in league["fixtures"]
        if fixture["home_id"] != participant_id and fixture["away_id"] != participant_id
    ]

    if len(league["participants"]) == original_count:
        flash("Participant could not be found.", "error")
    else:
        save_store(store)
        flash("Participant removed. Only their fixtures and results were removed.", "success")

    return redirect(url_for("league_table", league_id=league_id))


@app.route("/leagues/<league_id>/delete", methods=["POST"])
def delete_league(league_id: str):
    store = load_store()
    before = len(store["leagues"])
    store["leagues"] = [league for league in store["leagues"] if league["id"] != league_id]

    if len(store["leagues"]) == before:
        flash("League could not be found.", "error")
    else:
        save_store(store)
        flash("League deleted.", "success")

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=False)

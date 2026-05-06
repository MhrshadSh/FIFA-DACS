# FIFA League Tracker

A small Flask web application for setting up FIFA leagues, generating fixtures, entering results, and tracking live league tables.

## Run

```bash
python3 app.py
```

Then open `http://127.0.0.1:5000`.

## Features

- Create a named league with any number of players.
- Create multiple leagues and open them from a league list.
- Choose between 1v1 player leagues and 2v2 team leagues.
- Generate one fixture for every pair of players or teams.
- Add or update scores for each fixture.
- Clear a result if it was entered by mistake.
- Add players or 2v2 teams while a league is running and generate only their new fixtures.
- Remove players or teams while preserving all unrelated results.
- Automatically update standings with played, wins, draws, losses, goals, goal difference, and points.
- Persist league data in `data/leagues.json`.

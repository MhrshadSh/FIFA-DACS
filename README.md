# FIFA League Tracker

A small Flask web application for setting up a FIFA league, generating fixtures, entering results, and tracking the league table.

## Run

```bash
python3 app.py
```

Then open `http://127.0.0.1:5000`.

## Features

- Create a named league with any number of players.
- Generate one fixture for every pair of players.
- Add or update scores for each fixture.
- Clear a result if it was entered by mistake.
- Automatically update standings with played, wins, draws, losses, goals, goal difference, and points.
- Persist league data in `data/league.json`.

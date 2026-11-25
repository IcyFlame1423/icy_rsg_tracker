# MCSR RSG Tracker

A run tracker and stats dashboard for Minecraft 1.16.1 random seed speedruns (RSG).

It reads the records the [SpeedRunIGT](https://github.com/RedLime/SpeedRunIGT) mod already saves for
every world you play, and turns them into a run history and statistics: split times, nethers per hour,
resets, sessions, deaths and more. It runs alongside the game in your browser. It isn't a mod, so it
can't affect your runs or make them unverifiable.

## What you get

- **Dashboard:** nethers per hour, runs played, total resets (including wall resets), average nether,
  completions, split progression, split times, and your latest runs.
- **Runs:** every run with its splits, filterable (reached split, result, deaths), with any of the
  80 advancements as extra columns. **View** opens a run's own page.
- **Run page:** each split against your average (all time or that session), segment times, an estimate
  of key resources (blaze rods, pearls, beds, respawn anchors, fire resistance, obsidian),
  deaths, and achievements in the order you got them.
- **Sessions:** trends across sessions (nethers per hour, runs, resets per nether, average split
  times), and each session's timeline.
- **Splits:** one split in depth: distribution, over time, top 10, from the start of the run or from
  the previous split.
- **CSV files** you can open in Excel or Google Sheets (see [Output](#output)).

Split icons are drawn from your own copy of Minecraft (nothing of Mojang's is included here).

## Requirements

- Windows.
- Minecraft 1.16.1 with **SpeedRunIGT** and **Atum** (RSG worlds named `Random Speedrun #N`).
  **SeedQueue** works and is what wall resets are counted from; without it, you just get no wall
  resets.
- One instance at a time. Multi-instance walls (several instances playing at once) aren't supported yet:
  every instance names its worlds the same way, so their runs can't be told apart.
- Prism Launcher or MultiMC are found automatically. Other launchers work too: set the instance's
  `.minecraft` folder in Settings.

## Install

1. Download `MCSR Tracker.exe` from the [Releases](../../releases) page.
2. Put it in a folder of its own (it keeps its settings and data next to itself).
3. Double-click it. It opens the dashboard in your browser at http://127.0.0.1:8765/.
   Windows may warn that the app is unrecognized, because it isn't signed. Click **More info**, then
   **Run anyway**.
4. Keep the window open while you play; close it to stop tracking.

On the first start it finds your RSG instance (one with Atum installed) and imports every run
SpeedRunIGT has recorded. If it can't find the instance, the status bar says so: open **Settings**,
click **Detect instances** or enter the instance's `.minecraft` folder.

### From source

Needs Python 3.11 or newer, with no other packages. Download the repository and double-click
`track.bat`, or run `python -m mcsr_tracker`.

## What it reads, and what it doesn't do

It only reads files; it never changes the game, your worlds or SpeedRunIGT's records.

- SpeedRunIGT's records (`%USERPROFILE%\speedrunigt\records`): splits, advancements, item statistics.
- The instance's game logs: to tell death resets from accidental deaths, and when each death happened.
- The instance's `usercache.json`: your username, for the top bar.
- Your Minecraft game file (the 1.16.1 client jar the launcher downloaded): the icon textures.

The dashboard is only reachable from your own PC (it listens on 127.0.0.1). The one thing it fetches
from the internet is your skin, from Mojang's servers, for the player head. It's cached, so it shows
offline too.

## How the numbers work

- **Splits** come from SpeedRunIGT's timeline: nether, bastion, fortress, blind, stronghold, end,
  finish. Bastion and fortress can come in either order, so progression stats use **Structure 1** and
  **Structure 2**: the first and second one entered.
- **Wall resets:** SeedQueue numbers every world it creates, played or not. The jump in world number
  between the runs you played is how many worlds you reset on the wall.
  Total resets = worlds generated - completions.
- **Sessions:** a break longer than 30 minutes (adjustable) starts a new session. Nethers per hour use
  real time across the session.
- **Deaths:** with a respawn point (bed or anchor: a death reset) or without (back to world spawn),
  from the game log.
- **Resources** (run page) come from the game's item statistics: picked up minus dropped. Deaths make
  these estimates, because picking your items back up counts them again; the run page's **Learn more**
  explains the assumptions.
- A run where the world was opened to LAN with cheats keeps only what happened before cheats were turned
  on. Runs with cheats on from the start are ignored.

## Output

Written to `data\<instance>\`:

- `runs.csv`: one row per run: splits, result (finished/reset), deaths, and every advancement.
- `sessions.csv`: one row per session with its stats.
- `stats.csv`: every stat for all time, the last session, the last 7 days and the last 30 days.

If a CSV is open in Excel, the tracker can't update it; it tries again once you close it.

## Settings

Use the app's **Settings** page, which writes `config.toml` next to the app. You can also copy
`config.example.toml` to `config.toml` and edit it.

## Command line

```
python -m mcsr_tracker                   # dashboard + tracking (same as `app`)
python -m mcsr_tracker app --no-browser  # options: --port N, --no-tracker (view only)
python -m mcsr_tracker watch             # tracking only, console output
python -m mcsr_tracker import            # one-off update
python -m mcsr_tracker import --rebuild  # rebuild from the records folder (old file kept as runs.csv.bak)
python -m unittest discover -s tests -t .
```

The .exe takes the same commands, e.g. `"MCSR Tracker.exe" import --rebuild`.

## Building the .exe

Run `build.bat` (needs Python 3.11+). It installs PyInstaller into its own `.build-venv` folder and
writes `dist\MCSR Tracker.exe`.

## License

[MIT](LICENSE)

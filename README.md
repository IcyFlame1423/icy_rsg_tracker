# Icy RSG Tracker

A run tracker and stats dashboard for Minecraft 1.16.1 random seed speedruns (RSG).

It reads the records the [SpeedRunIGT](https://github.com/RedLime/SpeedRunIGT) mod already saves for
every world you play, and turns them into a run history and statistics: split times, nethers per hour,
resets, sessions, deaths and more. It runs alongside the game in your browser. It isn't a mod, so it
can't affect your runs or make them unverifiable.

## What you get

- **Dashboard:** nethers per hour, runs played, total resets (including wall resets), average nether,
  completions, split progression, split times, and your latest runs.
- **Runs:** every run with its splits, filterable by the split they reached, with any of the
  80 advancements as extra columns. **View** opens a run's own page.
- **Run page:** each split against your average (all time or that session), segment times, key items
  obtained (blaze rods, pearls, beds, respawn anchors, fire resistance, obsidian), the seed if you
  typed `/seed`, a breakdown of each part of the run (structures looted, raw materials at nether
  enter, distances travelled, blaze rate, blind accuracy, eyes placed in the portal,
  beds used in the End), deaths, and advancements in the order you got them. Items, the seed and
  the breakdown need the Hermes mod. Finished Hermes runs also get a **score**: the seconds lost against a
  top player on the same seed (fitted on MCSR Ranked's top players, allowing for distances and
  resource shortages), with a page showing how it's worked out. The score uses data from the
  [MCSR Ranked](https://mcsrranked.com) API (top-player times), Couriway's 100K tracker (structureless
  overworld) and T_Wagz's End fight time analysis (End fights with 2 explosives or fewer).
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

1. Download `icy_rsg_tracker.exe` from the [Releases](../../releases) page.
2. Put it in a folder of its own (it keeps its settings and data next to itself).
3. Double-click it. It opens the dashboard in your browser at http://127.0.0.1:8765/.
   Windows may warn that the app is unrecognized, because it isn't signed. Click **More info**, then
   **Run anyway**.
4. It runs in the background, without a window of its own. Keep the dashboard tab open while you
   play. To stop tracking, press **Stop tracking** at the top of the dashboard, or close the tab.
   Opening the exe again while it's running just opens the dashboard.

On the first start it finds your RSG instance (one with Atum installed) and imports every run
SpeedRunIGT has recorded. If it can't find the instance, the status bar says so: open **Settings**,
click **Detect instances** or enter the instance's `.minecraft` folder.

### From source

Needs Python 3.11 or newer, with no other packages. Download the repository and double-click
`track.bat`, or run `python -m icy_rsg_tracker`.

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
- **Items and seed** (run page) need the [Hermes](https://github.com/DuncanRuns/Hermes) mod, which
  saves a play log in each world when you leave it. Items are counted from your inventory as it
  changed: items picked back up after a death or a drop, put in a chest and taken out again, or
  placed and broken again aren't counted twice. Blaze rods only count from blazes. Runs played
  without Hermes have no item counts. The tracker never reads the ciphered live copy of the log.
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
python -m icy_rsg_tracker                   # dashboard + tracking (same as `app`)
python -m icy_rsg_tracker app --no-browser  # options: --port N, --no-tracker (view only)
python -m icy_rsg_tracker watch             # tracking only, console output
python -m icy_rsg_tracker import            # one-off update
python -m icy_rsg_tracker import --rebuild  # rebuild from the records folder (old file kept as runs.csv.bak)
python -m unittest discover -s tests -t .
```

The .exe takes the same commands, e.g. `"icy_rsg_tracker.exe" import --rebuild`. It has no console, so
what it prints goes to `tracker.log` next to it (the same happens with `track.bat`).

## Building the .exe

Run `build.bat` (needs Python 3.11+). It installs PyInstaller into its own `.build-venv` folder and
writes `dist\icy_rsg_tracker.exe`.

## License

[MIT](LICENSE)

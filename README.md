<p align="center">
  <img src="assets/Tacticfy.ico" width="96" alt="Tacticfy icon">
</p>

<h1 align="center">Tacticfy</h1>

<p align="center">
  A native Windows desktop app for <b>Football Manager 27</b> that reads your squad and builds the tactic around it.<br>
  <a href="https://tacticfyhelp.github.io/Tacticfy/">tacticfyhelp.github.io/Tacticfy</a>
</p>

---

## What Tacticfy does

Tacticfy reads your squad straight from a running FM27 save (or from an imported squad file) and works out:

- **Best formation** – scores every supported formation against your squad and picks the one your players fit best (or lock one yourself).
- **Dual-phase roles** – FM27 gives each player an *In Possession* and an *Out of Possession* role. Tacticfy assigns both per slot, using the official FM27 role names so you can copy them 1:1.
- **Team & Player Instructions** – the matching team instruction tiles and per-player instructions for your chosen style (High-Scoring Attacking, Proactive Possession, Balanced Tactical Meta, Fluid Counter-Attack or Defensive Solidity), using the exact FM27 tile names.
- **Best XI, Second XI and Drop-Off** – who starts, who rotates, and where the quality drops off.
- **Matchday bench** – a 7 or 9-man bench with a backup keeper and cover for every line, plus planned substitutions (chase a goal, protect a lead, fresh legs) with minute windows.
- **Individual training** – role focus, additional focus and training intensity for every player, based on attribute gaps, age, potential and personality.
- **Squad transfer advisor** – Core / Rotation / Loan / Sell High / Sell, plus the weakest link in your starting XI.

### New in v1.1.0

- **FM Meta vs Balanced scoring** – the default *FM Meta* mode adds extra weight to the attributes the FM match engine rewards most (Pace, Acceleration, Jumping Reach, Anticipation, Concentration, Dribbling, Agility, Balance, Decisions; for goalkeepers Reflexes, Agility, One On Ones, Aerial Reach) on top of each role's own attributes. *Balanced* uses the role weights only.
- **"Why this XI?"** – click any player on the pitch to see their top contributing attributes and why they beat the runner-up for that slot (for example *+1.8 Current Ability, +0.9 Pace/Acceleration, +0.8 Decisions*). The Match Plan now opens with the **Top 3 evaluated formations** and their synergy scores, so you can see why the recommended shape won.
- **Live fitness & Exclude** – Match Sharpness and Fatigue are read live from FM27. With **Factor in Fitness** on (the default), unsharp or tired players are penalized and flagged with a warning on the pitch and the bench. Tick **Exclude** next to **Lock XI** on the Squad tab to leave out injured, suspended or rested players – Best XI, Second XI and bench re-optimize instantly.
- **Opponent Matchup** – *Neutral*, *Favorite vs Low Block*, *Underdog vs Stronger*, *vs Fast Counter* or *vs Aerial / Direct*. Each one re-weights what Tacticfy looks for in defenders, midfielders and attackers (faster centre-backs vs a fast counter, better Jumping Reach vs a direct side, more Flair/Dribbling/Off The Ball/Vision vs a low block, more Work Rate/Positioning/Concentration as the underdog) and adapts the FM27 Team Instructions.

Scoring Mode, Matchup and Factor in Fitness sit in a compact bar on the Tactics tab and re-optimize as soon as you change them.

Tacticfy is a native Windows desktop application (PySide6 / Qt) with Apple-style Light and Dark themes. It runs entirely on your PC – no browser and no account, and nothing is sent online unless you choose to report a bug.

Languages: English and Hebrew (right-to-left) – switch any time with the **Lang: EN / עב** button next to **Theme**.

## Easy installation (no Python required)

1. Go to the **[Releases](https://github.com/tacticfyhelp/Tacticfy/releases)** page.
2. Download **`TacticfySetup.exe`** from the latest release.
3. Run it and install like any standard Windows app. It adds Start Menu and (optionally) Desktop shortcuts and a normal uninstaller.
4. Start FM27, load your save, open the **Squad** screen, then click **Load from FM27** in Tacticfy.

> Windows SmartScreen may warn about an unrecognised app because the installer is not code-signed. Click **More info → Run anyway**.

Your logs and any offsets you calibrate yourself are stored in `%LOCALAPPDATA%\Tacticfy\`, so nothing is written to `Program Files`.

## FM27 patch policy

Live reading depends on memory offsets for the **current FM27 patch**, stored in [`config/offsets.json`](config/offsets.json).
FM27 updates can move those offsets, and then **Load from FM27** fails (for example *"Squad array signature not found"*).

- Whenever a new FM27 patch breaks live reading, an **updated release will be published on GitHub** – just install the new `TacticfySetup.exe` over the old one.
- Until then you can still use **Import**, or try **Calibrate** (In-Game Editor values) in the app. A user calibration is saved to `%LOCALAPPDATA%\Tacticfy\offsets.json` and is ignored automatically after you update to a newer release.
- Please report broken patches with the **Report Bug** button (or the [bug report form](https://github.com/tacticfyhelp/Tacticfy/issues/new?template=bug_report.md)) and include your FM27 version.

## Reporting bugs

Click **Report Bug** in the top-right of the toolbar. It opens a GitHub issue pre-filled with your Windows version, the Tacticfy version and the last 20 log lines. Tacticfy never logs player names, attributes or save data, and your Windows user name and home folder are removed from the log lines.

## Developer setup

Requirements: **Windows 10/11** and **Python 3.11+**.

```bat
git clone https://github.com/tacticfyhelp/Tacticfy.git
cd Tacticfy
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
run.bat
```

`run.bat` creates `.venv` and installs `requirements.txt` on first run if you skip the manual steps.

Run the tests:

```bat
.venv\Scripts\python.exe -m pytest
```

### Building the installer

```bat
build_installer.bat
```

The script installs PyInstaller into `.venv`, runs the tests, builds `dist\Tacticfy\Tacticfy.exe` from [`build/tacticfy.spec`](build/tacticfy.spec) (one-folder, windowed), and then packages `dist\TacticfySetup.exe` with [Inno Setup 6](https://jrsoftware.org/isdl.php) using [`build/installer.iss`](build/installer.iss). Upload `TacticfySetup.exe` to a GitHub Release; `dist/` is not committed.

The app version lives in `src/app_paths.py` (`APP_VERSION`).

### Project layout

```
main.py                 entry point
config/                 formations, FM27 role/instruction catalogues, offsets.json
src/engine/             role evaluator, formation/synergy optimizer, instructions, bench, training
src/advisor/            squad classifier and weakest-link analysis
src/memory/             fm.exe live reader, calibration, CSV/JSON fallback loader
src/ui/                 PySide6 UI, themes and EN/HE translations (i18n.py)
tests/                  pytest suite
build/                  PyInstaller spec and Inno Setup script
probe_fm.py             developer tool for re-mapping offsets after an FM27 patch
```

## Disclaimer

Tacticfy is an unofficial fan-made tool and is not affiliated with or endorsed by Sports Interactive or SEGA. *Football Manager* is a trademark of its owners. Tacticfy only **reads** game memory; it never modifies your save.

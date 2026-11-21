<p align="center">
  <img src="assets/Tacticfy.ico" width="96" alt="Tacticfy icon">
</p>

<h1 align="center">Tacticfy</h1>

<p align="center">
  A web app for <b>Football Manager 27</b> that reads your squad and builds the tactic around it – running on your own PC, in your browser.<br>
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

Languages: English and Hebrew (right-to-left), with light and dark themes.

### How it runs

Tacticfy is a **local web app**. Starting it launches a small server on your PC and opens the UI in your default browser at `http://127.0.0.1:8527`.
The server is what reads FM27's memory – a web page on its own can't do that – and it only listens on your own machine, so nothing is sent to the internet.
Closing the tab (or clicking the ⏻ button) stops it; starting Tacticfy again while it's running just reopens the page.

## Easy installation (no Python required)

1. Go to the **[Releases](https://github.com/tacticfyhelp/Tacticfy/releases)** page.
2. Download **`TacticfySetup.exe`** from the latest release.
3. Run it and install like any standard Windows app. It adds Start Menu and (optionally) Desktop shortcuts and a normal uninstaller.
4. Start FM27, load your save and open the **Squad** screen.
5. Start Tacticfy – it opens in your browser – and click **Load from FM27**.

> Windows SmartScreen may warn about an unrecognised app because the installer is not code-signed. Click **More info → Run anyway**.

Your logs and any offsets you calibrate yourself are stored in `%LOCALAPPDATA%\Tacticfy\`, so nothing is written to `Program Files`.

## FM27 patch policy

Live reading depends on memory offsets for the **current FM27 patch**, stored in [`config/offsets.json`](config/offsets.json).
FM27 updates can move those offsets, and then **Load from FM27** fails (for example *"Squad array signature not found"*).

- Whenever a new FM27 patch breaks live reading, an **updated release will be published on GitHub** – just install the new `TacticfySetup.exe` over the old one.
- Until then you can still use **Import**, or try **Calibrate** (In-Game Editor values) in the app. A user calibration is saved to `%LOCALAPPDATA%\Tacticfy\offsets.json` and is ignored automatically after you update to a newer release.
- Please report broken patches with the **Report Bug** button (or the [bug report form](https://github.com/tacticfyhelp/Tacticfy/issues/new?template=bug_report.md)) and include your FM27 version.

## Reporting bugs

Click **Report Bug** in the toolbar. It opens a GitHub issue pre-filled with your Windows version, the Tacticfy version and the last 20 log lines. Tacticfy never logs player names, attributes or save data, and your Windows user name and home folder are removed from the log lines.

## Developer setup

Requirements: **Windows 10/11** and **Python 3.11+**.

```bat
git clone https://github.com/tacticfyhelp/Tacticfy.git
cd Tacticfy
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
run.bat
```

`run.bat` creates `.venv` and installs `requirements.txt` on first run if you skip the manual steps. It starts the server and opens your browser; `python main.py --no-browser --port 8600` is handy while developing.

The compiled Tailwind CSS is committed, so running from source needs no Node.js. After changing `web/index.html`, `web/app.js` or `styles/*.css`, rebuild it with `build_css.bat` (Node.js 18+, Tailwind CSS 4).

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
main.py                 entry point: starts the local server and opens the browser
web/                    browser UI: index.html, app.js, compiled Tailwind CSS (assets/app.css)
styles/                 Tailwind sources for the app (app.css) and the website (site.css)
config/                 formations, FM27 role/instruction catalogues, offsets.json
src/engine/             role evaluator, formation/synergy optimizer, instructions, bench, training
src/advisor/            squad classifier and weakest-link analysis
src/memory/             fm.exe live reader, calibration, CSV/JSON fallback loader
src/web/                local HTTP server (stdlib), JSON API and result serialisation
src/i18n.py             English / Hebrew UI strings sent to the browser
tests/                  pytest suite
build/                  PyInstaller spec and Inno Setup script
docs/                   GitHub Pages website
probe_fm.py             developer tool for re-mapping offsets after an FM27 patch
```

## Disclaimer

Tacticfy is an unofficial fan-made tool and is not affiliated with or endorsed by Sports Interactive or SEGA. *Football Manager* is a trademark of its owners. Tacticfy only **reads** game memory; it never modifies your save.

"""UI translations (English / Hebrew).

Usage: ``tr("toolbar.load")`` or ``tr("status.imported", count=26, file="squad.html")``.
Missing Hebrew keys fall back to English, missing English keys fall back to the key itself.

Deliberately NOT translated (they must match the FM27 UI 1:1): FM27 role names, team / player
instruction tile names and their values, mentality names, formation names and player names.
Wrap such names with ``ltr()`` when they sit inside Hebrew right-to-left text.
"""

from __future__ import annotations

from typing import Dict, Iterable

LANGUAGES = ("en", "he")
LANG_BUTTON_TEXT = "Lang: EN / עב"
RTL_LANGUAGES = {"he"}

_LRE, _RLE, _PDF = "\u202a", "\u202b", "\u202c"  # left-to-right / right-to-left embedding, pop directional formatting

EN: Dict[str, str] = {
    # ---------------------------------------------------------------- main window / toolbar
    "app.title": "FM27 Scout & Dual-Phase Tactical Synergy Optimizer",
    "toolbar.load": "Load from FM27",
    "toolbar.load_tip": "Read your live squad from the running fm.exe (non-blocking)",
    "toolbar.scanning": "Scanning…",
    "toolbar.calibrate": "Calibrate",
    "toolbar.calibrate_tip": "Calibrate Offsets (IGE)",
    "toolbar.import": "Import",
    "toolbar.import_tip": "Import an exported squad view (HTML/CSV)",
    "toolbar.style": "Style",
    "toolbar.formation": "Formation",
    "toolbar.important": "Important Match",
    "toolbar.important_tip": "Important Match Mode: weights Important Matches, Pressure and Consistency",
    "toolbar.optimize": "Re-optimize",
    "toolbar.optimize_tip": "Re-optimize the lineup (Style, Formation and Important Match changes already apply instantly)",
    "toolbar.theme": "Theme: {name}",
    "toolbar.theme_tip": "Switch between Apple Light Glass and Apple Dark Glass",
    "toolbar.lang_tip": "Language: English (click to switch to Hebrew)",
    "toolbar.report_bug": "Report Bug",
    "toolbar.report_bug_tip": "Open a GitHub issue pre-filled with your Windows version, app version and the last 20 log lines (no player or save data)",
    "theme.Light": "Light",
    "theme.Dark": "Dark",
    "formation.auto_standard": "Auto-Recommend (Standard Formations)",
    "formation.auto_all": "Auto-Recommend (All / Meta Formations)",
    "formation.category.standard": "Standard",
    "formation.category.tactical_meta": "Tactical Meta",
    "style.High-Scoring Attacking": "High-Scoring Attacking",
    "style.Proactive Possession": "Proactive Possession",
    "style.Balanced Tactical Meta": "Balanced Tactical Meta",
    "style.Fluid Counter-Attack": "Fluid Counter-Attack",
    "style.Defensive Solidity": "Defensive Solidity",
    "tab.tactics": "Tactical Pitch && Instructions",
    "tab.squad": "Squad && Hidden Attributes",
    "tab.advisor": "Squad Planner && Transfer Advisor",
    # ---------------------------------------------------------------- status / dialogs
    "status.ready": "Ready. Click 'Load from FM27' to read live RAM or load the sample squad.",
    "status.scanning": "Scanning fm.exe live memory...",
    "status.live_ok": "Live RAM  ·  {message}",
    "status.live_failed": "Live read failed  ·  {message} {shown}",
    "status.fallback": "Demo / fallback  ·  {message} Showing 26-player sample squad.",
    "status.kept_current": "Keeping the previously loaded squad.",
    "status.showing_demo": "Showing the 26-player DEMO squad.",
    "status.calibrated": "Offsets calibrated! Click 'Load from FM27' to read the live squad.",
    "status.imported": "Imported file  ·  Loaded {count} players from {file}.",
    "pool.standard": "Best of standard formations",
    "pool.all": "Best of all formations (incl. tactical meta)",
    "pool.locked": "Formation locked",
    "dialog.live_loaded.title": "FM27 Live RAM Loaded",
    "dialog.live_failed.title": "FM27 Live Read Failed",
    "dialog.live_failed.body": (
        "fm.exe is running, but its squad could not be read from memory.\n\n{message}\n\n"
        "{shown} The players shown are NOT your live FM27 squad.\n\n"
        "Likely causes: no save is loaded yet, the squad screen has not been opened, or a game "
        "patch moved the player data (config/offsets.json -> fm27_live_layout needs re-mapping)."
    ),
    "dialog.calibration.title": "FM27 Detected — Calibration Required",
    "dialog.calibration.body": (
        "fm.exe is running, but config/offsets.json is not calibrated for this patch yet.\n\n"
        "Would you like to open the In-Game Editor (IGE) Calibration Wizard now?"
    ),
    "dialog.not_loaded.title": "FM27 Process Not Loaded",
    "dialog.not_loaded.body": (
        "{message}\n\nOptions:\n"
        "1. Launch FM27 (fm.exe), load your save, and click 'Load from FM27' again.\n"
        "2. Or click 'Import' to load an exported squad view directly."
    ),
    "dialog.import.title": "Import FM27 Squad View",
    "dialog.import.filter": "Squad Exports (*.html *.htm *.csv *.rtf);;All Files (*)",
    "dialog.import_incomplete.title": "Import Incomplete",
    "dialog.import_incomplete.body": (
        "Only {count} players were parsed. Need at least 11 players for tactical optimization."
    ),
    "dialog.import_error.title": "Import Error",
    # ---------------------------------------------------------------- tactics tab
    "tactics.prompt": "Click 'Load from FM27' to generate your Dual-Phase Tactical Plan.",
    "tactics.mode.best": "Best XI",
    "tactics.mode.second": "Second XI",
    "tactics.mode.dropoff": "Drop-Off",
    "tactics.mode.bench": "Bench & Subs",
    "tactics.pitch.ip": "In Possession",
    "tactics.pitch.oop": "Out of Possession",
    "tactics.match_plan": "Match Plan",
    "tactics.copy_plan": "Copy Plan",
    "tactics.copy_tip": "Copy formation, Best XI roles, bench and all instructions to the clipboard",
    "tactics.copied": "Copied ✓",
    "tactics.instructions_placeholder": "Team instructions will appear here.",
    "tactics.click_hint": "Click any player on either pitch to inspect their Individual Instructions & Transition Load.",
    "tactics.mentality": "Mentality",
    "tactics.section.ip": "In Possession",
    "tactics.section.transition": "In Transition",
    "tactics.section.oop": "Out of Possession",
    "tactics.section.notes": "Synergy & Tactical Notes",
    "tactics.phase.Build-Up": "Build-Up",
    "tactics.phase.Progression": "Progression",
    "tactics.phase.Final Third": "Final Third",
    "tactics.phase.High Press": "High Press",
    "tactics.phase.Mid Block": "Mid Block",
    "tactics.phase.Low Block": "Low Block",
    "tactics.summary.synergy": "Synergy",
    "tactics.summary.important": "Important Match",
    "tactics.detail.ip": "In Possession",
    "tactics.detail.oop": "Out of Possession",
    "tactics.detail.displacement": "Transition Displacement",
    "tactics.detail.alert": "Alert",
    "tactics.detail.optimal": "Transition Load: Optimal",
    "tactics.detail.pi": "Individual Instructions",
    "tactics.detail.training": "Training",
    # ---------------------------------------------------------------- bench & subs
    "bench.title": "Recommended Matchday Bench",
    "bench.size": "Subs",
    "bench.size_tip": "Number of substitutes allowed on the matchday bench",
    "bench.col.player": "Player",
    "bench.col.pos": "Pos",
    "bench.col.cover": "Bench Role",
    "bench.col.covers": "Covers",
    "bench.col.best": "Best Cover",
    "bench.col.impact": "Impact",
    "bench.role.backup_gk": "Backup GK",
    "bench.role.defence": "Defensive Cover",
    "bench.role.midfield": "Midfield Cover",
    "bench.role.attack": "Attacking Cover",
    "bench.role.utility": "Utility",
    "bench.uncovered": "No natural cover for: {slots}",
    "bench.all_covered": "Every Best XI slot has bench cover.",
    "bench.empty": "Not enough players outside the Best XI to name a bench.",
    "bench.subs_title": "Suggested In-Game Substitutions",
    "bench.no_subs": "No clear substitution upgrade from this bench.",
    "subs.kind.chase_goal": "Chase a Goal",
    "subs.kind.protect_lead": "Protect a Lead",
    "subs.kind.fatigue": "Fresh Legs",
    "subs.change": "{on} ON for {off} ({slot})",
    "subs.roles": "Role",
    "subs.reason.chase": "Fresh impact {on_impact} vs tiring starter {off_impact} (Pace {pace}, Dribbling {dribbling}).",
    "subs.reason.protect": "Defensive solidity {on_def} vs tiring starter {off_def} (Work Rate {work_rate}, Tackling {tackling}).",
    "subs.reason.fatigue": "Like-for-like change for the starter most likely to tire (Stamina {stamina}, Natural Fitness {fitness}).",
    # ---------------------------------------------------------------- squad tab
    "squad.col.lock": "Lock XI",
    "squad.col.name": "Name",
    "squad.col.age": "Age",
    "squad.col.pos": "Pos",
    "squad.col.ca": "CA",
    "squad.col.pa": "PA",
    "squad.col.headroom": "PA-CA",
    "squad.col.prof": "Prof",
    "squad.col.amb": "Amb",
    "squad.col.imp": "Imp.M",
    "squad.col.pres": "Pres",
    "squad.col.cons": "Cons",
    "squad.col.inj": "Inj",
    "squad.col.wage": "Wage ($/wk)",
    "squad.col.best_ip": "Best IP Role",
    "squad.col.ip": "IP",
    "squad.col.best_oop": "Best OOP Role",
    "squad.col.oop": "OOP",
    "squad.col.status": "Advisor Status",
    "squad.col.role_focus": "Role Focus",
    "squad.col.add_focus": "Add. Focus",
    "squad.col.intensity": "Intensity",
    "squad.search": "Search name, position, role or advisor status…",
    "squad.count": "{total} players",
    "squad.count_filtered": "{shown} of {total} players",
    "squad.lock_hint": "Check 'Lock XI' to force a player into the Best XI.",
    "squad.wage_unmapped": "Wage is not yet mapped for the live FM27 reader.",
    # ---------------------------------------------------------------- advisor tab
    "advisor.weakest.title": "Weakest Link && Priority Transfer Target Profile",
    "advisor.weakest.placeholder": "Load your squad to generate your Weakest Link scouting profile.",
    "advisor.weakest.summary": "Priority Upgrade: {slot} ({name}, Score {score} as {role}).",
    "advisor.weakest.depth": "Steepest squad depth drop-off is at {slot} (-{delta} pts).",
    "advisor.weakest.no_depth": "No full Second XI available, so depth drop-off cannot be measured.",
    "advisor.weakest.filter": "Recommended search filter for",
    "advisor.bucket.KEEP": "Core && Rotation (Keep)",
    "advisor.bucket.LOAN": "Loan Out (High-Potential Prospects)",
    "advisor.bucket.SELL_HIGH": "Sell High (False Potential Traps)",
    "advisor.bucket.OFFLOAD": "Sell / Offload (Deadweight && Surplus)",
    "advisor.bucket.empty": "No players in this category.",
    "advisor.none": "None",
    "advisor.player_line": "Age {age} · {stats}",
    "advisor.training.title": "Individual Training Plan",
    "advisor.training.placeholder": "Load your squad to generate individual training recommendations.",
    "category.Core Starter (Keep)": "Core Starter (Keep)",
    "category.Rotation / Sub (Keep)": "Rotation / Sub (Keep)",
    "category.Loan Out (Development)": "Loan Out (Development)",
    "category.Sell High (False Potential)": "Sell High (False Potential)",
    "category.Sell / Offload": "Sell / Offload",
    # ---------------------------------------------------------------- training
    "training.col.player": "Player",
    "training.col.role_focus": "Role Focus",
    "training.col.add_focus": "Additional Focus",
    "training.col.intensity": "Intensity",
    "training.col.reason": "Reason",
    "training.source.best_xi": "Best XI",
    "training.source.second_xi": "Second XI",
    "training.source.natural": "Natural role",
    "training.focus.Quickness": "Quickness",
    "training.focus.Endurance": "Endurance",
    "training.focus.Passing": "Passing",
    "training.focus.Final Third": "Final Third",
    "training.focus.Defensive Positioning": "Defensive Positioning",
    "training.focus.Aerial": "Aerial",
    "training.focus.Ball Control": "Ball Control",
    "training.focus.Shot Stopping": "Shot Stopping",
    "training.focus.Distribution": "Distribution",
    "training.focus.None": "None",
    "training.intensity.Double Intensity": "Double Intensity",
    "training.intensity.Normal": "Normal",
    "training.intensity.Half Intensity": "Half Intensity",
    "training.reason.injury_risk": "Injury Proneness {inj}: protect him from overload.",
    "training.reason.veteran": "Age {age}: lighten the load to preserve his physicals.",
    "training.reason.develop": "Age {age}, +{headroom} headroom, Prof {prof} / Det {det}: push development.",
    "training.reason.mentality_limits": "+{headroom} headroom but Prof {prof} / Det {det} limits extra load.",
    "training.reason.focus_gap": "Biggest {role} gaps: {attrs}.",
    "training.reason.ceiling": "At his ceiling (CA {ca} / PA {pa}): maintain, no extra focus.",
    "training.reason.complete": "Already well rounded for {role}.",
    "training.reason.focus_suffix": " Focus: {attrs}.",
}

HE: Dict[str, str] = {
    # ---------------------------------------------------------------- main window / toolbar
    "app.title": "FM27 סקאוט ומייעל סינרגיה טקטית דו-שלבית",
    "toolbar.load": "טען מ-FM27",
    "toolbar.load_tip": "קריאת הסגל החי מתהליך fm.exe הפועל (ללא חסימה)",
    "toolbar.scanning": "סורק…",
    "toolbar.calibrate": "כיול",
    "toolbar.calibrate_tip": "כיול היסטים (IGE)",
    "toolbar.import": "ייבוא",
    "toolbar.import_tip": "ייבוא תצוגת סגל מיוצאת (HTML/CSV)",
    "toolbar.style": "סגנון",
    "toolbar.formation": "מערך",
    "toolbar.important": "משחק חשוב",
    "toolbar.important_tip": "מצב משחק חשוב: משקל ל'משחקים חשובים', עמידה בלחץ ועקביות",
    "toolbar.optimize": "חשב מחדש",
    "toolbar.optimize_tip": "חישוב מחדש של ההרכב (שינויי סגנון, מערך ומשחק חשוב חלים מיד)",
    "toolbar.theme": "ערכה: {name}",
    "toolbar.theme_tip": "מעבר בין ערכת זכוכית בהירה לכהה",
    "toolbar.lang_tip": "שפה: עברית (לחץ למעבר לאנגלית)",
    "toolbar.report_bug": "דווח על באג",
    "toolbar.report_bug_tip": "פתיחת דיווח ב-GitHub עם גרסת Windows, גרסת האפליקציה ו-20 שורות הלוג האחרונות (ללא נתוני שחקנים או שמירה)",
    "theme.Light": "בהירה",
    "theme.Dark": "כהה",
    "formation.auto_standard": "המלצה אוטומטית (מערכים סטנדרטיים)",
    "formation.auto_all": "המלצה אוטומטית (כל המערכים / מטא)",
    "formation.category.standard": "סטנדרטי",
    "formation.category.tactical_meta": "מטא טקטי",
    "style.High-Scoring Attacking": "התקפה עתירת שערים",
    "style.Proactive Possession": "החזקת כדור יוזמת",
    "style.Balanced Tactical Meta": "מטא טקטי מאוזן",
    "style.Fluid Counter-Attack": "מתפרצות זורמות",
    "style.Defensive Solidity": "יציבות הגנתית",
    "tab.tactics": "מגרש טקטי והוראות",
    "tab.squad": "סגל ותכונות נסתרות",
    "tab.advisor": "תכנון סגל ויועץ העברות",
    # ---------------------------------------------------------------- status / dialogs
    "status.ready": "מוכן. לחץ 'טען מ-FM27' כדי לקרוא את הזיכרון החי או לטעון סגל לדוגמה.",
    "status.scanning": "סורק את הזיכרון החי של fm.exe...",
    "status.live_ok": "זיכרון חי  ·  {message}",
    "status.live_failed": "הקריאה החיה נכשלה  ·  {message} {shown}",
    "status.fallback": "הדגמה / גיבוי  ·  {message} מוצג סגל לדוגמה של 26 שחקנים.",
    "status.kept_current": "נשמר הסגל שנטען קודם.",
    "status.showing_demo": "מוצג סגל ההדגמה של 26 שחקנים.",
    "status.calibrated": "ההיסטים כוילו! לחץ 'טען מ-FM27' כדי לקרוא את הסגל החי.",
    "status.imported": "קובץ יובא  ·  נטענו {count} שחקנים מתוך {file}.",
    "pool.standard": "הטוב ביותר מבין המערכים הסטנדרטיים",
    "pool.all": "הטוב ביותר מבין כל המערכים (כולל מטא טקטי)",
    "pool.locked": "מערך נעול",
    "dialog.live_loaded.title": "הזיכרון החי של FM27 נטען",
    "dialog.live_failed.title": "הקריאה החיה מ-FM27 נכשלה",
    "dialog.live_failed.body": (
        "fm.exe פועל, אך לא ניתן היה לקרוא את הסגל מהזיכרון.\n\n{message}\n\n"
        "{shown} השחקנים המוצגים אינם הסגל החי שלך ב-FM27.\n\n"
        "סיבות אפשריות: לא נטענה שמירה, מסך הסגל לא נפתח, או שעדכון משחק הזיז את נתוני השחקנים "
        "(config/offsets.json -> fm27_live_layout דורש מיפוי מחדש)."
    ),
    "dialog.calibration.title": "FM27 זוהה — נדרש כיול",
    "dialog.calibration.body": (
        "fm.exe פועל, אך config/offsets.json עדיין לא מכויל לעדכון הזה.\n\n"
        "לפתוח עכשיו את אשף הכיול של העורך במשחק (IGE)?"
    ),
    "dialog.not_loaded.title": "תהליך FM27 לא נטען",
    "dialog.not_loaded.body": (
        "{message}\n\nאפשרויות:\n"
        "1. הפעל את FM27 (fm.exe), טען את השמירה ולחץ שוב 'טען מ-FM27'.\n"
        "2. או לחץ 'ייבוא' כדי לטעון ישירות תצוגת סגל מיוצאת."
    ),
    "dialog.import.title": "ייבוא תצוגת סגל FM27",
    "dialog.import.filter": "קבצי סגל (*.html *.htm *.csv *.rtf);;כל הקבצים (*)",
    "dialog.import_incomplete.title": "הייבוא לא הושלם",
    "dialog.import_incomplete.body": "נקראו רק {count} שחקנים. נדרשים לפחות 11 שחקנים לאופטימיזציה טקטית.",
    "dialog.import_error.title": "שגיאת ייבוא",
    # ---------------------------------------------------------------- tactics tab
    "tactics.prompt": "לחץ 'טען מ-FM27' כדי ליצור את התוכנית הטקטית הדו-שלבית שלך.",
    "tactics.mode.best": "ההרכב הטוב",
    "tactics.mode.second": "הרכב שני",
    "tactics.mode.dropoff": "ירידת איכות",
    "tactics.mode.bench": "ספסל וחילופים",
    "tactics.pitch.ip": "בהחזקת כדור",
    "tactics.pitch.oop": "ללא כדור",
    "tactics.match_plan": "תוכנית משחק",
    "tactics.copy_plan": "העתק תוכנית",
    "tactics.copy_tip": "העתקת המערך, התפקידים, הספסל וכל ההוראות ללוח",
    "tactics.copied": "הועתק ✓",
    "tactics.instructions_placeholder": "הוראות הקבוצה יופיעו כאן.",
    "tactics.click_hint": "לחץ על שחקן באחד המגרשים כדי לראות את ההוראות האישיות ועומס המעבר שלו.",
    "tactics.mentality": "מנטליות",
    "tactics.section.ip": "בהחזקת כדור",
    "tactics.section.transition": "במעבר",
    "tactics.section.oop": "ללא כדור",
    "tactics.section.notes": "סינרגיה והערות טקטיות",
    "tactics.phase.Build-Up": "בניית משחק",
    "tactics.phase.Progression": "התקדמות",
    "tactics.phase.Final Third": "שליש אחרון",
    "tactics.phase.High Press": "לחץ גבוה",
    "tactics.phase.Mid Block": "בלוק אמצעי",
    "tactics.phase.Low Block": "בלוק נמוך",
    "tactics.summary.synergy": "סינרגיה",
    "tactics.summary.important": "משחק חשוב",
    "tactics.detail.ip": "בהחזקת כדור",
    "tactics.detail.oop": "ללא כדור",
    "tactics.detail.displacement": "תזוזת מעבר",
    "tactics.detail.alert": "התראה",
    "tactics.detail.optimal": "עומס מעבר: אופטימלי",
    "tactics.detail.pi": "הוראות אישיות",
    "tactics.detail.training": "אימון",
    # ---------------------------------------------------------------- bench & subs
    "bench.title": "ספסל מומלץ ליום המשחק",
    "bench.size": "מחליפים",
    "bench.size_tip": "מספר המחליפים המותר על הספסל",
    "bench.col.player": "שחקן",
    "bench.col.pos": "עמדה",
    "bench.col.cover": "תפקיד בספסל",
    "bench.col.covers": "מכסה",
    "bench.col.best": "כיסוי מיטבי",
    "bench.col.impact": "השפעה",
    "bench.role.backup_gk": "שוער מחליף",
    "bench.role.defence": "כיסוי הגנה",
    "bench.role.midfield": "כיסוי קישור",
    "bench.role.attack": "כיסוי התקפה",
    "bench.role.utility": "רב-תכליתי",
    "bench.uncovered": "אין כיסוי טבעי עבור: {slots}",
    "bench.all_covered": "לכל עמדה בהרכב יש כיסוי בספסל.",
    "bench.empty": "אין מספיק שחקנים מחוץ להרכב כדי להרכיב ספסל.",
    "bench.subs_title": "חילופים מומלצים במהלך המשחק",
    "bench.no_subs": "אין בספסל הזה חילוף שמשפר בבירור.",
    "subs.kind.chase_goal": "רדיפה אחרי שער",
    "subs.kind.protect_lead": "שמירה על יתרון",
    "subs.kind.fatigue": "רגליים רעננות",
    "subs.change": "{on} נכנס במקום {off} ({slot})",
    "subs.roles": "תפקיד",
    "subs.reason.chase": "השפעה רעננה {on_impact} מול {off_impact} של שחקן עייף (מהירות {pace}, כדרור {dribbling}).",
    "subs.reason.protect": "יציבות הגנתית {on_def} מול {off_def} של שחקן עייף (חריצות {work_rate}, תיקולים {tackling}).",
    "subs.reason.fatigue": "חילוף זהה לשחקן שצפוי להתעייף ראשון (סיבולת {stamina}, כושר טבעי {fitness}).",
    # ---------------------------------------------------------------- squad tab
    "squad.col.lock": "נעילה",
    "squad.col.name": "שם",
    "squad.col.age": "גיל",
    "squad.col.pos": "עמדה",
    "squad.col.ca": "CA",
    "squad.col.pa": "PA",
    "squad.col.headroom": "PA-CA",
    "squad.col.prof": "מקצועיות",
    "squad.col.amb": "שאפתנות",
    "squad.col.imp": "מ. חשובים",
    "squad.col.pres": "לחץ",
    "squad.col.cons": "עקביות",
    "squad.col.inj": "פציעות",
    "squad.col.wage": "שכר ($/שבוע)",
    "squad.col.best_ip": "תפקיד IP מיטבי",
    "squad.col.ip": "IP",
    "squad.col.best_oop": "תפקיד OOP מיטבי",
    "squad.col.oop": "OOP",
    "squad.col.status": "המלצת יועץ",
    "squad.col.role_focus": "מיקוד תפקיד",
    "squad.col.add_focus": "מיקוד נוסף",
    "squad.col.intensity": "עצימות",
    "squad.search": "חיפוש לפי שם, עמדה, תפקיד או המלצה…",
    "squad.count": "{total} שחקנים",
    "squad.count_filtered": "{shown} מתוך {total} שחקנים",
    "squad.lock_hint": "סמן 'נעילה' כדי לכפות שחקן בהרכב הטוב.",
    "squad.wage_unmapped": "השכר עדיין לא ממופה בקורא החי של FM27.",
    # ---------------------------------------------------------------- advisor tab
    "advisor.weakest.title": "החוליה החלשה ופרופיל יעד העברה עדיף",
    "advisor.weakest.placeholder": "טען את הסגל כדי ליצור את פרופיל הסקאוטינג של החוליה החלשה.",
    "advisor.weakest.summary": "שדרוג עדיף: {slot} ({name}, ציון {score} בתפקיד {role}).",
    "advisor.weakest.depth": "ירידת העומק החדה ביותר היא ב-{slot} (‎-{delta} נק').",
    "advisor.weakest.no_depth": "אין הרכב שני מלא, ולכן אי אפשר למדוד ירידת עומק.",
    "advisor.weakest.filter": "מסנן חיפוש מומלץ עבור",
    "advisor.bucket.KEEP": "גרעין ורוטציה (להשאיר)",
    "advisor.bucket.LOAN": "השאלה (כישרונות עם פוטנציאל)",
    "advisor.bucket.SELL_HIGH": "למכור ביוקר (מלכודות פוטנציאל)",
    "advisor.bucket.OFFLOAD": "למכור / לשחרר (עודף סגל)",
    "advisor.bucket.empty": "אין שחקנים בקטגוריה הזו.",
    "advisor.none": "אין",
    "advisor.player_line": "גיל {age} · {stats}",
    "advisor.training.title": "תוכנית אימון אישית",
    "advisor.training.placeholder": "טען את הסגל כדי ליצור המלצות אימון אישיות.",
    "category.Core Starter (Keep)": "פותח מרכזי (להשאיר)",
    "category.Rotation / Sub (Keep)": "רוטציה / מחליף (להשאיר)",
    "category.Loan Out (Development)": "השאלה (התפתחות)",
    "category.Sell High (False Potential)": "למכור ביוקר (פוטנציאל מטעה)",
    "category.Sell / Offload": "למכור / לשחרר",
    # ---------------------------------------------------------------- training
    "training.col.player": "שחקן",
    "training.col.role_focus": "מיקוד תפקיד",
    "training.col.add_focus": "מיקוד נוסף",
    "training.col.intensity": "עצימות",
    "training.col.reason": "סיבה",
    "training.source.best_xi": "ההרכב הטוב",
    "training.source.second_xi": "הרכב שני",
    "training.source.natural": "תפקיד טבעי",
    "training.focus.Quickness": "מהירות וזריזות",
    "training.focus.Endurance": "סיבולת",
    "training.focus.Passing": "מסירות",
    "training.focus.Final Third": "שליש אחרון",
    "training.focus.Defensive Positioning": "מיקום הגנתי",
    "training.focus.Aerial": "משחק אווירי",
    "training.focus.Ball Control": "שליטה בכדור",
    "training.focus.Shot Stopping": "עצירת בעיטות",
    "training.focus.Distribution": "הפצת כדור",
    "training.focus.None": "ללא",
    "training.intensity.Double Intensity": "עצימות כפולה",
    "training.intensity.Normal": "רגילה",
    "training.intensity.Half Intensity": "חצי עצימות",
    "training.reason.injury_risk": "נטייה לפציעות {inj}: יש להגן עליו מעומס יתר.",
    "training.reason.veteran": "גיל {age}: הפחתת עומס לשימור הנתונים הפיזיים.",
    "training.reason.develop": "גיל {age}, ‎+{headroom} פוטנציאל, מקצועיות {prof} / נחישות {det}: לדחוף התפתחות.",
    "training.reason.mentality_limits": "‎+{headroom} פוטנציאל, אך מקצועיות {prof} / נחישות {det} מגבילות עומס נוסף.",
    "training.reason.focus_gap": "הפערים הגדולים ביותר בתפקיד {role}: {attrs}.",
    "training.reason.ceiling": "בתקרה שלו (CA {ca} / PA {pa}): שימור, ללא מיקוד נוסף.",
    "training.reason.complete": "כבר מעוגל היטב לתפקיד {role}.",
    "training.reason.focus_suffix": " מיקוד: {attrs}.",
}

ATTRIBUTES_HE: Dict[str, str] = {
    "corners": "קרנות", "crossing": "הגבהות", "dribbling": "כדרור", "finishing": "סיומת",
    "first_touch": "נגיעה ראשונה", "free_kick_taking": "בעיטות חופשיות", "heading": "משחק ראש",
    "long_shots": "בעיטות מרחוק", "long_throws": "זריקות חוץ ארוכות", "marking": "שמירה", "passing": "מסירות",
    "penalty_taking": "פנדלים", "tackling": "תיקולים", "technique": "טכניקה", "aggression": "אגרסיביות",
    "anticipation": "קריאת משחק", "bravery": "אומץ", "composure": "קור רוח", "concentration": "ריכוז",
    "decisions": "קבלת החלטות", "determination": "נחישות", "flair": "כישרון", "leadership": "מנהיגות",
    "off_the_ball": "תנועה ללא כדור", "positioning": "מיקום", "teamwork": "עבודת צוות", "vision": "ראיית משחק",
    "work_rate": "חריצות", "acceleration": "האצה", "agility": "זריזות", "balance": "שיווי משקל",
    "jumping_reach": "ניתור", "natural_fitness": "כושר טבעי", "pace": "מהירות", "stamina": "סיבולת",
    "strength": "כוח", "aerial_reach": "טווח אווירי", "command_of_area": "שליטה ברחבה",
    "communication": "תקשורת", "eccentricity": "אקסצנטריות", "handling": "תפיסה", "kicking": "בעיטות שוער",
    "one_on_ones": "אחד על אחד", "punching": "הדיפות", "reflexes": "רפלקסים", "rushing_out": "יציאות",
    "throwing": "זריקות", "consistency": "עקביות", "important_matches": "משחקים חשובים",
    "injury_proneness": "נטייה לפציעות", "professionalism": "מקצועיות", "ambition": "שאפתנות",
    "pressure": "עמידה בלחץ", "temperament": "מזג", "versatility": "ורסטיליות", "adaptability": "הסתגלות",
    "loyalty": "נאמנות", "dirtiness": "משחק מלוכלך", "sportsmanship": "ספורטיביות", "controversy": "שנויות במחלוקת",
}

_TABLES: Dict[str, Dict[str, str]] = {"en": EN, "he": HE}
_current = "en"


def set_language(lang: str) -> None:
    """Switch the active UI language ("en" or "he")."""
    global _current
    if lang not in _TABLES:
        raise ValueError(f"Unsupported language {lang!r}; expected one of {LANGUAGES}.")
    _current = lang


def current_language() -> str:
    return _current


def is_rtl(lang: str | None = None) -> bool:
    return (lang or _current) in RTL_LANGUAGES


class _SafeArgs(dict):
    """Leaves unknown ``{placeholders}`` untouched instead of raising KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def tr(key: str, **args: object) -> str:
    """Translate ``key`` into the active language and fill ``{placeholders}`` from ``args``.

    In Hebrew the result is wrapped in a right-to-left embedding (invisible control characters).
    """
    text = _TABLES[_current].get(key)
    if text is None:
        text = EN.get(key, key)
    text = text.format_map(_SafeArgs(args)) if args else text
    # Force a right-to-left base direction: Qt draws button / tab / header text left-to-right even in a
    # right-to-left window, which scrambles Hebrew strings that contain Latin tokens such as "FM27".
    return f"{_RLE}{text}{_PDF}" if is_rtl() and text else text


def ltr(text: str) -> str:
    """Keep an English FM27 name (role, instruction, player) readable inside right-to-left text."""
    return f"{_LRE}{text}{_PDF}" if is_rtl() and text else text


def tr_attr(attr: str) -> str:
    """Display name of an attribute ("off_the_ball" -> "Off The Ball" / "תנועה ללא כדור")."""
    if _current == "he" and attr in ATTRIBUTES_HE:
        return ATTRIBUTES_HE[attr]
    return attr.replace("_", " ").title()


def tr_attrs(attrs: Iterable[str]) -> str:
    return ", ".join(tr_attr(a) for a in attrs)


def tr_category(category: str) -> str:
    return tr(f"category.{category}") if f"category.{category}" in EN else category


def tr_focus(focus: str) -> str:
    return tr(f"training.focus.{focus}") if f"training.focus.{focus}" in EN else focus


def tr_intensity(intensity: str) -> str:
    return tr(f"training.intensity.{intensity}") if f"training.intensity.{intensity}" in EN else intensity


def tr_style(style: str) -> str:
    return tr(f"style.{style}") if f"style.{style}" in EN else style


def tr_reason(key: str, args: dict) -> str:
    """Render an engine reason (translation key + args); lists of attributes become display names."""
    if not key:
        return ""
    filled = {k: (tr_attrs(v) if isinstance(v, (list, tuple)) else v) for k, v in args.items()}
    if "role" in filled:
        filled["role"] = ltr(str(filled["role"]))
    return tr(key, **filled)


def training_reason(rec) -> str:
    """One-line reason for a TrainingRecommendation (focus attributes appended when relevant)."""
    text = tr_reason(rec.reason_key, rec.reason_args)
    attrs = rec.reason_args.get("attrs") or []
    if rec.reason_key != "training.reason.focus_gap" and rec.additional_focus != "None" and attrs:
        text += tr("training.reason.focus_suffix", attrs=tr_attrs(attrs))
    return text


def tr_button(key: str, **args: object) -> str:
    """``tr()`` for QPushButton / QCheckBox text, where a single "&" would become a mnemonic underline."""
    return tr(key, **args).replace("&", "&&")


def bidi_row(cells: Iterable[str]) -> str:
    """Join rich-text table cells so the first column sits on the reading-start side (right in Hebrew)."""
    cells = list(cells)
    return "".join(reversed(cells) if is_rtl() else cells)


def table_open(extra: str = "") -> str:
    """Opening <table> tag aligned to the reading-start side."""
    align = " align='right'" if is_rtl() else ""
    return f"<table cellspacing='0'{align}{(' ' + extra) if extra else ''}>"


def cell_pad(v: int = 2, gap: int = 10) -> str:
    """Cell padding with the column gap on the reading-end side."""
    return f"padding:{v}px 0 {v}px {gap}px" if is_rtl() else f"padding:{v}px {gap}px {v}px 0"

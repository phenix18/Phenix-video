#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Auto-test : fabrique de petites vidéos synthétiques et vérifie les fonctions principales de bout en bout.

  ./phenix selftest

Cas : vidéo carrée SANS parole (sport/musique), vidéo plus courte que le minimum, amélioration (effets, mascotte),
masquage de logo, dossier de publication. Dure 1 à 3 minutes. Ne télécharge rien (sauf modèles de transcription si absents).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = [sys.executable, "-I"]


def sh(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


def probe(path: Path) -> str:
    _, out = sh(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration", "-of", "csv=p=0", str(path)])
    return out.strip().replace("\n", " | ")


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="phenix_selftest_"))
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"[{'OK' if ok else 'ÉCHEC'}] {name}" + (f" — {detail}" if detail and not ok else ""), flush=True)

    t0 = time.time()
    src = work / "sans_parole.mp4"
    rc, out = sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1080:rate=30:duration=25",
                  "-f", "lavfi", "-i", "sine=frequency=220:duration=25,tremolo=f=2:d=0.9", "-c:v", "libx264", "-preset",
                  "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)])
    check("création de la vidéo de test", rc == 0 and src.exists(), out[-200:])
    if rc != 0:
        return 1

    # 1) vidéo carrée sans parole, plus courte que --min : ne doit pas échouer
    o1 = work / "o1"
    rc, out = sh([*PY, str(HERE / "pipeline.py"), str(src), "-o", str(o1), "--clips", "3", "--quality", "fast", "--model", "tiny",
                  "--translate-to", "fr", "--tighten", "--no-thumbnails"])
    mp4 = sorted(o1.glob("clip_*.mp4"))
    check("vidéo sans parole + vidéo courte (clip unique, 9:16)", rc == 0 and len(mp4) == 1 and "1080,1920" in probe(mp4[0]),
          out[-300:])

    # 2) amélioration : nettoyage, effets, titre, mascotte
    if mp4:
        pro = work / "pro.mp4"
        rc, out = sh([*PY, str(HERE / "enhance.py"), str(mp4[0]), "-o", str(pro), "--clean", "--effects", "cinema,vignette",
                      "--title", "Test", "--mascot", "--quality", "fast"])
        check("amélioration (nettoyage, effets, titre, mascotte)", rc == 0 and pro.exists() and "1080,1920" in probe(pro), out[-300:])
        dl = work / "dl.mp4"
        rc, out = sh([*PY, str(HERE / "edit.py"), "delogo", str(mp4[0]), "-o", str(dl), "--area", "br", "--quality", "fast"])
        check("masquage de logo", rc == 0 and dl.exists(), out[-300:])
        rc, out = sh([*PY, str(HERE / "publish.py"), str(o1)])
        check("dossier de publication + fiche de boost", rc == 0 and (o1 / "publish" / "INDEX.md").exists()
              and (o1 / "publish" / "BOOST.md").exists(), out[-300:])

    # 3) sélection par le son/mouvement sur une vidéo plus longue
    long_src = work / "longue.mp4"
    rc, _ = sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15:duration=300", "-f", "lavfi",
                "-i", "sine=frequency=330:duration=300,volume='0.1+0.9*gt(sin(t/9),0.6)':eval=frame", "-c:v", "libx264",
                "-preset", "ultrafast", "-crf", "32", "-c:a", "aac", "-shortest", str(long_src)])
    if rc == 0:
        o3 = work / "o3"
        rc, out = sh([*PY, str(HERE / "pipeline.py"), str(long_src), "-o", str(o3), "--clips", "3", "--stop-after", "clips",
                      "--model", "tiny"])
        n = out.count("moment ")
        check("sélection de plusieurs moments forts (sans parole)", rc == 0 and n >= 2, out[-300:])

    # 4) tendances (analyse hors ligne sur des métadonnées synthétiques)
    import json as _j
    fake = [{"url": f"https://exemple.test/{i}", "platform": "test", "title": t, "description": "", "duration": d,
             "views": v, "likes": v // 12, "comments": v // 200, "shares": 0, "engagement": 0.09,
             "hashtags": ["argent", "astuce"], "hour_utc": 19}
            for i, (t, d, v) in enumerate([("Pourquoi personne ne te dit la vérité ? #argent", 40, 900000),
                                           ("5 erreurs à éviter #argent", 35, 500000), ("Le secret des riches #astuce", 52, 300000)])]
    (work / "fake.json").write_text(_j.dumps({"entries": fake}), encoding="utf-8")
    rc, out = sh([*PY, str(HERE / "trends.py"), "--from-json", str(work / "fake.json"), "-o", str(work / "tr"), "--theme", "argent"])
    check("analyse de tendances (rapport + idées)", rc == 0 and (work / "tr" / "TENDANCES.md").exists()
          and (work / "tr" / "idees.md").exists(), out[-300:])

    # 4b) analyse de profil, niches, planning (données factices) + modules de comptes
    prof = [{"url": f"https://ex/{i}", "title": f"Astuce {i} argent #argent", "views": 1000 + 700 * i, "duration": 30 + 5 * (i % 6), "likes": 80 + i, "comments": 5,
             "hashtags": ["argent"], "timestamp": 1760000000 + i * 86400 * 1.3, "weekday_utc": i % 7, "hour_utc": 8 + (i % 4) * 4, "followers": 5000, "channel": "demo"}
            for i in range(14)]
    (work / "prof.json").write_text(_j.dumps({"entries": prof}), encoding="utf-8")
    rc, out = sh([*PY, str(HERE / "insights.py"), "profile", "-o", str(work / "ins"), "--from-json", str(work / "prof.json")])
    check("analyse de profil (horaires, jours, planning .ics)", rc == 0 and (work / "ins" / "insights.json").exists()
          and (work / "ins" / "planning.ics").exists(), out[-300:])
    rc, out = sh([*PY, "-c", "import sys;sys.path.insert(0,sys.argv[1]);import accounts;"
                  "cs,n=accounts.plan_chunks(25*1024*1024);assert cs*n<=25*1024*1024<cs*(n+1)+cs and n>=2;"
                  "assert accounts.status()['tiktok']['connected'] in (True,False)", str(HERE)])
    check("modules de comptes (TikTok/YouTube)", rc == 0, out[-300:])

    # 5) application : démarrage du serveur + outil de montage via l'API + fenêtre (navigateur factice)
    import json as _j2, os as _os, time as _t, urllib.request as _u
    wd = work / "app"
    (wd / "uploads").mkdir(parents=True, exist_ok=True)
    if mp4:
        import shutil as _sh
        _sh.copy2(mp4[0], wd / "uploads" / "v.mp4")
    srv = subprocess.Popen([*PY, str(HERE / "app.py"), "--port", "8899", "--no-browser", "--workdir", str(wd)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base, ok_app, detail = "http://127.0.0.1:8899", False, ""
        for _ in range(40):
            try:
                _u.urlopen(base + "/api/health", timeout=1).read()
                break
            except Exception:  # noqa: BLE001
                _t.sleep(0.25)
        rq = _u.Request(base + "/api/jobs", data=_j2.dumps({"kind": "tool", "options": {"tool": "speed", "factor": "1.2", "source": "v.mp4",
                        "quality": "fast"}}).encode(), method="POST")
        jid = _j2.loads(_u.urlopen(rq).read())["id"]
        for _ in range(120):
            _t.sleep(1)
            v = _j2.loads(_u.urlopen(base + "/api/jobs/" + jid).read())
            if v["status"] not in ("running", "queued"):
                break
        ok_app = v["status"] == "done" and any(o["name"] == "resultat.mp4" for o in v["outputs"])
        detail = v["log"][-200:]
    except Exception as exc:  # noqa: BLE001
        ok_app, detail = False, str(exc)
    finally:
        srv.terminate()
    check("application : serveur + outil de montage (API)", ok_app, detail)

    ok = sum(1 for _, k, _ in results if k)
    print(f"\n{ok}/{len(results)} tests réussis en {time.time() - t0:.0f} s (fichiers : {work})")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

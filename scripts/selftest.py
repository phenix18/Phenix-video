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
        check("dossier de publication", rc == 0 and (o1 / "publish" / "INDEX.md").exists(), out[-300:])

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

    ok = sum(1 for _, k, _ in results if k)
    print(f"\n{ok}/{len(results)} tests réussis en {time.time() - t0:.0f} s (fichiers : {work})")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

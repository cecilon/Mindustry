#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gen_Turret_Complex.py : genere un schematic Mindustry (.msch) viable en une seule commande.

Usage :
    python Gen_Turret_Complex.py <largeur> <hauteur> <ressource1> [ressource2 ...]
        --data <data.json> <sortie.msch>
        [--no-wall]
        [--duree <sec>]
        [--ammo <ammo1> <ammo2> ...]
        [--out <dossier>]

Exemple :
    python Gen_Turret_Complex.py 35 35 silicon titanium copper thorium graphite --data data.json --ammo copper titanium thorium silicon graphite Mindustry_Schemas_Output\\Sh7.msch
    python Gen_Turret_Complex.py 35 35 energy liquids metaglass lead silicon titanium copper thorium graphite plastinium --data data.json --ammo copper titanium thorium plastinium silicon graphite Mindustry_Schemas_Output\Sh11.msch
    
    c'est bcp mieux!

    input: python Gen_Turret_Complex.py 35 35 energy liquids metaglass lead silicon titanium copper thorium graphite --data data.json --ammo copper titanium thorium silicon graphite Mindustry_Schemas_Output\Sh11.msch

    mais
    
Equivalent des etapes manuelles :
    0) npm install -g msch-generate              (si absent)
    1) python turret_complex.py <params>         -> schema.txt, legend.json, ...
    2) python ascii_to_tiles.py schema.txt legend.json tiles.json
    3) node write_msch.mjs tiles.json <sortie.msch>
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
os.environ["PYTHONIOENCODING"] = "utf-8"
HERE = Path(__file__).resolve().parent
IS_WIN = os.name == "nt"


def fail(msg, code=1):
    print("ERREUR : " + msg, file=sys.stderr)
    sys.exit(code)


def run(cmd, what, cwd=None):
    print("\n>>> " + " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, text=True, encoding="utf-8",
                       errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = (r.stdout or "").strip()
    if out:
        lines = out.splitlines()
        if len(lines) > 40:
            lines = lines[:10] + ["   [...]"] + lines[-10:]
        print("\n".join(lines))
    if r.returncode != 0:
        fail("%s a echoue (code %d)." % (what, r.returncode), r.returncode)
    return out


# ------------------------------------------------------------------ prerequis
def ensure_python():
    if sys.version_info < (3, 8):
        fail("Python >= 3.8 requis (version actuelle : %s)." % sys.version.split()[0])
    print("[OK] Python %s" % sys.version.split()[0])


def find_node():
    exe = shutil.which("node")
    if exe:
        return exe
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            cand = Path(base) / "nodejs" / "node.exe"
            if cand.exists():
                return str(cand)
    return None


def ensure_node():
    node = find_node()
    if not node:
        print("[..] Node.js absent : installation en cours.")
        if IS_WIN and shutil.which("winget"):
            subprocess.run(["winget", "install", "--id", "OpenJS.NodeJS.LTS", "-e",
                            "--accept-package-agreements", "--accept-source-agreements"])
            node = find_node()
        if not node:
            fail("Node.js introuvable. Installez-le depuis https://nodejs.org (LTS) puis relancez.")
    os.environ["PATH"] = str(Path(node).parent) + os.pathsep + os.environ.get("PATH", "")
    ver = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
    print("[OK] Node.js %s (%s)" % (ver, node))
    return node


def find_msch_cli():
    cands = []
    if os.environ.get("APPDATA"):
        cands.append(Path(os.environ["APPDATA"]) / "npm" / "node_modules")
    cands.append(Path("/usr/lib/node_modules"))
    cands.append(Path("/usr/local/lib/node_modules"))
    for c in cands:
        cli = c / "msch-generate" / "build" / "cli.js"
        if cli.exists():
            return cli
    npm = find_npm()
    if npm:
        r = subprocess.run([npm, "root", "-g"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            cli = Path(r.stdout.strip().splitlines()[-1]) / "msch-generate" / "build" / "cli.js"
            if cli.exists():
                return cli
    return None


def find_npm():
    return shutil.which("npm.cmd") if IS_WIN else shutil.which("npm")


def ensure_msch(node):
    cli = find_msch_cli()
    if cli is None:
        npm = find_npm()
        if not npm:
            fail("npm introuvable (installe avec Node.js).")
        print("[..] msch-generate absent : npm install -g msch-generate")
        run([npm, "install", "-g", "msch-generate"], "npm install -g msch-generate")
        cli = find_msch_cli()
        if cli is None:
            fail("msch-generate installe mais cli.js introuvable.")
    print("[OK] msch-generate (%s)" % cli)
    return cli


# ------------------------------------------------------------------ arguments
def parse(argv):
    """
    Parse les arguments de Gen_Turret_Complex.py et construit la liste
    de paramètres à passer à turret_complex.py.

    Paramètres reconnus :
        <largeur> <hauteur>           positional obligatoires (2 premiers entiers)
        <ressource> ...               tous les tokens non-flags qui ne sont pas
                                      largeur/hauteur, .json ou .msch
        --data <data.json>            obligatoire
        --ammo <a1> [a2 ...]          optionnel, liste de munitions
        --no-wall                     flag optionnel
        --duree <sec>                 optionnel
        <sortie.msch>                 obligatoire, exactement 1 fichier .msch
    """

    # ── Extraire le .msch ────────────────────────────────────────────────
    msch_list = [a for a in argv if a.lower().endswith(".msch")]
    if len(msch_list) != 1:
        fail("Il faut exactement un fichier de sortie .msch en parametre.", 2)
    msch_path = Path(msch_list[0]).expanduser().resolve()

    # On retire le .msch de la liste de travail
    argv = [a for a in argv if a != msch_list[0]]

    # ── Parser manuellement les flags connus ─────────────────────────────
    data_path   = None
    ammo_list   = []       # valeurs après --ammo
    no_wall     = False
    duree       = None
    ressources  = []
    largeur     = None
    hauteur     = None

    i = 0
    while i < len(argv):
        token = argv[i]

        if token == "--data":
            if i + 1 >= len(argv):
                fail("--data requiert un argument (chemin vers data.json).", 2)
            i += 1
            data_path = argv[i]

        elif token == "--ammo":
            # Consomme tous les tokens suivants qui ne commencent pas par "--"
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                ammo_list.append(argv[i])
                i += 1
            continue   # i déjà avancé

        elif token == "--no-wall":
            no_wall = True

        elif token == "--duree":
            if i + 1 >= len(argv):
                fail("--duree requiert un argument numerique.", 2)
            i += 1
            duree = argv[i]
            
        elif token == "--anti-air":
            i += 1
            anti_air = argv[i]

        else:
            # Token positional : largeur, hauteur, ressources
            # Les 2 premiers entiers sont largeur et hauteur
            if largeur is None:
                try:
                    largeur = int(token)
                except ValueError:
                    fail("Largeur invalide (entier attendu) : %s" % token, 2)
            elif hauteur is None:
                try:
                    hauteur = int(token)
                except ValueError:
                    fail("Hauteur invalide (entier attendu) : %s" % token, 2)
            else:
                # Tout le reste sont des ressources
                ressources.append(token)

        i += 1

    # ── Validations ──────────────────────────────────────────────────────
    if largeur is None or hauteur is None:
        fail("Largeur et hauteur obligatoires.", 2)

    if not ressources:
        fail("Au moins une ressource est requise.", 2)

    if data_path is None:
        fail("--data <data.json> est obligatoire.", 2)

    # Résolution du chemin data.json
    p = Path(data_path)
    if not p.exists() and (HERE / data_path).exists():
        p = HERE / data_path
    if not p.exists():
        fail("Fichier de donnees introuvable : %s" % data_path, 2)
    data_path = str(p.resolve())

    return largeur, hauteur, ressources, data_path, ammo_list, no_wall, duree, msch_path


def build_turret_params(largeur, hauteur, ressources, data_path,
                         ammo_list, no_wall, duree, work_dir):
    """
    Construit la liste d'arguments à passer à turret_complex.py.
    Correspond exactement à l'interface v4.0 de turret_complex.py.
    """
    params = [str(largeur), str(hauteur)] + ressources
    params += ["--data", data_path]
    params += ["--out", str(work_dir)]

    if no_wall:
        params.append("--no-wall")

    if duree is not None:
        params += ["--duree", str(duree)]

    if ammo_list:
        params += ["--ammo"] + ammo_list

    return params


def main():
    largeur, hauteur, ressources, data_path, ammo_list, no_wall, duree, msch_path = parse(
        sys.argv[1:]
    )

    ensure_python()
    node = ensure_node()
    ensure_msch(node)

    for needed in ("turret_complex.py", "ascii_to_tiles.py", "write_msch.mjs"):
        if not (HERE / needed).exists():
            fail("Fichier requis manquant a cote du script : %s" % needed)

    work = msch_path.parent / (msch_path.stem + "_intermediaires")
    work.mkdir(parents=True, exist_ok=True)
    msch_path.parent.mkdir(parents=True, exist_ok=True)
    py = sys.executable

    schema = work / "schema.txt"
    legend = work / "legend.json"
    tiles  = work / "tiles.json"

    for f in (schema, legend, tiles, msch_path):
        if f.exists():
            f.unlink()

    # 1) layout ASCII via turret_complex.py
    turret_params = build_turret_params(
        largeur, hauteur, ressources, data_path,
        ammo_list, no_wall, duree, work
    )
    run([py, HERE / "turret_complex.py"] + turret_params, "turret_complex.py")

    if not schema.exists() or not legend.exists():
        fail("schema.txt / legend.json n'ont pas ete generes.")

    # 2) ASCII -> tuiles
    run([py, HERE / "ascii_to_tiles.py", schema, legend, tiles], "ascii_to_tiles.py")
    if not tiles.exists():
        fail("tiles.json n'a pas ete genere.")

    # 3) tuiles -> .msch
    run([node, HERE / "write_msch.mjs", tiles, msch_path], "write_msch.mjs")
    if not msch_path.exists() or msch_path.stat().st_size == 0:
        fail("Le fichier .msch n'a pas ete cree : %s" % msch_path)

    print("\n[OK] Schematic genere : %s (%d octets)" % (msch_path, msch_path.stat().st_size))
    print("     Intermediaires    : %s" % work)


if __name__ == "__main__":
    main()

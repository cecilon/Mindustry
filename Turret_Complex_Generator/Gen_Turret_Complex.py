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

    input: python Gen_Turret_Complex.py 35 35 energy liquids metaglass lead silicon titanium copper thorium graphite surge-alloy --data data.json --ammo copper titanium thorium silicon graphite surge-alloy Mindustry_Schemas_Output\Sh11.msch

    mais
    
Equivalent des etapes manuelles :
    0) npm install -g msch-generate              (si absent)
    1) python turret_complex.py <params>         -> schema.txt, legend.json, ...
    2) python ascii_to_tiles.py schema.txt legend.json tiles.json
    3) node write_msch.mjs tiles.json <sortie.msch>
"""
import argparse
import os
import sys
import subprocess


def run_step(cmd: list, step_name: str, stream_live: bool = False):
    print(f"\n{'=' * 65}")
    print(f"ETAPE : {step_name}")
    print(f"  Commande : {' '.join(cmd)}")
    print(f"{'=' * 65}")

    if stream_live:
        proc = subprocess.Popen(cmd)
        try:
            proc.wait()
        except KeyboardInterrupt:
            print("\n[ORCHESTRATEUR] Ctrl+C recu : sauvegarde de turret_complex.py en cours...")
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        return

    res = subprocess.run(cmd, text=True, capture_output=True)
    if res.stdout:
        print(res.stdout.strip())
    if res.stderr:
        print(res.stderr.strip(), file=sys.stderr)
    if res.returncode != 0:
        print(f"\nERREUR lors de l'etape '{step_name}' (Code {res.returncode})", file=sys.stderr)
        sys.exit(res.returncode)


def extraire_cible_msch(liste_args: list, defaut_msch: str) -> str:
    for idx in range(len(liste_args) - 1, -1, -1):
        elem = next(iter(liste_args[idx:idx + 1]), "")
        if elem.lower().endswith(".msch"):
            return liste_args.pop(idx)
    return defaut_msch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("largeur", type=int)
    parser.add_argument("hauteur", type=int)
    parser.add_argument("ressources", nargs="+")
    parser.add_argument("--data", default=None)
    parser.add_argument("--no-wall", action="store_true")
    parser.add_argument("--duree", type=float, default=30.0)
    parser.add_argument("--anti-air", type=float, default=15.0)
    parser.add_argument("--ammo", nargs="*", default=None)
    parser.add_argument("--output-msch", default="Turret_Complex.msch")
    parser.add_argument("--work-dir", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--brain", default=None)

    args = parser.parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    ressources = list(args.ressources)
    ammo_list = list(args.ammo) if args.ammo is not None else []

    cible_msch = args.output_msch.strip()
    if ammo_list:
        cible_msch = extraire_cible_msch(ammo_list, cible_msch)
    cible_msch = extraire_cible_msch(ressources, cible_msch)

    data_path = args.data
    for idx in range(len(ressources) - 1, -1, -1):
        elem = next(iter(ressources[idx:idx + 1]), "")
        if elem.lower().endswith(".json"):
            data_path = ressources.pop(idx)
            break
    if not data_path:
        data_path = os.path.join(script_dir, "data.json")

    output_msch = os.path.abspath(cible_msch)
    os.makedirs(os.path.dirname(output_msch), exist_ok=True)
    base_name = next(iter(os.path.splitext(os.path.basename(output_msch))))

    if args.work_dir:
        work_dir = os.path.abspath(args.work_dir)
    else:
        work_dir = os.path.join(os.path.dirname(output_msch), f"{base_name}_intermediaires")
    os.makedirs(work_dir, exist_ok=True)

    turret_script = os.path.join(script_dir, "turret_complex.py")
    ascii_script = os.path.join(script_dir, "ascii_to_tiles.py")
    mjs_script = os.path.join(script_dir, "write_msch.mjs")

    cmd_step1 = [
        sys.executable, "-u", turret_script,
        str(args.largeur), str(args.hauteur),
        *ressources,
        "--data", os.path.abspath(data_path),
        "--duree", str(args.duree),
        "--anti-air", str(args.anti_air),
        "--out", work_dir,
    ]
    if args.no_wall:
        cmd_step1.append("--no-wall")
    if ammo_list:
        cmd_step1.extend(["--ammo", *ammo_list])
    if args.train:
        cmd_step1.append("--train")
    if args.brain:
        cmd_step1.extend(["--brain", os.path.abspath(args.brain)])

    run_step(cmd_step1, "1/3 - Optimisation du Complexe (turret_complex.py)", stream_live=args.train)

    schema_txt = os.path.join(work_dir, "schema.txt")
    legend_json = os.path.join(work_dir, "legend.json")
    tiles_json = os.path.join(work_dir, "tiles_input.json")

    cmd_step2 = [sys.executable, ascii_script, schema_txt, legend_json, tiles_json]
    run_step(cmd_step2, "2/3 - Conversion ASCII vers Tuiles Mindustry (ascii_to_tiles.py)")

    cmd_step3 = ["node", mjs_script, tiles_json, output_msch]
    run_step(cmd_step3, "3/3 - Compilation Binaire Mindustry .msch (write_msch.mjs)")

    print(f"\nSUCCES TOTAL ! Fichier .msch genere : {output_msch}")
    print(f"Fichiers intermediaires et rapports : {work_dir}")


if __name__ == "__main__":
    main()

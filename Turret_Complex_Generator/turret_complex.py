#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
import sys
import os
import argparse
import string
import time
import random
import signal

from copy import deepcopy
from dataclasses import dataclass, field
from typing import List, Tuple, Set
from collections import defaultdict
from itertools import islice, combinations

SEUIL_LOGISTIQUE = 0.99
TOLERANCE_FLOTTANTE = 0.01
TEMPS_MAX_EXECUTION = 1800
CAPACITES_SPECIALES = {"energy", "liquids", "utilities"}

CHAR_RESERVOIR = [
    ch for ch in (
        string.ascii_uppercase +
        string.ascii_lowercase +
        string.digits +
        "!@#$%^&()-_=+[]{}|;:,.<>?/"
    ) if ch not in ('*', ' ', '"', "'", '\\')
]

PORTES_EXACTES = {
    "duo": 20.0, "scatter": 22.5, "scorch": 7.5, "hail": 29.375, "arc": 11.25,
    "wave": 13.75, "lancer": 20.625, "salvo": 19.0, "swarmer": 30.0,
    "ripple": 36.25, "cyclone": 25.0, "fuse": 11.25, "spectre": 32.5,
    "meltdown": 24.375, "foreshadow": 62.5, "tsunami": 23.75, "parallax": 28.75,
}

PORTES_SOIN_PHASE = {
    "mender": 8.5,
    "mend-projector": 16.25,
    "force-projector": 17.7,
    "overdrive-projector": 16.875,
    "overdrive-dome": 10.625,
}

GROUPE_AA_PUR = {"scatter", "parallax"}
GROUPE_AA_TOUS = {"scatter", "parallax", "swarmer", "cyclone"}
SYNONYMES_MAT = {"plastinum": "plastanium", "plastinium": "plastanium"}


@dataclass
class Bloc:
    id: str
    nom: str
    largeur: int = 1
    hauteur: int = 1
    rotation: int = 0
    type: str = "generique"
    kind: str = ""
    materiaux: dict = field(default_factory=dict)
    capacites: set = field(default_factory=set)
    dps_brut: float = 0.0
    portee: float = 0.0
    rate: float = 1.0
    speed_boost: float = 1.0
    consomme_energie: bool = False
    energy_consume_rate: float = 0.0
    energy_stored: float = 0.0
    consomme_liquide: bool = False
    targets_air: bool = False
    targets_ground: bool = True
    laser_range: float = 6.0
    max_links: int = 10
    ammo_type: str = ""
    best_ammo: str = ""
    ammo_optional: bool = True
    ammo_dps: dict = field(default_factory=dict)
    health: float = 0.0
    vitesse_transport: float = 0.0
    dps_par_taille: float = 0.0
    dps_par_cout: float = 0.0
    dps_reel: float = 0.0
    dps_par_surface: float = 0.0
    x: int = 0
    y: int = 0
    char: str = ""
    pair_char: str = ""

    def taille(self) -> int:
        return self.largeur * self.hauteur

    def cout_total(self) -> float:
        total_mat = sum(self.materiaux.values())
        return total_mat if total_mat > 0 else 1.0


class Grille:
    def __init__(self, largeur: int, hauteur: int):
        self.largeur = largeur
        self.hauteur = hauteur
        self.cellules = [[None] * largeur for _ in range(hauteur)]

    def peut_placer(self, elem: Bloc, pos_x: int, pos_y: int) -> bool:
        if pos_x < 0 or pos_y < 0 or pos_x + elem.largeur > self.largeur or pos_y + elem.hauteur > self.hauteur:
            return False
        for dec_y in range(elem.hauteur):
            for dec_x in range(elem.largeur):
                if self.cellules[pos_y + dec_y][pos_x + dec_x] is not None:
                    return False
        return True

    def placer(self, elem: Bloc, pos_x: int, pos_y: int):
        elem.x = pos_x
        elem.y = pos_y
        for dec_y in range(elem.hauteur):
            for dec_x in range(elem.largeur):
                self.cellules[pos_y + dec_y][pos_x + dec_x] = elem

    def retirer(self, elem: Bloc):
        for dec_y in range(elem.hauteur):
            for dec_x in range(elem.largeur):
                cy = elem.y + dec_y
                cx = elem.x + dec_x
                if 0 <= cy < self.hauteur and 0 <= cx < self.largeur:
                    if self.cellules[cy][cx] is elem:
                        self.cellules[cy][cx] = None

    def liberer_zone(self, x_deb: int, y_deb: int, larg: int, haut: int, registre: list = None):
        deja_vus = set()
        for cy in range(max(0, y_deb), min(self.hauteur, y_deb + haut)):
            for cx in range(max(0, x_deb), min(self.largeur, x_deb + larg)):
                occ = self.cellules[cy][cx]
                if occ is not None and id(occ) not in deja_vus:
                    deja_vus.add(id(occ))
                    self.retirer(occ)
                    if registre is not None and occ in registre:
                        registre.remove(occ)

    def surface_utilisee_reelle(self) -> int:
        deja_vus = set()
        cumul = 0
        for ligne in self.cellules:
            for case in ligne:
                if case is not None and id(case) not in deja_vus:
                    deja_vus.add(id(case))
                    cumul += case.taille()
        return cumul


def phase0_validation(larg_g: int, haut_g: int, liste_res: list, chemin_json: str) -> Tuple[set, set]:
    if not (5 <= larg_g <= 100 and 5 <= haut_g <= 100):
        raise ValueError(f"Dimensions hors bornes: {larg_g}x{haut_g}")
    if not os.path.isfile(chemin_json):
        raise FileNotFoundError(f"Introuvable: {chemin_json}")
    normees = [SYNONYMES_MAT.get(r.lower(), r.lower()) for r in liste_res]
    ens_mat = {r for r in normees if r not in CAPACITES_SPECIALES}
    ens_cap = {r for r in normees if r in CAPACITES_SPECIALES}
    return ens_mat, ens_cap

def fabricable(elem: Bloc, ens_mat: set, ens_cap: set) -> bool:
    return (set(elem.materiaux.keys()) <= ens_mat and elem.capacites <= ens_cap)


def ammo_autorisee(elem: Bloc, ens_ammo: set) -> bool:
    if not ens_ammo or elem.ammo_optional or not elem.ammo_type or elem.ammo_type == "power":
        return True
    if elem.ammo_dps:
        if "power" in elem.ammo_dps:
            return True
        return bool(set(elem.ammo_dps.keys()) & ens_ammo)
    return elem.ammo_type in ens_ammo


def parse_bloc(info: dict, cat_bloc: str, ens_cap: set) -> Bloc:
    ident = info.get("id", info.get("nom", "unknown"))
    couts_mat = {
        cle[5:]: val for cle, val in info.items()
        if cle.startswith("cost_") and isinstance(val, (int, float)) and val > 0
    }
    conso_elec = float(info.get("energy_consume", 0.0) or 0.0)
    stock_elec = float(info.get("stored", 0.0) or 0.0)
    besoin_elec = conso_elec > 0
    req_cap = set(info.get("capacites", []))
    liste_boost = info.get("boosters", [])
    prend_liq = (bool(liste_boost) or "liquids" in req_cap) and ("liquids" in ens_cap)
    debit = float(info.get("speed", info.get("flow", info.get("vitesse_transport", 0.0))) or 0.0)
    portee_laser = float(info.get("laser_range", 6.0) or 6.0)
    liens_max = int(info.get("laser_links", 10) or 10)
    mult_vit = float(info.get("speed_boost", 1.0) or 1.0)
    cible_air = (ident in GROUPE_AA_TOUS)
    cible_sol = (ident not in GROUPE_AA_PUR)

    if cat_bloc == "soin":
        portee_tir = info.get("range_phase_boost", PORTES_SOIN_PHASE.get(ident, info.get("range", 0.0)))
    else:
        portee_tir = PORTES_EXACTES.get(ident, info.get("range", info.get("portee", 0.0)))

    return Bloc(
        id=ident,
        nom=info.get("name_fr", info.get("nom", ident)),
        largeur=info.get("width", info.get("largeur", 1)),
        hauteur=info.get("height", info.get("hauteur", 1)),
        rotation=info.get("rotation", 0),
        type=cat_bloc,
        kind=info.get("kind", info.get("role", "")),
        materiaux=couts_mat,
        capacites=req_cap,
        dps_brut=float(info.get("dps", info.get("dps_brut", 0.0))),
        portee=float(portee_tir),
        rate=float(info.get("rate", 1.0) or 1.0),
        speed_boost=mult_vit,
        consomme_energie=besoin_elec,
        energy_consume_rate=conso_elec,
        energy_stored=stock_elec,
        consomme_liquide=prend_liq,
        targets_air=bool(cible_air),
        targets_ground=bool(cible_sol),
        laser_range=portee_laser,
        max_links=liens_max,
        ammo_type=info.get("ammo_type", ""),
        ammo_optional=info.get("ammo_optional", False if cat_bloc == "turret" else True),
        ammo_dps=info.get("ammo_dps", {}),
        health=float(info.get("health", 0.0)),
        vitesse_transport=debit,
    )


def calculer_dps_reel(elem: Bloc, ens_ammo: set) -> Tuple[float, str]:
    if elem.ammo_dps and ens_ammo:
        options = [(v_dps, nom_a) for nom_a, v_dps in elem.ammo_dps.items() if nom_a in ens_ammo or nom_a == "power"]
        if options:
            options.sort(reverse=True)
            meilleur_dps, meilleure_ammo = next(iter(options))
            return float(meilleur_dps), str(meilleure_ammo)
    if elem.ammo_dps:
        options = [(v_dps, nom_a) for nom_a, v_dps in elem.ammo_dps.items()]
        options.sort(reverse=True)
        if options:
            meilleur_dps, meilleure_ammo = next(iter(options))
            return float(meilleur_dps), str(meilleure_ammo)
    return float(elem.dps_brut), str(elem.ammo_type or "")


def phase2_ciblage(liste_t: list, larg_g: int, haut_g: int) -> Tuple[float, float, Tuple[float, float], int]:
    if not liste_t:
        raise ValueError("Aucune tourelle disponible.")
    p_max = max(t.portee for t in liste_t)
    dist_c = 8
    pos_c = (larg_g / 2.0, -8.0)
    return p_max, dist_c, pos_c, haut_g


def calculer_zone_tourelles(larg_g: int, haut_g: int, sans_mur: bool) -> Tuple[Tuple[int, int, int, int], int, str]:
    if sans_mur:
        return (0, larg_g, 0, haut_g), 0, "none"
    dim_m = max(larg_g, haut_g)
    if dim_m < 10:
        return (0, larg_g, 0, haut_g - 1), 1, "simple_rear_line"
    elif dim_m <= 12:
        return (1, larg_g - 1, 1, haut_g - 1), 1, "small_lateral_loop"
    else:
        return (2, larg_g - 2, 2, haut_g - 2), 2, "large_2x2_loop"

def phase1_chargement(chemin_json: str, ens_mat: set, ens_cap: set, ens_ammo: set):
    with open(chemin_json, "r", encoding="utf-8") as flux_f:
        donnees = json.load(flux_f)

    cat_tourelles = []
    cat_logistique = []
    cat_liquides = []
    cat_protection = []
    cat_energie = []
    cat_soin = []

    brut_off = dict(donnees.get("turrets_offense", {}))
    brut_off.setdefault("scatter", {
        "name_fr": "Eparpilleur", "dps": 90, "ammo_type": "lead", "rate": 6.6, "range": 22.5,
        "ammo_dps": {"scrap": 45, "lead": 65, "metaglass": 90},
        "cost_copper": 85, "cost_lead": 45, "width": 2, "height": 2,
        "targets_air": True, "targets_ground": False, "boosters": ["water", "cryofluid"]
    })

    for cle_id, desc in brut_off.items():
        if not isinstance(desc, dict):
            continue
        desc = dict(desc, id=cle_id)
        if cle_id in ("meltdown", "spectre", "foreshadow"):
            desc["width"] = 4
            desc["height"] = 4
        elif cle_id in ("wave", "parallax", "scatter"):
            desc["width"] = 2
            desc["height"] = 2
        if cle_id == "foreshadow":
            desc.setdefault("cost_surge-alloy", 300)
            desc.setdefault("cost_plastanium", 200)
            desc["ammo_type"] = "surge-alloy"
            desc["ammo_dps"] = {"surge-alloy": desc.get("dps", 500)}
        elif cle_id == "cyclone":
            desc["ammo_type"] = "plastanium"
            desc["ammo_dps"] = {"metaglass": 120, "plastanium": 190, "surge-alloy": 260, "blast-compound": 180}
        elif cle_id == "ripple":
            d_ammo = dict(desc.get("ammo_dps", {"graphite": 132, "silicon": 132, "pyratite": 180}))
            d_ammo.setdefault("plastanium", 160)
            desc["ammo_dps"] = d_ammo
        elif cle_id == "swarmer":
            d_ammo = dict(desc.get("ammo_dps", {"thorium": 60}))
            d_ammo.setdefault("plastanium", 180)
            d_ammo.setdefault("pyratite", 140)
            d_ammo.setdefault("surge-alloy", 240)
            desc["ammo_dps"] = d_ammo
        elif cle_id in ("meltdown", "tsunami", "wave", "parallax"):
            desc["ammo_type"] = "power"
            desc["ammo_dps"] = {"power": desc.get("dps", 180)}
        obj_b = parse_bloc(desc, "turret", ens_cap)
        if not fabricable(obj_b, ens_mat, ens_cap) or not ammo_autorisee(obj_b, ens_ammo):
            continue
        if obj_b.dps_brut <= 0 or obj_b.portee <= 0 or (obj_b.consomme_energie and "energy" not in ens_cap):
            continue
        obj_b.dps_reel, obj_b.best_ammo = calculer_dps_reel(obj_b, ens_ammo)
        obj_b.dps_par_taille = obj_b.dps_reel / obj_b.taille()
        obj_b.dps_par_cout = obj_b.dps_reel / obj_b.cout_total()
        obj_b.dps_par_surface = obj_b.dps_par_taille
        cat_tourelles.append(obj_b)

    brut_dist = dict(donnees.get("distribution_blocks", {}))
    brut_dist.setdefault("container", {"width": 2, "height": 2, "kind": "storage", "cost_titanium": 100})
    brut_dist.setdefault("vault", {"width": 3, "height": 3, "kind": "storage", "cost_titanium": 250, "cost_thorium": 125})
    for cle_id, desc in brut_dist.items():
        obj_b = parse_bloc(dict(desc, id=cle_id), "logistique", ens_cap)
        if fabricable(obj_b, ens_mat, ens_cap):
            cat_logistique.append(obj_b)

    brut_liq = dict(donnees.get("liquid_blocks", {}))
    brut_liq.setdefault("pulse-conduit", {"width": 1, "height": 1, "kind": "conduit", "flow": 16, "cost_titanium": 2, "cost_metaglass": 1})
    brut_liq.setdefault("liquid-router", {"width": 1, "height": 1, "kind": "router", "flow": 4, "cost_graphite": 4, "cost_metaglass": 2})
    brut_liq.setdefault("bridge-conduit", {"width": 1, "height": 1, "kind": "bridge", "flow": 4, "range": 4, "cost_graphite": 4, "cost_metaglass": 8})
    brut_liq.setdefault("liquid-container", {"width": 2, "height": 2, "kind": "storage", "flow": 0, "cost_titanium": 10, "cost_metaglass": 15})
    for cle_id, desc in brut_liq.items():
        if "pump" in cle_id.lower() or "extractor" in cle_id.lower():
            continue
        obj_b = parse_bloc(dict(desc, id=cle_id), "liquide", ens_cap)
        if not obj_b.kind:
            obj_b.kind = "bridge" if "bridge" in cle_id else ("storage" if ("tank" in cle_id or "container" in cle_id) else ("router" if "router" in cle_id else "conduit"))
        if fabricable(obj_b, ens_mat, ens_cap):
            cat_liquides.append(obj_b)

    for cle_id, desc in donnees.get("walls", {}).items():
        obj_b = parse_bloc(dict(desc, id=cle_id), "protection", ens_cap)
        if fabricable(obj_b, ens_mat, ens_cap):
            cat_protection.append(obj_b)

    brut_en = dict(donnees.get("energy_sources", {}))
    brut_en.setdefault("power-node", {"role": "node", "laser_links": 10, "laser_range": 6.0, "width": 1, "height": 1, "cost_copper": 1, "cost_lead": 3})
    brut_en.setdefault("power-node-large", {"role": "node", "laser_links": 15, "laser_range": 15.0, "width": 2, "height": 2, "cost_titanium": 5, "cost_lead": 10, "cost_silicon": 3})
    brut_en.setdefault("surge-tower", {"role": "node", "laser_links": 2, "laser_range": 30.0, "width": 2, "height": 2, "cost_titanium": 7, "cost_lead": 10, "cost_silicon": 15, "cost_surge-alloy": 15})
    brut_en.setdefault("battery", {"role": "battery", "stored": 4000, "width": 1, "height": 1, "cost_copper": 5, "cost_lead": 20})
    brut_en.setdefault("battery-large", {"role": "battery", "stored": 50000, "width": 3, "height": 3, "cost_titanium": 20, "cost_lead": 50, "cost_silicon": 30})
    for cle_id, desc in brut_en.items():
        desc = dict(desc, id=cle_id)
        if "battery" in cle_id:
            desc["kind"] = "battery"
            if cle_id == "battery" and desc.get("stored", 0) < 4000:
                desc["stored"] = 4000
        elif "node" in cle_id or "tower" in cle_id:
            desc["kind"] = "node"
        else:
            desc["kind"] = "generator"
        obj_b = parse_bloc(desc, "energie", ens_cap)
        if fabricable(obj_b, ens_mat, ens_cap):
            cat_energie.append(obj_b)

    brut_prot = dict(donnees.get("turrets_protection", {}))
    brut_prot.setdefault("force-projector", {"width": 3, "height": 3, "kind": "shield", "range": 12.7, "range_phase_boost": 17.7, "energy_consume": 240, "cost_lead": 100, "cost_titanium": 75, "cost_silicon": 125, "boosters": ["water", "cryofluid"]})
    brut_prot.setdefault("overdrive-projector", {"width": 2, "height": 2, "kind": "overdrive", "range": 10.0, "range_phase_boost": 16.875, "speed_boost": 2.25, "energy_consume": 210, "cost_lead": 100, "cost_titanium": 75, "cost_silicon": 75, "cost_plastanium": 30})
    brut_prot.setdefault("overdrive-dome", {"width": 3, "height": 3, "kind": "overdrive", "range": 10.625, "range_phase_boost": 10.625, "speed_boost": 2.5, "energy_consume": 450, "cost_lead": 200, "cost_titanium": 130, "cost_silicon": 130, "cost_plastanium": 80, "cost_surge-alloy": 120})
    for cle_id, desc in brut_prot.items():
        desc = dict(desc, id=cle_id)
        if not desc.get("kind"):
            desc["kind"] = "shield" if "force" in cle_id else ("overdrive" if "overdrive" in cle_id else "healer")
        obj_b = parse_bloc(desc, "soin", ens_cap)
        if (not obj_b.consomme_energie or "energy" in ens_cap) and fabricable(obj_b, ens_mat, ens_cap):
            cat_soin.append(obj_b)

    cat_tourelles.sort(key=lambda t: (-t.dps_par_surface, -t.dps_reel))
    cat_logistique.sort(key=lambda l: (0 if l.kind == "conveyor" else 1, -l.vitesse_transport))
    cat_liquides.sort(key=lambda lq: (0 if lq.kind == "conduit" else 1, -lq.vitesse_transport))
    cat_protection.sort(key=lambda w: (-w.health, w.cout_total()))
    return cat_tourelles, cat_logistique, cat_liquides, cat_protection, cat_energie, cat_soin

def _lignes_couloirs_internes(cadre_z: Tuple[int, int, int, int], larg_g: int,
                              haut_g: int, mode_liq: bool = False,
                              pas_force: int = 0) -> Tuple[Set[int], Set[int]]:
    bx_min, bx_max, by_min, by_max = cadre_z
    if min(larg_g, haut_g) < 10:
        return {max(by_min, by_max - 1)}, set()

    ens_ammo = {by_min, by_max - 1}
    ens_liq = set()

    if mode_liq and (by_max - by_min) >= 14:
        yl_bas = by_max - 2
        ens_liq.add(yl_bas)
        ya_bas = yl_bas - 4
        if ya_bas > by_min + 4:
            ens_ammo.add(ya_bas)
        else:
            ya_bas = yl_bas

        cur_y = by_min
        est_tour_liq = True
        idx_rang = 0
        while True:
            reste_y = ya_bas - cur_y
            if reste_y <= 5:
                break
            if pas_force in (4, 5) and cur_y + pas_force <= ya_bas - 4:
                saut_y = pas_force
            else:
                saut_y = 4 if (idx_rang == 0 or cur_y >= 20) else 5
            if cur_y + saut_y >= ya_bas - 3:
                if est_tour_liq and (ya_bas - cur_y) >= 7:
                    ens_liq.add(cur_y + (ya_bas - cur_y) // 2)
                break
            cur_y += saut_y
            if est_tour_liq:
                ens_liq.add(cur_y)
            else:
                ens_ammo.add(cur_y)
            est_tour_liq = not est_tour_liq
            idx_rang += 1
    else:
        cur_y = by_min + 5
        while cur_y < by_max - 3:
            ens_ammo.add(cur_y)
            cur_y += 5

    return ens_ammo, ens_liq


def _zone_interieure_tourelles(cadre_z: Tuple[int, int, int, int], larg_g: int,
                               haut_g: int, mode_liq: bool = False) -> Tuple[int, int, int, int]:
    bx_min, bx_max, by_min, by_max = cadre_z
    if min(larg_g, haut_g) >= 14:
        pad_g = 3 if mode_liq else 1
        pad_d = 4 if mode_liq else 2
        return (bx_min + pad_g, bx_max - pad_d, by_min + 1, by_max - 1)
    return (bx_min + 1, max(bx_min + 2, bx_max - 1), by_min + 1, max(by_min + 2, by_max - 1))


def placer_soin_minimal_avant(plan_g: Grille, liste_soin: list,
                              cadre_z: Tuple[int, int, int, int], larg_g: int,
                              haut_g: int, sans_mur: bool, mode_liq: bool = False) -> list:
    soigneurs = [s for s in liste_soin if s.kind == "healer" or s.id in ("mender", "mend-projector")]
    if not soigneurs:
        return []

    bx_min, bx_max, by_min, by_max = cadre_z
    ix_g, ix_d, _, _ = _zone_interieure_tourelles(cadre_z, larg_g, haut_g, mode_liq)
    ens_ammo, ens_liq = _lignes_couloirs_internes(cadre_z, larg_g, haut_g, mode_liq)

    points_cibles = set()
    for py in range(haut_g):
        for px in range(larg_g):
            points_cibles.add((px, py))

    tri_soin = sorted(soigneurs, key=lambda s: (-s.portee, s.taille()))
    deja_couverts = set()
    blocs_poses = []

    vus_id = set()
    for py in range(plan_g.hauteur):
        for px in range(plan_g.largeur):
            occ = plan_g.cellules[py][px]
            if occ is not None and occ.type == "soin" and occ.kind == "healer" and id(occ) not in vus_id:
                vus_id.add(id(occ))
                mil_x = occ.x + occ.largeur / 2.0
                mil_y = occ.y + occ.hauteur / 2.0
                for tx, ty in points_cibles:
                    if math.hypot((tx + 0.5) - mil_x, (ty + 0.5) - mil_y) <= occ.portee:
                        deja_couverts.add((tx, ty))

    while len(deja_couverts) < len(points_cibles):
        opt_proto = None
        opt_pos = None
        opt_val = (-1, -1)
        opt_ens = set()
        for proto_s in tri_soin:
            ray_s = proto_s.portee
            for py in range(by_max - proto_s.hauteur - 1, by_min, -1):
                if any((py + dy) in ens_ammo or (py + dy) in ens_liq for dy in range(proto_s.hauteur)):
                    continue
                for px in range(ix_g, ix_d - proto_s.largeur + 1, 2):
                    if not plan_g.peut_placer(proto_s, px, py):
                        continue
                    mil_x = px + proto_s.largeur / 2.0
                    mil_y = py + proto_s.hauteur / 2.0
                    ens_loc = set()
                    for tx, ty in points_cibles:
                        if math.hypot((tx + 0.5) - mil_x, (ty + 0.5) - mil_y) <= ray_s:
                            ens_loc.add((tx, ty))
                    apport = len(ens_loc - deja_couverts)
                    marge_arr = min(py - by_min, 8)
                    if apport > 0 and (apport, marge_arr) > opt_val:
                        opt_val = (apport, marge_arr)
                        opt_proto = proto_s
                        opt_pos = (px, py)
                        opt_ens = ens_loc

        if opt_proto is None:
            break
        nouv_s = deepcopy(opt_proto)
        pos_x, pos_y = opt_pos
        plan_g.placer(nouv_s, pos_x, pos_y)
        blocs_poses.append(nouv_s)
        deja_couverts.update(opt_ens)

    return blocs_poses


def _couloir_proche(elem_t: Bloc, pos_y: int, ens_lignes: set) -> int:
    for lig_c in sorted(ens_lignes):
        if lig_c == pos_y - 1 or lig_c == pos_y + elem_t.hauteur:
            return lig_c
    return -1


def distance_a_cible(elem_t: Bloc, pos_x: int, pos_y: int, lim_cible_y: int) -> float:
    return abs((pos_y + elem_t.hauteur / 2.0) - lim_cible_y)


def peut_couvrir_cible(elem_t: Bloc, pos_x: int, pos_y: int, lim_cible_y: int) -> bool:
    return distance_a_cible(elem_t, pos_x, pos_y, lim_cible_y) <= elem_t.portee


def selectionner_top_2_munitions(liste_t: list, ens_ammo: set, lim_cible_y: int,
                                 y_dep: int, y_arr: int = 30,
                                 paire_imposee: Tuple[str, str] = None) -> Tuple[List[str], List[Bloc]]:
    val_poly = defaultdict(float)
    val_lourd = defaultdict(float)
    for obj_t in liste_t:
        for nom_a, v_dps in (obj_t.ammo_dps or {}).items():
            if nom_a == "power" or (ens_ammo and nom_a not in ens_ammo):
                continue
            ratio_d = float(v_dps) / obj_t.taille()
            if ratio_d > val_poly[nom_a]:
                val_poly[nom_a] = ratio_d
            if obj_t.portee >= 29.0 or obj_t.largeur >= 4:
                val_lourd[nom_a] += ratio_d * (1.5 if obj_t.portee >= 32.0 else 1.0)

    if paire_imposee:
        duo_ammo = list(paire_imposee)
    else:
        duo_ammo = list(islice(sorted(val_poly.keys(), key=lambda a: (-val_poly[a], a)), 0, 2))
        a_presage = any(t.id == "foreshadow" for t in liste_t)
        if not a_presage and y_arr > 24 and "graphite" in val_lourd and "graphite" not in duo_ammo:
            duo_ammo = [next(iter(duo_ammo)), "graphite"] if duo_ammo else ["graphite"]
        elif val_lourd and not any(a in val_lourd for a in duo_ammo):
            meill_l = max(val_lourd.keys(), key=lambda a: val_lourd[a])
            duo_ammo = [next(iter(duo_ammo)), meill_l] if duo_ammo else [meill_l]

    ens_duo = set(duo_ammo)
    retenues = []
    for obj_t in liste_t:
        copie_t = deepcopy(obj_t)
        if copie_t.ammo_type == "power" or "power" in copie_t.ammo_dps:
            copie_t.best_ammo = "power"
            retenues.append(copie_t)
            continue
        paires_v = sorted([(v_dps, nom_a) for nom_a, v_dps in copie_t.ammo_dps.items() if nom_a in ens_duo], reverse=True)
        if paires_v:
            v_opt, n_opt = next(iter(paires_v))
            copie_t.dps_reel = float(v_opt)
            copie_t.best_ammo = str(n_opt)
            copie_t.dps_par_taille = copie_t.dps_reel / copie_t.taille()
            copie_t.dps_par_surface = copie_t.dps_par_taille
            copie_t.dps_par_cout = copie_t.dps_reel / copie_t.cout_total()
            retenues.append(copie_t)
    return duo_ammo, retenues

def _preplacer_foreshadow_et_aa(plan_g: Grille, liste_t: list, bornes_i: Tuple[int, int, int, int],
                                ens_ammo: set, ens_liq: set, lim_cible_y: int,
                                quota_aa: float, map_ammo_yc: dict, liste_posees: list):
    ix_g, ix_d, iy_h, iy_b = bornes_i
    aire_u = max(10, (ix_d - ix_g) * (iy_b - iy_h - len(ens_ammo) - len(ens_liq)))
    nb_estime = max(10, int(aire_u / 8.5))
    plafond_par = max(1, int(0.10 * nb_estime))
    plafond_pre = max(1, int(0.05 * nb_estime))
    obj_par = min(plafond_par, max(1, int(round(0.06 * nb_estime))))

    proto_pre = next((t for t in liste_t if t.id == "foreshadow"), None)
    cpt_pre = 0
    if proto_pre:
        larg_f, haut_f = proto_pre.largeur, proto_pre.hauteur
        for py in range(iy_b - haut_f, iy_h - 1, -1):
            if cpt_pre >= plafond_pre:
                break
            if any((py + dy) in ens_ammo or (py + dy) in ens_liq for dy in range(haut_f)):
                continue
            yc_adj = _couloir_proche(proto_pre, py, ens_ammo)
            if yc_adj == -1 or (yc_adj in map_ammo_yc and map_ammo_yc[yc_adj] != proto_pre.best_ammo):
                continue
            for px in range(ix_g, ix_d - larg_f + 1, 4):
                if cpt_pre >= plafond_pre:
                    break
                if plan_g.peut_placer(proto_pre, px, py):
                    inst_f = deepcopy(proto_pre)
                    plan_g.placer(inst_f, px, py)
                    liste_posees.append(inst_f)
                    map_ammo_yc[yc_adj] = inst_f.best_ammo
                    cpt_pre += 1

    proto_par = next((t for t in liste_t if t.id == "parallax"), None)
    if proto_par:
        larg_a, haut_a = proto_par.largeur, proto_par.hauteur
        deja_aa = []
        pts_ancres = [(ix_g, iy_h), (ix_d - 2, iy_h), (ix_g, iy_b - 2), (ix_d - 2, iy_b - 2)]
        while len(deja_aa) < obj_par:
            opt_coord = None
            opt_eloign = -1.0
            for py in range(iy_h, iy_b - haut_a + 1):
                if any((py + dy) in ens_ammo or (py + dy) in ens_liq for dy in range(haut_a)):
                    continue
                if not peut_couvrir_cible(proto_par, ix_g, py, lim_cible_y):
                    continue
                touches_liq = (_couloir_proche(proto_par, py, ens_liq) != -1)
                touches_ammo = (_couloir_proche(proto_par, py, ens_ammo) != -1)
                if not touches_liq and not touches_ammo:
                    continue
                for px in (ix_g, ix_d - larg_a):
                    if not (ix_g <= px <= ix_d - larg_a) or not plan_g.peut_placer(proto_par, px, py):
                        continue
                    rep_pts = [(a.x, a.y) for a in deja_aa] if deja_aa else pts_ancres
                    dist_m = min(math.hypot(px - rx, py - ry) for rx, ry in rep_pts)
                    bonus_liq = 2.0 if touches_liq else 0.0
                    if (dist_m + bonus_liq) > opt_eloign:
                        opt_eloign = dist_m + bonus_liq
                        opt_coord = (px, py)
            if opt_coord is None or (deja_aa and opt_eloign < 4.0):
                break
            cx, cy = opt_coord
            inst_a = deepcopy(proto_par)
            plan_g.placer(inst_a, cx, cy)
            liste_posees.append(inst_a)
            deja_aa.append(inst_a)


def remplir_glouton_stratifie(plan_g: Grille, liste_t: list, cadre_z: Tuple[int, int, int, int],
                              lim_cible_y: int, mode_liq: bool, quota_aa: float = 0.15,
                              dict_gene_ammo: dict = None, mode_gabarit: int = 0,
                              pas_force: int = 0) -> list:
    bornes_i = _zone_interieure_tourelles(cadre_z, plan_g.largeur, plan_g.hauteur, mode_liq)
    ix_g, ix_d, iy_h, iy_b = bornes_i
    ens_ammo, ens_liq = _lignes_couloirs_internes(cadre_z, plan_g.largeur, plan_g.hauteur, mode_liq, pas_force)
    lignes_toutes = sorted(ens_ammo | ens_liq)

    lourdes_4x4 = sorted(
        [t for t in liste_t if t.largeur == 4 and t.id != "foreshadow"],
        key=lambda t: (-t.dps_par_surface, -t.portee)
    )
    offensives_sol = sorted(
        [t for t in liste_t if t.targets_ground and t.id != "foreshadow"],
        key=lambda t: (-t.taille() if mode_gabarit == 1 else 0, -round(t.dps_par_surface, 1), -t.portee, -t.dps_reel)
    )
    elec_sans_ammo = sorted(
        [t for t in liste_t if t.best_ammo == "power" and t.id != "parallax"],
        key=lambda t: (-t.dps_par_surface, -t.portee)
    )

    marqueur_res = Bloc(id="__res__", nom="Res", largeur=1, hauteur=1)
    coords_res = []
    for py in range(iy_h, iy_b):
        for px in range(ix_g, ix_d):
            if (py in ens_ammo or py in ens_liq) and plan_g.cellules[py][px] is None:
                plan_g.cellules[py][px] = marqueur_res
                coords_res.append((px, py))

    liste_posees = []
    map_ammo_yc = dict(dict_gene_ammo) if dict_gene_ammo else {}
    _preplacer_foreshadow_et_aa(
        plan_g, liste_t, bornes_i, ens_ammo, ens_liq,
        lim_cible_y, quota_aa, map_ammo_yc, liste_posees
    )

    for py in range(iy_h, iy_b):
        if py in ens_ammo or py in ens_liq:
            continue
        proch_c = next((cy for cy in lignes_toutes if cy > py), iy_b)
        haut_disp = proch_c - py
        touche_liq_seul = ((py - 1) in ens_liq or (py + 2) in ens_liq) and ((py - 1) not in ens_ammo)
        if haut_disp == 4:
            seq_cand = lourdes_4x4 + [t for t in offensives_sol if t.largeur < 4]
        elif touche_liq_seul and haut_disp <= 2:
            seq_cand = elec_sans_ammo + offensives_sol
        else:
            seq_cand = offensives_sol

        for px in range(ix_g, ix_d):
            if plan_g.cellules[py][px] is not None:
                continue
            for proto_t in seq_cand:
                if px + proto_t.largeur > ix_d or py + proto_t.hauteur > iy_b:
                    continue
                if not peut_couvrir_cible(proto_t, px, py, lim_cible_y):
                    continue
                yc_adj = _couloir_proche(proto_t, py, ens_ammo)
                if proto_t.best_ammo and proto_t.best_ammo != "power":
                    if yc_adj == -1 or (yc_adj in map_ammo_yc and map_ammo_yc[yc_adj] != proto_t.best_ammo):
                        continue
                if mode_liq and proto_t.consomme_liquide and ens_liq:
                    if _couloir_proche(proto_t, py, ens_liq) == -1 and not (px == ix_g or px + proto_t.largeur == ix_d):
                        continue
                if plan_g.peut_placer(proto_t, px, py):
                    inst_t = deepcopy(proto_t)
                    plan_g.placer(inst_t, px, py)
                    liste_posees.append(inst_t)
                    if yc_adj != -1 and inst_t.best_ammo and inst_t.best_ammo != "power":
                        map_ammo_yc[yc_adj] = inst_t.best_ammo
                    break

    for rx, ry in coords_res:
        if plan_g.cellules[ry][rx] is marqueur_res:
            plan_g.cellules[ry][rx] = None
    return liste_posees

def _placer_boucliers_et_accelerants(plan_g: Grille, liste_posees: list, liste_soin: list,
                                     cadre_z: Tuple[int, int, int, int], larg_g: int, haut_g: int,
                                     lim_cible_y: int, mode_liq: bool, pas_force: int = 0) -> list:
    if len(liste_posees) <= 25:
        return []
    ix_g, ix_d, iy_h, iy_b = _zone_interieure_tourelles(cadre_z, larg_g, haut_g, mode_liq)
    ens_ammo, ens_liq = _lignes_couloirs_internes(cadre_z, larg_g, haut_g, mode_liq, pas_force)
    ajouts_soin = []

    dispo_boucliers = [s for s in liste_soin if s.kind == "shield" or s.id == "force-projector"]
    if dispo_boucliers and larg_g > 20 and haut_g > 20:
        proto_sh = next(iter(dispo_boucliers))
        larg_s, haut_s, ray_s = proto_sh.largeur, proto_sh.hauteur, proto_sh.portee
        ens_prot = set()
        while len(ens_prot) < math.ceil(0.85 * len(liste_posees)) and len(liste_posees) > 25:
            opt_coord = None
            opt_val = 0.0
            for py in range(iy_h, iy_b - haut_s + 1):
                if any((py + dy) in ens_ammo or (py + dy) in ens_liq for dy in range(haut_s)):
                    continue
                if mode_liq and ens_liq and _couloir_proche(proto_sh, py, ens_liq) == -1:
                    continue
                for px in range(ix_g, ix_d - larg_s + 1, 2):
                    if any(plan_g.cellules[py + dy][px + dx] is not None and plan_g.cellules[py + dy][px + dx].type != "turret" for dy in range(haut_s) for dx in range(larg_s)):
                        continue
                    mil_x = px + larg_s / 2.0
                    mil_y = py + haut_s / 2.0
                    loc_cov = set()
                    for t_cur in liste_posees:
                        if math.hypot((t_cur.x + t_cur.largeur / 2.0) - mil_x, (t_cur.y + t_cur.hauteur / 2.0) - mil_y) <= ray_s:
                            loc_cov.add(id(t_cur))
                    val_loc = sum(100.0 / (t_cur.y + 5.0) for t_cur in liste_posees if id(t_cur) in (loc_cov - ens_prot))
                    if val_loc > opt_val:
                        opt_val = val_loc
                        opt_coord = (px, py)
            if opt_coord is None or opt_val <= 0:
                break
            cx, cy = opt_coord
            plan_g.liberer_zone(cx, cy, larg_s, haut_s, liste_posees)
            inst_sh = deepcopy(proto_sh)
            plan_g.placer(inst_sh, cx, cy)
            ajouts_soin.append(inst_sh)
            for t_cur in liste_posees:
                if math.hypot((t_cur.x + t_cur.largeur / 2.0) - (cx + larg_s / 2.0), (t_cur.y + t_cur.hauteur / 2.0) - (cy + haut_s / 2.0)) <= ray_s:
                    ens_prot.add(id(t_cur))

    dispo_od = sorted([s for s in liste_soin if s.kind == "overdrive" or "overdrive" in s.id], key=lambda s: -s.speed_boost)
    if dispo_od and larg_g > 14 and haut_g > 14 and len(liste_posees) > 25:
        proto_od = next(iter(dispo_od))
        larg_o, haut_o, ray_o = proto_od.largeur, proto_od.hauteur, proto_od.portee
        fact_mult = proto_od.speed_boost - 1.0
        ens_boost = set()
        while len(ens_boost) < math.ceil(0.80 * len(liste_posees)) and len(liste_posees) > 25:
            opt_coord = None
            opt_gain = 0.0
            opt_cov = set()
            for py in range(iy_h, iy_b - haut_o + 1):
                if any((py + dy) in ens_ammo or (py + dy) in ens_liq for dy in range(haut_o)):
                    continue
                touche_liq = (_couloir_proche(proto_od, py, ens_liq) != -1)
                for px in range(ix_g, ix_d - larg_o + 1, 2):
                    if any(plan_g.cellules[py + dy][px + dx] is not None and plan_g.cellules[py + dy][px + dx].type != "turret" for dy in range(haut_o) for dx in range(larg_o)):
                        continue
                    mil_x = px + larg_o / 2.0
                    mil_y = py + haut_o / 2.0
                    ecrasees = [t_cur for t_cur in liste_posees if not (t_cur.x + t_cur.largeur <= px or t_cur.x >= px + larg_o or t_cur.y + t_cur.hauteur <= py or t_cur.y >= py + haut_o)]
                    loc_cov = set()
                    for t_cur in liste_posees:
                        if t_cur not in ecrasees and math.hypot((t_cur.x + t_cur.largeur / 2.0) - mil_x, (t_cur.y + t_cur.hauteur / 2.0) - mil_y) <= ray_o:
                            loc_cov.add(id(t_cur))
                    gain_net = sum(t_cur.dps_reel * fact_mult for t_cur in liste_posees if id(t_cur) in (loc_cov - ens_boost) and peut_couvrir_cible(t_cur, t_cur.x, t_cur.y, lim_cible_y)) - sum(t_cur.dps_reel for t_cur in ecrasees)
                    if touche_liq:
                        gain_net += 35.0
                    if gain_net > opt_gain:
                        opt_gain = gain_net
                        opt_coord = (px, py)
                        opt_cov = loc_cov
            if opt_coord is None or opt_gain <= 50.0:
                break
            cx, cy = opt_coord
            plan_g.liberer_zone(cx, cy, larg_o, haut_o, liste_posees)
            inst_od = deepcopy(proto_od)
            plan_g.placer(inst_od, cx, cy)
            ajouts_soin.append(inst_od)
            ens_boost.update(opt_cov)
    return ajouts_soin


def phase3_optimisation_dps(plan_g: Grille, liste_t: list, liste_soin: list,
                            cadre_z: Tuple[int, int, int, int], larg_g: int,
                            haut_g: int, lim_cible_y: int, ens_cap: set,
                            ens_ammo: set, quota_aa: float = 0.15,
                            genome_ext: dict = None):
    mode_liq = "liquids" in ens_cap
    _, _, by_min, by_max = cadre_z
    paire_f = tuple(genome_ext["ammo_pair"]) if (genome_ext and genome_ext.get("ammo_pair")) else None
    pas_f = int(genome_ext.get("pas_travees", 0)) if genome_ext else 0

    duo_ammo, t_filtrees = selectionner_top_2_munitions(liste_t, ens_ammo, lim_cible_y, by_min + 1, by_max - 2, paire_f)
    ens_a_lignes, _ = _lignes_couloirs_internes(cadre_z, larg_g, haut_g, mode_liq, pas_f)
    lignes_a_tri = sorted(ens_a_lignes - {by_max - 1})

    if genome_ext and "gene_ammo" in genome_ext:
        g_map = {int(k): v for k, v in genome_ext["gene_ammo"].items()}
        g_tail = int(genome_ext.get("gene_taille", 0))
        essais_genes = [(g_map, g_tail)]
    else:
        essais_genes = [({}, 0), ({}, 1)]
        if len(duo_ammo) >= 2 and lignes_a_tri:
            am_p = next(iter(duo_ammo))
            am_s = next(islice(duo_ammo, 1, 2))
            essais_genes.append(({yc: (am_p if idx % 2 == 0 else am_s) for idx, yc in enumerate(lignes_a_tri)}, 0))
            essais_genes.append(({yc: (am_s if idx == len(lignes_a_tri) - 1 else am_p) for idx, yc in enumerate(lignes_a_tri)}, 1))

    meilleur_fit = -1e9
    meilleur_etat = None
    for map_a, mod_t in essais_genes:
        copie_plan = deepcopy(plan_g)
        posees_t = remplir_glouton_stratifie(copie_plan, t_filtrees, cadre_z, lim_cible_y, mode_liq, quota_aa, map_a, mod_t, pas_f)
        posees_s = _placer_boucliers_et_accelerants(copie_plan, posees_t, liste_soin, cadre_z, larg_g, haut_g, lim_cible_y, mode_liq, pas_f)
        somme_dps = sum(t_cur.dps_reel for t_cur in posees_t)
        aire_occ = sum(t_cur.taille() for t_cur in posees_t) + sum(s_cur.taille() for s_cur in posees_s)
        val_fit = somme_dps + aire_occ * 15.0
        if val_fit > meilleur_fit:
            meilleur_fit = val_fit
            meilleur_etat = (copie_plan, posees_t, somme_dps)

    plan_opt, t_retenues, dps_final = meilleur_etat
    plan_g.cellules = plan_opt.cellules
    return plan_g, t_retenues, t_filtrees, duo_ammo, dps_final

def _placer_tampons_crise(plan_g: Grille, liste_posees: list, cadre_z: Tuple[int, int, int, int],
                          ens_ammo: set, ens_liq: set, liste_log: list,
                          liste_liq: list, mode_liq: bool, duo_ammo: List[str]) -> Tuple[list, set]:
    nb_t = len(liste_posees)
    if nb_t < 25 or plan_g.largeur <= 16 or plan_g.hauteur <= 16:
        return [], set()
    bx_min, bx_max, by_min, by_max = cadre_z
    mil_x = (bx_min + bx_max) // 2
    ajouts_st = []
    yc_avec_st = set()

    pr_vault = next((b for b in liste_log if b.id == "vault"), None)
    pr_cont = next((b for b in liste_log if b.id == "container"), None)
    pr_unl = next((b for b in liste_log if b.id == "unloader"), None)
    pr_ov = next((b for b in liste_log if b.id == "overflow-gate"), None)
    pr_rt = next((b for b in liste_log if b.id == "router"), None)
    pr_conv = next((b for b in liste_log if b.kind == "conveyor"), None)
    pr_tank = next((b for b in liste_liq if b.id == "liquid-tank"), None)
    pr_lcont = next((b for b in liste_liq if b.id == "liquid-container"), pr_tank)
    pr_lrt = next((b for b in liste_liq if b.id == "liquid-router"), None)
    pr_cond = next((b for b in liste_liq if b.kind == "conduit"), None)

    bloc_it = pr_vault if (nb_t > 50 and pr_vault) else pr_cont
    bloc_lq = pr_tank if (nb_t > 50 and pr_tank) else pr_lcont
    if not bloc_it:
        return [], set()
    larg_i, haut_i = bloc_it.largeur, bloc_it.hauteur
    larg_l, haut_l = (bloc_lq.largeur, bloc_lq.hauteur) if bloc_lq else (larg_i, haut_i)
    lim_pont_d = (bx_max - 6) if mode_liq else (bx_max - 3)

    couples_al = []
    for ya_c in sorted(ens_ammo - {by_max - 1}):
        for yl_c in sorted(ens_liq):
            if 3 <= abs(yl_c - ya_c) <= 5:
                couples_al.append((ya_c, yl_c))

    if nb_t <= 70 or (bx_max - bx_min) < 26:
        if couples_al:
            ya_sel, yl_sel = next(islice(couples_al, len(couples_al) // 2, len(couples_al) // 2 + 1))
            pos_vy = (ya_sel + 1) if yl_sel > ya_sel else (ya_sel - haut_i)
        else:
            l_int = sorted(y for y in ens_ammo if by_min < y < by_max - 2) or sorted(ens_ammo)
            ya_sel = next(islice(l_int, len(l_int) // 2, len(l_int) // 2 + 1))
            yl_sel = -1
            pos_vy = ya_sel + 1 if (ya_sel + 1 + haut_i < by_max - 2) else ya_sel - haut_i
        pos_vx = mil_x - larg_i
        if (lim_pont_d - (pos_vx + 2) + 1) % 2 != 0:
            pos_vx -= 1
        emplacements = [(pos_vx, pos_vy, pos_vx + larg_i, ya_sel, yl_sel)]
    else:
        ya_h, yl_h = next(iter(couples_al), (by_min, -1))
        ya_b, yl_b = couples_al[-1] if len(couples_al) >= 2 else (max(y for y in ens_ammo if y < by_max - 1), -1)
        vy_h = (ya_h + 1) if (yl_h == -1 or yl_h > ya_h) else (ya_h - haut_i)
        vy_b = (ya_b + 1) if (yl_b == -1 or yl_b > ya_b) else (ya_b - haut_i)
        vx_g = bx_min + 6
        if ((vx_g - 3) - (bx_min + 4) + 1) % 2 != 0:
            vx_g += 1
        vx_d = bx_max - 4 - 2 * larg_i
        if (lim_pont_d - (vx_d + 2) + 1) % 2 != 0:
            vx_d -= 1
        emplacements = [
            (vx_g, vy_h, vx_g + larg_i, ya_h, yl_h),
            (vx_d, vy_h, vx_d + larg_i, ya_h, yl_h),
            (vx_g, vy_b, vx_g + larg_i, ya_b, yl_b),
            (vx_d, vy_b, vx_d + larg_i, ya_b, yl_b),
        ]

    for vx, vy, tx, yc_ref, yl_ref in emplacements:
        yc_avec_st.add(yc_ref)
        col_u = vx - 1
        col_r = vx - 2
        if yl_ref != -1:
            ty = (yl_ref - haut_l) if yl_ref > yc_ref else (yl_ref + 1)
        else:
            ty = vy

        y_haut_lib = min(vy, ty)
        y_bas_lib = max(vy + haut_i, ty + haut_l)
        x_droite_lib = (tx + larg_l) if (mode_liq and bloc_lq) else (vx + larg_i)
        plan_g.liberer_zone(col_r, y_haut_lib, x_droite_lib - col_r, y_bas_lib - y_haut_lib, liste_posees)

        inst_it = deepcopy(bloc_it)
        inst_it.kind = "storage"
        plan_g.placer(inst_it, vx, vy)
        ajouts_st.append(inst_it)

        if mode_liq and bloc_lq:
            inst_lq = deepcopy(bloc_lq)
            inst_lq.kind = "storage"
            plan_g.placer(inst_lq, tx, ty)
            ajouts_st.append(inst_lq)
            if yl_ref != -1 and pr_lrt and pr_cond:
                tx_io = tx if (lim_pont_d - (tx + 1) + 1) % 2 == 0 else tx + 1
                if plan_g.cellules[yl_ref][tx_io] is None and plan_g.cellules[yl_ref][tx_io - 1] is None:
                    sens_lq = 0 if yl_ref == max(ens_liq) else 2
                    b_lrt = deepcopy(pr_lrt)
                    b_lrt.kind = "storage_io"
                    b_lrt.rotation = sens_lq
                    plan_g.placer(b_lrt, tx_io, yl_ref)
                    ajouts_st.append(b_lrt)
                    b_lcd = deepcopy(pr_cond)
                    b_lcd.kind = "storage_io"
                    b_lcd.rotation = sens_lq
                    plan_g.placer(b_lcd, tx_io - 1, yl_ref)
                    ajouts_st.append(b_lcd)

        if pr_ov and pr_conv and plan_g.cellules[yc_ref][vx + 1] is None and plan_g.cellules[yc_ref][vx] is None:
            b_ov = deepcopy(pr_ov)
            b_ov.kind = "storage_io"
            b_ov.rotation = 2
            plan_g.placer(b_ov, vx + 1, yc_ref)
            ajouts_st.append(b_ov)
            b_cin = deepcopy(pr_conv)
            b_cin.kind = "storage_io"
            b_cin.rotation = 2
            plan_g.placer(b_cin, vx, yc_ref)
            ajouts_st.append(b_cin)

        if pr_unl and pr_conv and duo_ammo:
            pr_jonc = pr_rt if pr_rt else pr_conv
            for cx_io in (col_u, col_r):
                if plan_g.cellules[yc_ref][cx_io] is None:
                    b_ct = deepcopy(pr_jonc if cx_io == col_u else pr_conv)
                    b_ct.kind = "storage_io"
                    b_ct.rotation = 2
                    plan_g.placer(b_ct, cx_io, yc_ref)
                    ajouts_st.append(b_ct)
            for idx_a, nom_cfg in enumerate(islice(duo_ammo, 0, min(2, haut_i))):
                b_un = deepcopy(pr_unl)
                b_un.kind = "storage_io"
                b_un.rotation = 1
                b_un.best_ammo = nom_cfg
                plan_g.placer(b_un, col_u, vy + idx_a)
                ajouts_st.append(b_un)
                if idx_a == 1:
                    for ry_c in (vy + 1, vy):
                        b_cv = deepcopy(pr_conv)
                        b_cv.kind = "storage_io"
                        b_cv.rotation = 1
                        plan_g.placer(b_cv, col_r, ry_c)
                        ajouts_st.append(b_cv)
    return ajouts_st, yc_avec_st


def _couloir_a_besoin_ammo(plan_g: Grille, lig_y: int, bx_min: int, bx_max: int,
                           duo_ammo: List[str] = None) -> str:
    touche_st = False
    for px in range(bx_min + 1, bx_max - 1):
        for adj_y in (lig_y - 1, lig_y + 1):
            if 0 <= adj_y < plan_g.hauteur:
                occ = plan_g.cellules[adj_y][px]
                if occ is not None:
                    if occ.type == "turret" and occ.best_ammo and occ.best_ammo != "power":
                        return occ.best_ammo
                    if occ.kind in ("storage", "storage_io"):
                        touche_st = True
    if touche_st and duo_ammo:
        return next(iter(duo_ammo), "")
    return ""


def _choisir_distributeurs(ens_blocs: list, role_base: str):
    voies = [b for b in ens_blocs if b.kind == role_base]
    b_princ = next(iter(voies), next(iter(ens_blocs), None))
    b_tri = next((b for b in ens_blocs if b.id == "sorter"), b_princ)
    b_rep = (
        next((b for b in ens_blocs if b.id == "underflow-gate"), None)
        or next((b for b in ens_blocs if b.id == "liquid-router"), None)
        or next((b for b in ens_blocs if b.kind in ("gate", "router")), b_princ)
    )
    b_rout = (
        next((b for b in ens_blocs if b.id in ("router", "liquid-router")), None)
        or next((b for b in ens_blocs if b.kind == "router"), b_princ)
    )
    l_ponts = [b for b in ens_blocs if b.kind == "bridge" or "bridge" in b.id.lower()]
    l_ponts.sort(key=lambda b: -b.vitesse_transport)
    b_pont = next(iter(l_ponts), None)
    return b_princ, b_tri, b_rep, b_rout, b_pont

def _densifier_par_ponts(plan_g: Grille, ens_lignes: set, x_start: int, x_end: int,
                         pr_pont: Bloc, registre: list):
    if pr_pont is None or x_start >= x_end:
        return
    for lig_y in sorted(ens_lignes):
        dir_l = 2
        for xs in range(x_start, x_end + 1):
            occ = plan_g.cellules[lig_y][xs]
            if occ is not None and occ.kind in ("conveyor", "conduit") and occ.rotation in (0, 2):
                dir_l = occ.rotation
                break
        if dir_l == 2:
            cur_x = x_end
            while cur_x - 1 >= x_start:
                b1, b2 = plan_g.cellules[lig_y][cur_x], plan_g.cellules[lig_y][cur_x - 1]
                if (b1 and b2 and b1.kind in ("conveyor", "conduit") and b2.kind == b1.kind and
                        b1.rotation == 2 and b2.rotation == 2):
                    plan_g.retirer(b1)
                    plan_g.retirer(b2)
                    if b1 in registre:
                        registre.remove(b1)
                    if b2 in registre:
                        registre.remove(b2)
                    pa, pb = deepcopy(pr_pont), deepcopy(pr_pont)
                    pa.rotation = 2
                    pb.rotation = 2
                    plan_g.placer(pa, cur_x, lig_y)
                    plan_g.placer(pb, cur_x - 1, lig_y)
                    registre.extend([pa, pb])
                    cur_x -= 2
                else:
                    cur_x -= 1
        else:
            cur_x = x_start
            while cur_x + 1 <= x_end:
                b1, b2 = plan_g.cellules[lig_y][cur_x], plan_g.cellules[lig_y][cur_x + 1]
                if (b1 and b2 and b1.kind in ("conveyor", "conduit") and b2.kind == b1.kind and
                        b1.rotation == 0 and b2.rotation == 0):
                    plan_g.retirer(b1)
                    plan_g.retirer(b2)
                    if b1 in registre:
                        registre.remove(b1)
                    if b2 in registre:
                        registre.remove(b2)
                    pa, pb = deepcopy(pr_pont), deepcopy(pr_pont)
                    pa.rotation = 0
                    pb.rotation = 0
                    plan_g.placer(pa, cur_x, lig_y)
                    plan_g.placer(pb, cur_x + 1, lig_y)
                    registre.extend([pa, pb])
                    cur_x += 2
                else:
                    cur_x += 1


def _densifier_colonnes_par_ponts(plan_g: Grille, liste_cols: list, y_start: int, y_end: int,
                                  pr_pont: Bloc, registre: list):
    if pr_pont is None or y_start >= y_end:
        return
    for col_x in liste_cols:
        cur_y = y_start
        while cur_y + 1 <= y_end:
            b1, b2 = plan_g.cellules[cur_y][col_x], plan_g.cellules[cur_y + 1][col_x]
            if (b1 and b2 and b1.kind in ("conveyor", "conduit") and b2.kind == b1.kind and
                    b1.rotation == 3 and b2.rotation == 3):
                plan_g.retirer(b1)
                plan_g.retirer(b2)
                if b1 in registre:
                    registre.remove(b1)
                if b2 in registre:
                    registre.remove(b2)
                pa, pb = deepcopy(pr_pont), deepcopy(pr_pont)
                pa.rotation = 3
                pb.rotation = 3
                plan_g.placer(pa, col_x, cur_y)
                plan_g.placer(pb, col_x, cur_y + 1)
                registre.extend([pa, pb])
                cur_y += 2
            else:
                cur_y += 1


def _placer_batteries_4s(plan_g: Grille, liste_en: list, cadre_z: Tuple[int, int, int, int],
                         liste_posees: list, lig_exclues: set) -> list:
    dispo_bats = sorted([e for e in liste_en if e.kind == "battery"], key=lambda b: (-b.taille(), -b.energy_stored))
    if not dispo_bats:
        return []
    bx_min, bx_max, by_min, by_max = cadre_z
    lim_arr_y = max(by_min + 1, by_min + int((by_max - by_min) * 0.65))
    cols_excl = {bx_min, bx_min + 2, bx_max - 4, bx_max - 1}

    vus_id = set()
    conso_glob = 0.0
    reserve_act = 0.0
    for py in range(plan_g.hauteur):
        for px in range(plan_g.largeur):
            occ = plan_g.cellules[py][px]
            if occ is not None and id(occ) not in vus_id:
                vus_id.add(id(occ))
                conso_glob += occ.energy_consume_rate
                reserve_act += occ.energy_stored

    obj_4s = conso_glob * 4.0
    ajouts_b = []
    for mode_ecrase in (False, True):
        for pr_bat in dispo_bats:
            if pr_bat.taille() == 1 and any(b.taille() >= 9 for b in dispo_bats):
                continue
            larg_b, haut_b = pr_bat.largeur, pr_bat.hauteur
            for py in range(by_max - 1 - haut_b, lim_arr_y - 1, -1):
                if reserve_act >= obj_4s:
                    break
                if any((py + dy) in lig_exclues for dy in range(haut_b)):
                    continue
                for px in range(bx_max - 1 - larg_b, bx_min, -1):
                    if reserve_act >= obj_4s:
                        break
                    if any((px + dx) in cols_excl for dx in range(larg_b)):
                        continue
                    if not plan_g.peut_placer(pr_bat, px, py):
                        if not mode_ecrase or any(plan_g.cellules[py + dy][px + dx] is not None and (plan_g.cellules[py + dy][px + dx].type != "turret" or plan_g.cellules[py + dy][px + dx].targets_air) for dy in range(haut_b) for dx in range(larg_b)):
                            continue
                        plan_g.liberer_zone(px, py, larg_b, haut_b, liste_posees)
                    inst_b = deepcopy(pr_bat)
                    inst_b.kind = "battery"
                    plan_g.placer(inst_b, px, py)
                    ajouts_b.append(inst_b)
                    reserve_act += inst_b.energy_stored
    return ajouts_b

def _placer_energie_connectee(plan_g: Grille, liste_en: list,
                              cadre_z: Tuple[int, int, int, int], liste_posees: list,
                              dispo_t: list, lig_exclues: set,
                              lim_cible_y: int = -8) -> list:
    dispo_nodes = [e for e in liste_en if e.kind == "node"]
    if not dispo_nodes:
        return []
    pr_petit = next((e for e in dispo_nodes if e.id == "power-node"), next(iter(dispo_nodes)))
    pr_grand = next((e for e in dispo_nodes if e.id == "power-node-large"), pr_petit)
    pr_tour = next((e for e in dispo_nodes if e.id == "surge-tower"), pr_grand)
    pr_bat1 = next((e for e in liste_en if e.id == "battery"), None)
    dispo_t1 = [t for t in dispo_t if t.taille() == 1]
    bx_min, bx_max, by_min, by_max = cadre_z
    cols_excl = {bx_min, bx_min + 2, bx_max - 4, bx_max - 1}
    ajouts_n = []

    def combler_trou_1x1(x_z: int, y_z: int, w_z: int, h_z: int):
        for ry in range(y_z, y_z + h_z):
            for rx in range(x_z, x_z + w_z):
                if plan_g.cellules[ry][rx] is not None:
                    continue
                for pr_t1 in dispo_t1:
                    if pr_t1.best_ammo == "power" and peut_couvrir_cible(pr_t1, rx, ry, lim_cible_y) and plan_g.peut_placer(pr_t1, rx, ry):
                        inst_t1 = deepcopy(pr_t1)
                        plan_g.placer(inst_t1, rx, ry)
                        liste_posees.append(inst_t1)
                        break
                if plan_g.cellules[ry][rx] is None and pr_bat1 and plan_g.peut_placer(pr_bat1, rx, ry):
                    inst_b1 = deepcopy(pr_bat1)
                    inst_b1.kind = "battery"
                    plan_g.placer(inst_b1, rx, ry)
                    ajouts_n.append(inst_b1)

    def tenter_pose_node(pr_n: Bloc, px: int, py: int, niv_ecrase: int = 0):
        larg_n, haut_n = pr_n.largeur, pr_n.hauteur
        if px < bx_min + 1 or px + larg_n > bx_max - 1 or py <= by_min or py + haut_n >= by_max - 1:
            return None
        if any((py + dy) in lig_exclues for dy in range(haut_n)) or any((px + dx) in cols_excl for dx in range(larg_n)):
            return None
        if plan_g.peut_placer(pr_n, px, py):
            inst_n = deepcopy(pr_n)
            inst_n.kind = "node"
            plan_g.placer(inst_n, px, py)
            return inst_n
        if niv_ecrase >= 1:
            cibles_ecr = []
            vus_ecr = set()
            for dy in range(haut_n):
                for dx in range(larg_n):
                    occ = plan_g.cellules[py + dy][px + dx]
                    if occ is not None:
                        if occ.type != "turret" or occ.targets_air or (niv_ecrase == 1 and occ.taille() > 1):
                            return None
                        if id(occ) not in vus_ecr:
                            vus_ecr.add(id(occ))
                            cibles_ecr.append(occ)
            zones_lib = [(v.x, v.y, v.largeur, v.hauteur) for v in cibles_ecr]
            for v in cibles_ecr:
                plan_g.retirer(v)
                if v in liste_posees:
                    liste_posees.remove(v)
            inst_n = deepcopy(pr_n)
            inst_n.kind = "node"
            plan_g.placer(inst_n, px, py)
            for zx, zy, zw, zh in zones_lib:
                combler_trou_1x1(zx, zy, zw, zh)
            return inst_n
        return None

    clients_elec = []
    liste_bats = []
    vus_id = set()
    for py in range(plan_g.hauteur):
        for px in range(plan_g.largeur):
            occ = plan_g.cellules[py][px]
            if occ is not None and id(occ) not in vus_id:
                vus_id.add(id(occ))
                if occ.consomme_energie or occ.type == "soin":
                    clients_elec.append(occ)
                elif occ.kind == "battery":
                    liste_bats.append(occ)

    bats_vues = set()
    for idx_i, b_a in enumerate(liste_bats):
        if idx_i not in bats_vues:
            clients_elec.append(b_a)
            file_q = [idx_i]
            bats_vues.add(idx_i)
            while file_q:
                id_cur = file_q.pop(0)
                b_cur = next(islice(liste_bats, id_cur, id_cur + 1))
                for idx_j, b_b in enumerate(liste_bats):
                    if idx_j not in bats_vues and (abs(b_cur.x - b_b.x) + abs(b_cur.y - b_b.y) <= max(b_cur.largeur, b_b.largeur)):
                        bats_vues.add(idx_j)
                        file_q.append(idx_j)

    sources_n = []
    cpt_liens = defaultdict(int)
    for cl in clients_elec:
        mil_x = cl.x + cl.largeur / 2.0
        mil_y = cl.y + cl.hauteur / 2.0
        n_dispo = next((nd for nd in sources_n if cpt_liens[id(nd)] < nd.max_links - 2 and math.hypot((nd.x + nd.largeur / 2.0) - mil_x, (nd.y + nd.hauteur / 2.0) - mil_y) <= nd.laser_range), None)
        if n_dispo:
            cpt_liens[id(n_dispo)] += 1
            continue
        est_pose = False
        for niv in (0, 1, 2):
            for pr_n in (pr_petit, pr_grand):
                ray_n = pr_n.laser_range
                for py in range(max(by_min + 1, int(mil_y - ray_n)), min(by_max - 1, int(mil_y + ray_n) + 1)):
                    for px in range(max(bx_min + 1, int(mil_x - ray_n)), min(bx_max - 1, int(mil_x + ray_n) + 1)):
                        if math.hypot((px + pr_n.largeur / 2.0) - mil_x, (py + pr_n.hauteur / 2.0) - mil_y) <= ray_n:
                            nouv_n = tenter_pose_node(pr_n, px, py, niv)
                            if nouv_n:
                                sources_n.append(nouv_n)
                                ajouts_n.append(nouv_n)
                                cpt_liens[id(nouv_n)] += 1
                                est_pose = True
                                break
                    if est_pose:
                        break
                if est_pose:
                    break
            if est_pose:
                break

    for _ in range(30):
        if len(sources_n) <= 1:
            break
        graphe_n = {idx: [] for idx in range(len(sources_n))}
        for i_a, na in enumerate(sources_n):
            for i_b, nb in enumerate(sources_n):
                if i_a < i_b and math.hypot((na.x + na.largeur / 2.0) - (nb.x + nb.largeur / 2.0), (na.y + na.hauteur / 2.0) - (nb.y + nb.hauteur / 2.0)) <= max(na.laser_range, nb.laser_range):
                    graphe_n[i_a].append(i_b)
                    graphe_n[i_b].append(i_a)
        visites = set()
        groupes = []
        for idx in range(len(sources_n)):
            if idx not in visites:
                grp = []
                file_q = [idx]
                visites.add(idx)
                while file_q:
                    sommet = file_q.pop(0)
                    grp.append(sommet)
                    for vois in graphe_n[sommet]:
                        if vois not in visites:
                            visites.add(vois)
                            file_q.append(vois)
                groupes.append(grp)
        if len(groupes) <= 1:
            break
        dist_min = 999999.0
        duo_opt = None
        grp_init = next(iter(groupes))
        for i_a in grp_init:
            for grp_autre in islice(groupes, 1, None):
                for i_b in grp_autre:
                    na = next(islice(sources_n, i_a, i_a + 1))
                    nb = next(islice(sources_n, i_b, i_b + 1))
                    ecart = math.hypot(na.x - nb.x, na.y - nb.y)
                    if ecart < dist_min:
                        dist_min = ecart
                        duo_opt = (na, nb)
        if not duo_opt:
            break
        na, nb = duo_opt
        pont_relais = None
        for niv in (0, 1, 2):
            for pr_n in (pr_grand, pr_tour, pr_petit):
                frac = min(pr_n.laser_range - 0.5, dist_min * 0.5) / max(dist_min, 1.0)
                cible_x = int(round(na.x + (nb.x - na.x) * frac))
                cible_y = int(round(na.y + (nb.y - na.y) * frac))
                for dy in (0, -1, 1, -2, 2, -3, 3):
                    for dx in (0, -1, 1, -2, 2, -3, 3):
                        rx = cible_x + dx
                        ry = cible_y + dy
                        if math.hypot((rx + pr_n.largeur / 2.0) - (na.x + na.largeur / 2.0), (ry + pr_n.hauteur / 2.0) - (na.y + na.hauteur / 2.0)) <= max(pr_n.laser_range, na.laser_range):
                            pont_relais = tenter_pose_node(pr_n, rx, ry, niv)
                            if pont_relais:
                                break
                    if pont_relais:
                        break
                if pont_relais:
                    break
            if pont_relais:
                break
        if pont_relais:
            sources_n.append(pont_relais)
            ajouts_n.append(pont_relais)
        else:
            break
    return ajouts_n

def _tracer_peignes_logistiques(plan_g: Grille, cadre_z: Tuple[int, int, int, int], mode_liq: bool,
                                ens_liq: set, yc_actifs: set, yc_stock: set,
                                map_ammo_yc: dict, duo_ammo: List[str], pr_conv: Bloc,
                                pr_tri: Bloc, pr_rout: Bloc, pr_pont: Bloc,
                                pr_cond: Bloc, pr_lrt: Bloc, pr_lpont: Bloc,
                                fn_pose, registre_infra: list):
    bx_min, bx_max, by_min, by_max = cadre_z
    if mode_liq and ens_liq:
        yl_bas = max(ens_liq)
        yl_haut = min(ens_liq)
        col_lq_g = bx_min + 2
        col_lq_d = bx_max - 4
        for py in range(yl_bas, yl_haut - 1, -1):
            besoin_r = (py in (ens_liq - {yl_bas}) or plan_g.cellules[py][col_lq_d + 1] is not None)
            fn_pose(col_lq_d, py, pr_lrt if besoin_r else pr_cond, 1)
            fn_pose(col_lq_g, py, pr_lrt if py in ens_liq else pr_cond, 3)
        for lig_l in sorted(ens_liq):
            dir_l = 0 if (lig_l == yl_bas and len(ens_liq) > 1) else 2
            for px in range(col_lq_d - 1, col_lq_g, -1):
                fn_pose(px, lig_l, pr_cond, dir_l)
        fn_pose(col_lq_g, yl_bas, pr_lrt, 0)
        _densifier_par_ponts(plan_g, ens_liq - {yl_bas}, col_lq_g + 1, col_lq_d - 1, pr_lpont, registre_infra)
        _densifier_par_ponts(plan_g, {yl_bas}, col_lq_g + 1, max(col_lq_g + 1, col_lq_d - 5), pr_lpont, registre_infra)

    if pr_conv:
        plusieurs_a = len(set(map_ammo_yc.values())) > 1 or len(duo_ammo) > 1
        for py in range(by_max - 1, by_min, -1):
            fn_pose(bx_max - 1, py, pr_rout if (py in yc_actifs and py != by_max - 1) else pr_conv, 1)
        fn_pose(bx_max - 1, by_min, pr_conv, 2)
        for py in range(by_min, by_max - 1):
            role_f = "storage_io" if (py in yc_actifs or (py - 1) in yc_actifs) else ""
            fn_pose(bx_min, py, pr_conv, 3, "", role_f)
        for px in range(bx_min, bx_max - 1):
            fn_pose(px, by_max - 1, pr_conv, 0)

        for lig_a in sorted(yc_actifs - {by_max - 1}):
            doit_filtrer = (lig_a != by_min and lig_a not in yc_stock and plusieurs_a and lig_a in map_ammo_yc)
            if mode_liq and ens_liq and pr_pont and lig_a >= min(ens_liq):
                cfg_tri = map_ammo_yc.get(lig_a, "") if doit_filtrer else ""
                fn_pose(bx_max - 2, lig_a, pr_tri if doit_filtrer else pr_conv, 2, cfg_tri, "storage_io")
                fn_pose(bx_max - 3, lig_a, pr_pont, 2, "", "bridge_io")
                fn_pose(bx_max - 5, lig_a, pr_pont, 2, "", "bridge_io")
                for px in range(bx_max - 6, bx_min + 3, -1):
                    fn_pose(px, lig_a, pr_conv, 2)
                fn_pose(bx_min + 3, lig_a, pr_pont, 2, "", "bridge_io")
                fn_pose(bx_min + 1, lig_a, pr_pont, 2, "", "bridge_io")
                _densifier_par_ponts(plan_g, {lig_a}, bx_min + 4, bx_max - 6, pr_pont, registre_infra)
            else:
                for px in range(bx_max - 2, bx_min, -1):
                    fn_pose(px, lig_a, pr_conv, 2)
                if doit_filtrer:
                    fn_pose(bx_max - 2, lig_a, pr_tri, 2, map_ammo_yc[lig_a], "storage_io")
                _densifier_par_ponts(plan_g, {lig_a}, bx_min + 1, bx_max - 1 if lig_a == by_min else bx_max - 3, pr_pont, registre_infra)

        _densifier_par_ponts(plan_g, {by_max - 1}, bx_min + 1, bx_max - 2, pr_pont, registre_infra)
        _densifier_colonnes_par_ponts(plan_g, [bx_min], by_min + 1, by_max - 2, pr_pont, registre_infra)

def phase4_infrastructure(plan_g: Grille, liste_posees: list, dispo_t: list,
                          liste_soin: list, liste_log: list, liste_liq: list,
                          liste_en: list, cadre_z: Tuple[int, int, int, int],
                          larg_g: int, haut_g: int, lim_cible_y: int,
                          sans_mur: bool, ens_cap: set, duo_ammo: List[str],
                          quota_aa: float = 0.15, pas_force: int = 0):
    bx_min, bx_max, by_min, by_max = cadre_z
    mode_liq = "liquids" in ens_cap and bool(liste_liq)
    ens_ammo, ens_liq = _lignes_couloirs_internes(cadre_z, larg_g, haut_g, mode_liq, pas_force)
    registre_infra = []

    pr_conv, pr_tri, pr_rep, pr_rout, pr_pont = _choisir_distributeurs(liste_log, "conveyor")
    pr_ov = next((b for b in liste_log if b.id == "overflow-gate"), pr_rep)
    if mode_liq:
        pr_cond, _, pr_lrt, _, pr_lpont = _choisir_distributeurs(liste_liq, "conduit")
    else:
        pr_cond, pr_lrt, pr_lpont = None, None, None
    pont_l_eff = pr_lpont if pr_lpont else pr_pont

    def poser_elem(px: int, py: int, pr_b: Bloc, dir_r: int, val_cfg: str = "", role_f: str = ""):
        if pr_b is None or not (0 <= px < larg_g and 0 <= py < haut_g):
            return
        occ = plan_g.cellules[py][px]
        if occ is not None:
            if occ.type in ("turret", "soin", "energie") or occ.kind in ("storage", "storage_io", "bridge_io"):
                return
            if occ in registre_infra:
                registre_infra.remove(occ)
            plan_g.retirer(occ)
        inst_b = deepcopy(pr_b)
        inst_b.rotation = dir_r
        inst_b.best_ammo = val_cfg
        if role_f:
            inst_b.kind = role_f
        plan_g.placer(inst_b, px, py)
        registre_infra.append(inst_b)

    blocs_st, yc_stock = _placer_tampons_crise(
        plan_g, liste_posees, cadre_z, ens_ammo, ens_liq,
        liste_log, liste_liq, mode_liq, duo_ammo
    )
    registre_infra += blocs_st
    placer_soin_minimal_avant(plan_g, liste_soin, cadre_z, larg_g, haut_g, sans_mur, mode_liq)

    if haut_g > by_max and pr_pont and pr_conv:
        poser_elem(bx_max - 2, haut_g - 1, pr_pont, 1, "", "bridge_io")
        poser_elem(bx_max - 2, by_max - 2, pr_pont, 1, "", "bridge_io")
        if by_max - 3 > by_min:
            poser_elem(bx_max - 2, by_max - 3, pr_conv, 0, "", "bridge_io")
            poser_elem(bx_max - 1, by_max - 1, pr_conv, 1, "", "bridge_io")
            poser_elem(bx_max - 1, by_max - 2, pr_conv, 1, "", "bridge_io")
            poser_elem(bx_max - 1, by_max - 3, pr_rout if pr_rout else pr_conv, 1, "", "bridge_io")

        col_echap = bx_max - 5
        if ((col_echap - 2) - (bx_min + 1) + 1) % 2 != 0:
            col_echap -= 1
        if col_echap > bx_min + 3 and pr_ov:
            poser_elem(col_echap - 1, by_max - 1, pr_conv, 0, "", "bridge_io")
            poser_elem(col_echap, by_max - 1, pr_ov, 0, "", "bridge_io")
            if haut_g - 1 > by_max:
                poser_elem(col_echap, by_max, pr_pont, 3, "", "bridge_io")
                poser_elem(col_echap, haut_g - 1, pr_pont, 3, "", "bridge_io")
            else:
                poser_elem(col_echap, by_max, pr_conv, 3, "", "bridge_io")

    if haut_g > by_max and mode_liq and ens_liq and pont_l_eff:
        yl_bas = max(ens_liq)
        poser_elem(bx_max - 4, haut_g - 1, pont_l_eff, 1, "", "bridge_io")
        poser_elem(bx_max - 4, yl_bas - 1, pont_l_eff, 1, "", "bridge_io")
        poser_elem(bx_max - 4, yl_bas, pr_cond, 1, "", "bridge_io")
        if yl_bas - 2 >= min(ens_liq):
            poser_elem(bx_max - 4, yl_bas - 2, pr_lrt, 1, "", "bridge_io")

    yc_actifs = {by_min, by_max - 1} | set(yc_stock)
    map_ammo_yc = {}
    for lig_a in sorted(ens_ammo - {by_max - 1}):
        nom_a = _couloir_a_besoin_ammo(plan_g, lig_a, bx_min, bx_max, duo_ammo)
        if nom_a:
            yc_actifs.add(lig_a)
            map_ammo_yc[lig_a] = nom_a
    lig_exclues = yc_actifs | ens_liq

    ix_g, ix_d, iy_h, iy_b = _zone_interieure_tourelles(cadre_z, larg_g, haut_g, mode_liq)
    tri_aa = sorted([t for t in dispo_t if t.targets_air], key=lambda t: (-t.dps_par_surface, -t.portee))
    tri_sol = sorted([t for t in dispo_t if t.targets_ground], key=lambda t: (-t.dps_par_surface, -t.portee))
    tri_pwr = sorted([t for t in dispo_t if t.best_ammo == "power"], key=lambda t: (-t.dps_par_surface, -t.portee))

    for py in range(iy_h, iy_b):
        if py in lig_exclues:
            continue
        for px in range(bx_min + 1, bx_max - 1):
            if px in (bx_min, bx_min + 2, bx_max - 4, bx_max - 1) or plan_g.cellules[py][px] is not None:
                continue
            zone_lat_elec = (px < ix_g or px >= ix_d)
            tot_t = max(1, len(liste_posees) + 1)
            nb_aa = sum(1 for t in liste_posees if t.targets_air)
            nb_par = sum(1 for t in liste_posees if t.id == "parallax")
            nb_pre = sum(1 for t in liste_posees if t.id == "foreshadow")
            manque_aa = bool(tri_aa) and ((nb_aa / tot_t) < max(0.15, quota_aa))
            seq_t = tri_pwr if zone_lat_elec else ((tri_aa + tri_sol) if manque_aa else (tri_sol + tri_aa))
            for pr_t in seq_t:
                if pr_t.id == "parallax" and nb_par >= max(1, int(0.10 * tot_t)):
                    continue
                if pr_t.id == "foreshadow" and nb_pre >= max(1, int(0.05 * tot_t)):
                    continue
                if not pr_t.targets_ground and pr_t.id != "parallax" and (nb_aa / tot_t) >= 0.20:
                    continue
                if zone_lat_elec and (px + pr_t.largeur > bx_max - 1 or any((px + dx) in (bx_min, bx_min + 2, bx_max - 4, bx_max - 1) for dx in range(pr_t.largeur))):
                    continue
                if not zone_lat_elec and px + pr_t.largeur > ix_d:
                    continue
                if py + pr_t.hauteur > iy_b or any((py + dy) in lig_exclues for dy in range(pr_t.hauteur)):
                    continue
                if not peut_couvrir_cible(pr_t, px, py, lim_cible_y):
                    continue
                if pr_t.best_ammo and pr_t.best_ammo != "power":
                    yc_adj = _couloir_proche(pr_t, py, yc_actifs)
                    if yc_adj == -1 or (yc_adj not in yc_stock and yc_adj in map_ammo_yc and map_ammo_yc[yc_adj] != pr_t.best_ammo):
                        continue
                if plan_g.peut_placer(pr_t, px, py):
                    inst_t = deepcopy(pr_t)
                    plan_g.placer(inst_t, px, py)
                    liste_posees.append(inst_t)
                    break

    if "energy" in ens_cap and liste_en:
        registre_infra += _placer_batteries_4s(plan_g, liste_en, cadre_z, liste_posees, lig_exclues)
        registre_infra += _placer_energie_connectee(plan_g, liste_en, cadre_z, liste_posees, dispo_t, lig_exclues, lim_cible_y)

    _tracer_peignes_logistiques(
        plan_g, cadre_z, mode_liq, ens_liq, yc_actifs, yc_stock,
        map_ammo_yc, duo_ammo, pr_conv, pr_tri, pr_rout, pr_pont,
        pr_cond, pr_lrt, pr_lpont, poser_elem, registre_infra
    )
    return registre_infra, pr_conv

def _resoudre_nom_item_msch(cfg_brut: str) -> str:
    if not cfg_brut:
        return ""
    table_alias = {
        "surge-alloy": ("surge_alloy", "surge", "surge-alloy", "surgealloy", "SurgeAlloy"),
        "phase-fabric": ("phase_fabric", "phase", "phase-fabric", "phasefabric", "PhaseFabric"),
        "blast-compound": ("blast_compound", "blast", "blast-compound", "blastcompound"),
        "spore-pod": ("spore_pod", "spore", "spore-pod", "sporepod"),
    }
    if cfg_brut not in table_alias:
        return cfg_brut

    variantes = table_alias.get(cfg_brut)
    rep_app = os.environ.get("APPDATA", "")
    rep_build = os.path.join(rep_app, "npm", "node_modules", "msch-generate", "build")
    if os.path.isdir(rep_build):
        code_js = ""
        for nom_f in os.listdir(rep_build):
            if nom_f.endswith(".js"):
                try:
                    with open(os.path.join(rep_build, nom_f), "r", encoding="utf-8", errors="ignore") as flux_j:
                        code_js += flux_j.read() + "\n"
                except OSError:
                    pass
        for var_c in variantes:
            if f'"{var_c}"' in code_js or f"'{var_c}'" in code_js or f"{var_c}:" in code_js:
                return var_c
        for repli in ("thorium", "plastanium", "titanium", "silicon", "graphite", "copper"):
            if f'"{repli}"' in code_js or f"'{repli}'" in code_js or f"{repli}:" in code_js:
                return repli
    return next(iter(variantes))


def calculer_besoin_munitions(liste_posees: list) -> float:
    return sum(max(0.2, min(t.rate, 3.0) * 0.4) for t in liste_posees if t.best_ammo != "power")


def evaluer_viabilite_approvisionnement(liste_posees: list, pr_log: Bloc,
                                        larg_g: int, haut_g: int) -> float:
    if not pr_log or not liste_posees:
        return 1.0
    debit_v = pr_log.vitesse_transport or 4.2
    cap_res = debit_v * ((larg_g + haut_g) * 1.5)
    demande = calculer_besoin_munitions(liste_posees)
    return min(cap_res / max(demande, 0.1), 1.0)


def phase6_logistique_finale(plan_g: Grille, liste_posees: list, registre_infra: list,
                             pr_conv: Bloc, larg_g: int, haut_g: int):
    vus_id = set()
    t_effectives = []
    for py in range(plan_g.hauteur):
        for px in range(plan_g.largeur):
            occ = plan_g.cellules[py][px]
            if occ is not None and occ.type == "turret" and id(occ) not in vus_id:
                vus_id.add(id(occ))
                t_effectives.append(occ)
    liste_posees[:] = t_effectives
    ratio_flux = evaluer_viabilite_approvisionnement(liste_posees, pr_conv, larg_g, haut_g)
    dps_cumul = sum(t.dps_reel for t in liste_posees)
    return dps_cumul, ratio_flux, registre_infra


def phase7_protection_compaction(plan_g: Grille, liste_murs: list,
                                 cadre_z: Tuple[int, int, int, int], larg_g: int,
                                 haut_g: int, sans_mur: bool, ens_mat: set, ens_cap: set) -> list:
    if sans_mur:
        return []
    bx_min, bx_max, by_min, by_max = cadre_z
    murs_poses = []
    murs_dispo = [b for b in liste_murs if fabricable(b, ens_mat, ens_cap)]
    for pr_mur in murs_dispo:
        larg_m, haut_m = pr_mur.largeur, pr_mur.hauteur
        for py in range(0, haut_g - haut_m + 1):
            for px in range(0, larg_g - larg_m + 1):
                en_bordure = (
                    (py + haut_m <= by_min) or (py >= by_max) or
                    (px + larg_m <= bx_min) or (px >= bx_max)
                )
                if en_bordure and plan_g.peut_placer(pr_mur, px, py):
                    inst_m = deepcopy(pr_mur)
                    plan_g.placer(inst_m, px, py)
                    murs_poses.append(inst_m)
    return murs_poses


def phase8_generer_fichiers(plan_g: Grille, rep_sortie: str = "."):
    os.makedirs(rep_sortie, exist_ok=True)
    dict_legende = {}
    map_symbole = {}
    iter_symbole = iter(CHAR_RESERVOIR)

    blocs_uniques = []
    vus_id = set()
    for py in range(plan_g.hauteur):
        for px in range(plan_g.largeur):
            occ = plan_g.cellules[py][px]
            if occ is not None and id(occ) not in vus_id:
                vus_id.add(id(occ))
                blocs_uniques.append(occ)

    for occ in blocs_uniques:
        cfg_b = occ.best_ammo if (occ.id in ("sorter", "inverted-sorter", "unloader") and getattr(occ, "best_ammo", "")) else ""
        cfg_ok = _resoudre_nom_item_msch(cfg_b)
        cle_u = (occ.id, occ.rotation, cfg_ok)
        if cle_u not in map_symbole:
            map_symbole[cle_u] = next(iter_symbole, "?")
        occ.char = map_symbole[cle_u]
        entree_l = {"id": occ.id, "width": occ.largeur, "height": occ.hauteur, "rotation": occ.rotation}
        if cfg_ok:
            entree_l["config"] = cfg_ok
        dict_legende[occ.char] = entree_l

    mat_ascii = [[" " for _ in range(plan_g.largeur)] for _ in range(plan_g.hauteur)]
    for occ in blocs_uniques:
        mat_ascii[occ.y][occ.x] = occ.char
        for dy in range(occ.hauteur):
            for dx in range(occ.largeur):
                if (dy != 0 or dx != 0) and 0 <= occ.y + dy < plan_g.hauteur and 0 <= occ.x + dx < plan_g.largeur:
                    mat_ascii[occ.y + dy][occ.x + dx] = "*"

    texte_schema = "\n".join("".join(lig) for lig in mat_ascii)
    with open(os.path.join(rep_sortie, "schema.txt"), "w", encoding="utf-8") as f_out:
        f_out.write(texte_schema)
    with open(os.path.join(rep_sortie, "legend.json"), "w", encoding="utf-8") as f_out:
        json.dump(dict_legende, f_out, ensure_ascii=False, indent=2)

    rep_dps = {
        "score_global": sum(b.dps_reel for b in blocs_uniques if b.type == "turret"),
        "dps_par_taille": sum((b.dps_par_taille for b in blocs_uniques if b.type == "turret"), 0.0),
        "dps_par_cout": sum((b.dps_par_cout for b in blocs_uniques if b.type == "turret"), 0.0),
        "tourelles": [b.id for b in blocs_uniques if b.type == "turret"],
    }
    with open(os.path.join(rep_sortie, "dps_report.txt"), "w", encoding="utf-8") as f_out:
        json.dump(rep_dps, f_out, ensure_ascii=False, indent=2)

    rep_infra = {
        "logistique": [b.id for b in blocs_uniques if b.type == "logistique"],
        "liquides": [b.id for b in blocs_uniques if b.type == "liquide"],
        "energie": [b.id for b in blocs_uniques if b.type == "energie"],
        "protection": [b.id for b in blocs_uniques if b.type == "protection"],
        "soin": [b.id for b in blocs_uniques if b.type == "soin"],
    }
    with open(os.path.join(rep_sortie, "infrastructure_report.txt"), "w", encoding="utf-8") as f_out:
        json.dump(rep_infra, f_out, ensure_ascii=False, indent=2)

    rep_val = {
        "nb_tourelles": len([b for b in blocs_uniques if b.type == "turret"]),
        "nb_tourelles_anti_air": len([b for b in blocs_uniques if b.type == "turret" and b.targets_air]),
        "nb_infra": len([b for b in blocs_uniques if b.type != "turret"]),
        "surface_blocs": sum(b.taille() for b in blocs_uniques),
    }
    with open(os.path.join(rep_sortie, "validation_report.txt"), "w", encoding="utf-8") as f_out:
        json.dump(rep_val, f_out, ensure_ascii=False, indent=2)

    return dict_legende, texte_schema

def _cle_signature_cerveau(larg_g: int, haut_g: int, ens_mat: set, ens_cap: set,
                           ens_ammo: set, sans_mur: bool, quota_aa: float) -> str:
    str_mat = ",".join(sorted(ens_mat | ens_cap))
    str_am = ",".join(sorted(ens_ammo)) if ens_ammo else "all"
    str_m = "nowall" if sans_mur else "wall"
    return f"{larg_g}x{haut_g}|{str_mat}|{str_am}|{str_m}|aa{int(round(quota_aa * 100))}"


def _charger_cerveau(chemin_cerveau: str) -> dict:
    defaut_c = {
        "version": "11.5-universal",
        "total_episodes": 0,
        "universal_episodes": 0,
        "neural_policy": {
            "pas_weights": {"0": [0.2, 0.0, 0.0], "4": [0.1, 0.5, -0.2], "5": [0.1, -0.2, 0.5]},
            "taille_weights": {"0": [0.1, -0.3, 0.2], "1": [0.2, 0.4, -0.1]},
            "ammo_synergy": {},
            "depth_rules": {"deep_graphite_bonus": 1.0, "heavy_thorium_bonus": 1.0},
        },
        "hall_of_fame": {},
    }
    if not os.path.isfile(chemin_cerveau):
        return defaut_c
    try:
        with open(chemin_cerveau, "r", encoding="utf-8") as f_in:
            lu = json.load(f_in)
            if isinstance(lu, dict) and "hall_of_fame" in lu:
                for cle_d, val_d in defaut_c.items():
                    lu.setdefault(cle_d, val_d)
                return lu
    except (OSError, ValueError):
        pass
    return defaut_c


def _sauvegarder_cerveau_atomique(chemin_cerveau: str, etat_cerveau: dict):
    chemin_tmp = chemin_cerveau + ".tmp"
    try:
        with open(chemin_tmp, "w", encoding="utf-8") as f_tmp:
            json.dump(etat_cerveau, f_tmp, ensure_ascii=False, indent=2)
            f_tmp.flush()
            os.fsync(f_tmp.fileno())
        os.replace(chemin_tmp, chemin_cerveau)
    except OSError:
        pass


def _extraire_vecteur_contexte(larg_g: int, haut_g: int, ens_mat: set, ens_cap: set) -> List[float]:
    v_prof = min(1.0, haut_g / 45.0)
    v_surf = min(1.0, (larg_g * haut_g) / 2500.0)
    v_tech = 1.0 if ("surge-alloy" in ens_mat or "thorium" in ens_mat) else 0.3
    return [1.0, v_prof, v_surf * v_tech]


def _predire_genome_neuronal(etat_cerveau: dict, larg_g: int, haut_g: int,
                             cadre_z: Tuple[int, int, int, int], ens_mat: set,
                             ens_cap: set, ens_ammo: set, cat_t: list,
                             exploration: float = 0.0) -> dict:
    pol = etat_cerveau.get("neural_policy", {})
    vec_x = _extraire_vecteur_contexte(larg_g, haut_g, ens_mat, ens_cap)
    mun_dispo = sorted({
        am for t in cat_t for am in (t.ammo_dps or {}).keys()
        if am != "power" and (not ens_ammo or am in ens_ammo)
    })
    paires_m = list(combinations(mun_dispo, 2)) if len(mun_dispo) >= 2 else [(next(iter(mun_dispo), "copper"),)]
    syn_map = pol.get("ammo_synergy", {})
    cle_prof = "deep" if haut_g >= 30 else ("mid" if haut_g >= 18 else "small")

    if random.random() < exploration:
        paire_sel = list(random.choice(paires_m))
        pas_sel = random.choice([0, 4, 5])
        tail_sel = random.choice([0, 1])
    else:
        def score_paire(p_cand):
            cle_p = f"{cle_prof}:{'+'.join(sorted(p_cand))}"
            bonus_h = 250.0 if (haut_g > 28 and "graphite" in p_cand) else 0.0
            return float(syn_map.get(cle_p, 0.0)) + bonus_h

        paire_sel = list(max(paires_m, key=score_paire))
        w_pas = pol.get("pas_weights", {"0": [0.2, 0.0, 0.0], "4": [0.1, 0.5, -0.2], "5": [0.1, -0.2, 0.5]})
        pas_sel = int(max(["0", "4", "5"], key=lambda k: sum(w * x for w, x in zip(w_pas.get(k, [0, 0, 0]), vec_x))))
        w_tail = pol.get("taille_weights", {"0": [0.1, -0.3, 0.2], "1": [0.2, 0.4, -0.1]})
        tail_sel = int(max(["0", "1"], key=lambda k: sum(w * x for w, x in zip(w_tail.get(k, [0, 0, 0]), vec_x))))

    ens_a_tmp, _ = _lignes_couloirs_internes(cadre_z, larg_g, haut_g, "liquids" in ens_cap, pas_sel)
    _, _, _, by_max_z = cadre_z
    lignes_tri = sorted(ens_a_tmp - {by_max_z - 1})
    map_a = {}
    for idx_l, yc in enumerate(lignes_tri):
        if exploration > 0.0 and random.random() < exploration:
            map_a[str(yc)] = random.choice(paire_sel)
        elif yc >= 20 and "graphite" in paire_sel:
            map_a[str(yc)] = "graphite"
        else:
            map_a[str(yc)] = paire_sel[idx_l % len(paire_sel)]

    return {"ammo_pair": paire_sel, "pas_travees": pas_sel, "gene_taille": tail_sel, "gene_ammo": map_a}


def _apprendre_politique_neuronale(etat_cerveau: dict, larg_g: int, haut_g: int,
                                   ens_mat: set, ens_cap: set, gen_gagnant: dict,
                                   gain_relatif: float):
    if not gen_gagnant or gain_relatif <= 0:
        return
    pol = etat_cerveau.setdefault("neural_policy", {})
    vec_x = _extraire_vecteur_contexte(larg_g, haut_g, ens_mat, ens_cap)
    lr = min(0.15, max(0.01, gain_relatif / 5000.0))

    cle_pas = str(gen_gagnant.get("pas_travees", 0))
    w_pas = pol.setdefault("pas_weights", {"0": [0.2, 0.0, 0.0], "4": [0.1, 0.5, -0.2], "5": [0.1, -0.2, 0.5]})
    if cle_pas in w_pas:
        w_pas[cle_pas] = [round(w + lr * x, 5) for w, x in zip(w_pas[cle_pas], vec_x)]

    cle_t = str(gen_gagnant.get("gene_taille", 0))
    w_tail = pol.setdefault("taille_weights", {"0": [0.1, -0.3, 0.2], "1": [0.2, 0.4, -0.1]})
    if cle_t in w_tail:
        w_tail[cle_t] = [round(w + lr * x, 5) for w, x in zip(w_tail[cle_t], vec_x)]

    paire_g = gen_gagnant.get("ammo_pair", [])
    if paire_g:
        cle_prof = "deep" if haut_g >= 30 else ("mid" if haut_g >= 18 else "small")
        cle_syn = f"{cle_prof}:{'+'.join(sorted(paire_g))}"
        syn_map = pol.setdefault("ammo_synergy", {})
        anc_v = float(syn_map.get(cle_syn, 0.0))
        syn_map[cle_syn] = round(anc_v + min(50.0, gain_relatif * 0.1), 2)

def _evaluer_complexe_complet(larg_g: int, haut_g: int, sans_mur: bool, lim_cible_y: int,
                              cadre_z: Tuple[int, int, int, int], ens_mat: set, ens_cap: set,
                              ens_ammo: set, quota_aa: float, cat_tourelles: list,
                              cat_soin: list, cat_log: list, cat_liq: list,
                              cat_en: list, cat_murs: list, genome_cand: dict):
    plan_cand = Grille(larg_g, haut_g)
    mode_liq = "liquids" in ens_cap
    pas_f = int(genome_cand.get("pas_travees", 0)) if genome_cand else 0

    placer_soin_minimal_avant(plan_cand, cat_soin, cadre_z, larg_g, haut_g, sans_mur, mode_liq)
    plan_cand, t_posees, t_top2, duo_ammo, _ = phase3_optimisation_dps(
        plan_cand, cat_tourelles, cat_soin, cadre_z, larg_g, haut_g,
        lim_cible_y, ens_cap, ens_ammo, quota_aa, genome_cand
    )
    reg_infra, conv_opt = phase4_infrastructure(
        plan_cand, t_posees, t_top2, cat_soin, cat_log, cat_liq, cat_en,
        cadre_z, larg_g, haut_g, lim_cible_y, sans_mur, ens_cap, duo_ammo, quota_aa, pas_f
    )
    dps_brut_tot, ratio_flux, _ = phase6_logistique_finale(
        plan_cand, t_posees, reg_infra, conv_opt, larg_g, haut_g
    )
    phase7_protection_compaction(plan_cand, cat_murs, cadre_z, larg_g, haut_g, sans_mur, ens_mat, ens_cap)

    vus_u = set()
    ods_poses = []
    nb_bat_1x1 = 0
    for py in range(haut_g):
        for px in range(larg_g):
            occ = plan_cand.cellules[py][px]
            if occ is not None and id(occ) not in vus_u:
                vus_u.add(id(occ))
                if occ.type == "soin" and occ.kind == "overdrive":
                    ods_poses.append(occ)
                elif occ.kind == "battery" and occ.taille() == 1:
                    nb_bat_1x1 += 1

    dps_effectif = 0.0
    for t_cur in t_posees:
        if not peut_couvrir_cible(t_cur, t_cur.x, t_cur.y, lim_cible_y):
            continue
        mult_od = 1.0
        tx_c, ty_c = t_cur.x + t_cur.largeur / 2.0, t_cur.y + t_cur.hauteur / 2.0
        for od in ods_poses:
            if math.hypot((od.x + od.largeur / 2.0) - tx_c, (od.y + od.hauteur / 2.0) - ty_c) <= od.portee:
                if od.speed_boost > mult_od:
                    mult_od = od.speed_boost
        dps_effectif += t_cur.dps_reel * mult_od

    fit_global = (dps_effectif * ratio_flux) - (nb_bat_1x1 * 25.0)
    return fit_global, dps_brut_tot, plan_cand, t_posees, duo_ammo


def _tirer_scenario_universel():
    paliers_mat = (
        {"copper", "lead", "graphite", "silicon", "titanium"},
        {"copper", "lead", "graphite", "silicon", "titanium", "metaglass", "thorium"},
        {"copper", "lead", "graphite", "silicon", "titanium", "metaglass", "thorium", "plastanium"},
        {"copper", "lead", "graphite", "silicon", "titanium", "metaglass", "thorium", "surge-alloy"},
        {"copper", "lead", "graphite", "silicon", "titanium", "metaglass", "thorium", "plastanium", "surge-alloy"},
    )
    paliers_cap = ({"energy"}, {"energy", "liquids"}, {"energy", "liquids"})
    w_rnd = random.randrange(16, 48, 2)
    h_rnd = random.randrange(16, 46, 2)
    mat_rnd = set(random.choice(paliers_mat))
    cap_rnd = set(random.choice(paliers_cap))
    am_rnd = {m for m in mat_rnd if m in ("copper", "lead", "graphite", "silicon", "thorium", "plastanium", "surge-alloy", "metaglass")}
    return w_rnd, h_rnd, mat_rnd, cap_rnd, am_rnd


def meil_fit_maj(cerveau: dict, cle: str, fit_act: float) -> bool:
    ancien = cerveau.get("hall_of_fame", {}).get(cle, {}).get("best_fitness", -1e9)
    return fit_act > ancien


def main():
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("largeur", type=int)
    analyseur.add_argument("hauteur", type=int)
    analyseur.add_argument("ressources", nargs="+")
    analyseur.add_argument("--data", default=None)
    analyseur.add_argument("--no-wall", action="store_true")
    analyseur.add_argument("--duree", type=float, default=30.0)
    analyseur.add_argument("--anti-air", type=float, default=15.0)
    analyseur.add_argument("--out", default=".")
    analyseur.add_argument("--ammo", nargs="*", default=[])
    analyseur.add_argument("--train", action="store_true")
    analyseur.add_argument("--brain", default=None)
    args_cli = analyseur.parse_args()

    larg_g, haut_g, liste_res = args_cli.largeur, args_cli.hauteur, args_cli.ressources
    ens_ammo = set(args_cli.ammo) if args_cli.ammo else set()
    chemin_json = liste_res.pop() if (liste_res and liste_res[-1].lower().endswith(".json")) else args_cli.data
    quota_aa = max(0.0, min(100.0, args_cli.anti_air)) / 100.0
    rep_script = os.path.dirname(os.path.abspath(__file__))
    chemin_cerveau = args_cli.brain or os.path.join(rep_script, "mindustry_brain.json")

    ens_mat, ens_cap = phase0_validation(larg_g, haut_g, liste_res, chemin_json)
    cat_t, cat_log, cat_liq, cat_murs, cat_en, cat_soin = phase1_chargement(chemin_json, ens_mat, ens_cap, ens_ammo)
    phase2_ciblage(cat_t, larg_g, haut_g)
    cadre_z, _, _ = calculer_zone_tourelles(larg_g, haut_g, args_cli.no_wall)
    lim_cible_y = -8

    etat_cerveau = _charger_cerveau(chemin_cerveau)
    cle_sig = _cle_signature_cerveau(larg_g, haut_g, ens_mat, ens_cap, ens_ammo, args_cli.no_wall, quota_aa)
    entree_hof = etat_cerveau["hall_of_fame"].get(cle_sig, {})
    meilleur_gen = entree_hof.get("best_genome") or _predire_genome_neuronal(
        etat_cerveau, larg_g, haut_g, cadre_z, ens_mat, ens_cap, ens_ammo, cat_t, 0.0
    )

    meilleur_fit, meilleur_dps, meilleur_plan, meilleures_t, meilleur_duo = _evaluer_complexe_complet(
        larg_g, haut_g, args_cli.no_wall, lim_cible_y, cadre_z, ens_mat, ens_cap,
        ens_ammo, quota_aa, cat_t, cat_soin, cat_log, cat_liq, cat_en, cat_murs, meilleur_gen
    )

    if args_cli.train:
        print(f"[TRAIN UNIVERSEL] Cible: {cle_sig} | Fit initial: {meilleur_fit:.0f} (Ctrl+C pour sauvegarder)")
        try:
            ep_loc = 0
            while True:
                ep_loc += 1
                etat_cerveau["total_episodes"] = int(etat_cerveau.get("total_episodes", 0)) + 1
                if ep_loc % 2 == 1:
                    gen_test = _predire_genome_neuronal(
                        etat_cerveau, larg_g, haut_g, cadre_z, ens_mat, ens_cap, ens_ammo, cat_t, 0.45
                    )
                    fit_c, dps_c, plan_c, t_c, duo_c = _evaluer_complexe_complet(
                        larg_g, haut_g, args_cli.no_wall, lim_cible_y, cadre_z, ens_mat, ens_cap,
                        ens_ammo, quota_aa, cat_t, cat_soin, cat_log, cat_liq, cat_en, cat_murs, gen_test
                    )
                    if fit_c > meilleur_fit:
                        gain = fit_c - meilleur_fit
                        meilleur_fit, meilleur_dps, meilleur_plan, meilleures_t, meilleur_duo = fit_c, dps_c, plan_c, t_c, duo_c
                        meilleur_gen = gen_test
                        _apprendre_politique_neuronale(etat_cerveau, larg_g, haut_g, ens_mat, ens_cap, gen_test, gain)
                        etat_cerveau["hall_of_fame"][cle_sig] = {"best_fitness": meilleur_fit, "best_dps": meilleur_dps, "best_genome": meilleur_gen}
                        _sauvegarder_cerveau_atomique(chemin_cerveau, etat_cerveau)
                        phase8_generer_fichiers(meilleur_plan, args_cli.out)
                        print(f"[RECORD CIBLE Ep {ep_loc}] Fit: {meilleur_fit:.0f} | DPS: {meilleur_dps:.0f} | Tourelles: {len(meilleures_t)} | Ammo: {meilleur_duo}")
                else:
                    etat_cerveau["universal_episodes"] = int(etat_cerveau.get("universal_episodes", 0)) + 1
                    w_u, h_u, m_u, c_u, a_u = _tirer_scenario_universel()
                    ct_u, cl_u, clq_u, cm_u, ce_u, cs_u = phase1_chargement(chemin_json, m_u, c_u, a_u)
                    if not ct_u:
                        continue
                    cz_u, _, _ = calculer_zone_tourelles(w_u, h_u, False)
                    sig_u = _cle_signature_cerveau(w_u, h_u, m_u, c_u, a_u, False, 0.15)
                    gen_u = _predire_genome_neuronal(etat_cerveau, w_u, h_u, cz_u, m_u, c_u, a_u, ct_u, 0.5)
                    fit_u, dps_u, _, _, _ = _evaluer_complexe_complet(
                        w_u, h_u, False, lim_cible_y, cz_u, m_u, c_u, a_u, 0.15, ct_u, cs_u, cl_u, clq_u, ce_u, cm_u, gen_u
                    )
                    anc_u = etat_cerveau["hall_of_fame"].get(sig_u, {}).get("best_fitness", 0.0)
                    if fit_u > anc_u:
                        _apprendre_politique_neuronale(etat_cerveau, w_u, h_u, m_u, c_u, gen_u, max(50.0, fit_u - anc_u))
                        etat_cerveau["hall_of_fame"][sig_u] = {"best_fitness": fit_u, "best_dps": dps_u, "best_genome": gen_u}
                        _sauvegarder_cerveau_atomique(chemin_cerveau, etat_cerveau)
                        print(f"[UNIVERSEL Ep {ep_loc}] Appris {w_u}x{h_u} -> Fit: {fit_u:.0f} | DPS: {dps_u:.0f}")
        except KeyboardInterrupt:
            print("\n[STOP] Interruption Ctrl+C detectee : sauvegarde atomique du cerveau universel...")

    if meil_fit_maj(etat_cerveau, cle_sig, meilleur_fit):
        etat_cerveau["hall_of_fame"][cle_sig] = {"best_fitness": meilleur_fit, "best_dps": meilleur_dps, "best_genome": meilleur_gen or {}}
    _sauvegarder_cerveau_atomique(chemin_cerveau, etat_cerveau)

    phase8_generer_fichiers(meilleur_plan, args_cli.out)
    nb_aa = sum(1 for t in meilleures_t if t.targets_air)
    pct_aa = (100.0 * nb_aa / max(1, len(meilleures_t)))
    print(f"\n[OK V11.5] Tourelles: {len(meilleures_t)} | Anti-Air: {pct_aa:.0f}% | Top2 Ammo: {meilleur_duo} | DPS: {meilleur_dps:.0f}")

if __name__ == "__main__":
    main()
    
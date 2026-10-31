#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mindustry Turret Complex Generator — v9.6 (FINAL VERIFIED)
BLOC 1 / 8 : Imports, Constantes Globales, Bloc & Grille
"""

import json
import math
import sys
import os
import argparse
import string
import time
import random

from copy import deepcopy
from dataclasses import dataclass, field
from typing import List, Tuple, Set
from collections import defaultdict
from itertools import islice

SEUIL_LOGISTIQUE    = 0.99
TOLERANCE_FLOTTANTE = 0.01
TEMPS_MAX_EXECUTION = 1800
CAPACITES_SPECIALES = {"energy", "liquids", "utilities"}

CHAR_RESERVOIR = [
    c for c in (
        string.ascii_uppercase +
        string.ascii_lowercase +
        string.digits +
        "!@#$%^&()-_=+[]{}|;:,.<>?/"
    ) if c not in ('*', ' ', '"', "'", '\\')
]


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
    consomme_liquide: bool = False
    targets_air: bool = False
    targets_ground: bool = True
    laser_range: float = 6.0
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
        val = sum(self.materiaux.values())
        return val if val > 0 else 1.0


class Grille:
    def __init__(self, largeur: int, hauteur: int):
        self.largeur = largeur
        self.hauteur = hauteur
        self.cellules = [[None] * largeur for _ in range(hauteur)]

    def peut_placer(self, b: Bloc, x: int, y: int) -> bool:
        if x < 0 or y < 0 or x + b.largeur > self.largeur or y + b.hauteur > self.hauteur:
            return False
        for dy in range(b.hauteur):
            for dx in range(b.largeur):
                if self.cellules[y + dy][x + dx] is not None:
                    return False
        return True

    def placer(self, b: Bloc, x: int, y: int):
        b.x, b.y = x, y
        for dy in range(b.hauteur):
            for dx in range(b.largeur):
                self.cellules[y + dy][x + dx] = b

    def retirer(self, b: Bloc):
        for dy in range(b.hauteur):
            for dx in range(b.largeur):
                py, px = b.y + dy, b.x + dx
                if 0 <= py < self.hauteur and 0 <= px < self.largeur:
                    if self.cellules[py][px] is b:
                        self.cellules[py][px] = None

    def liberer_zone(self, x0: int, y0: int, w: int, h: int, liste_a_filtrer: list = None):
        vus = set()
        for y in range(max(0, y0), min(self.hauteur, y0 + h)):
            for x in range(max(0, x0), min(self.largeur, x0 + w)):
                b = self.cellules[y][x]
                if b is not None and id(b) not in vus:
                    vus.add(id(b))
                    self.retirer(b)
                    if liste_a_filtrer is not None and b in liste_a_filtrer:
                        liste_a_filtrer.remove(b)

    def surface_utilisee_reelle(self) -> int:
        vus = set()
        total = 0
        for row in self.cellules:
            for c in row:
                if c is not None and id(c) not in vus:
                    vus.add(id(c))
                    total += c.taille()
        return total


# ─────────────────────────────────────────────────────────────────────────────
# BLOC 2 / 8 : Phase 0 & Phase 1 (Données Officielles, Anti-Air Pur & Alias)
# ─────────────────────────────────────────────────────────────────────────────

VRAIES_PORTEES = {
    "duo": 20.0, "scatter": 22.5, "scorch": 7.5, "hail": 29.375, "arc": 11.25,
    "wave": 13.75, "lancer": 20.625, "salvo": 19.0, "swarmer": 30.0,
    "ripple": 36.25, "cyclone": 25.0, "fuse": 11.25, "spectre": 32.5,
    "meltdown": 24.375, "foreshadow": 62.5, "tsunami": 23.75, "parallax": 28.75,
}

PORTEES_BOOST_PHASE = {
    "mender": 8.5,
    "mend-projector": 16.25,
    "force-projector": 17.7,
    "overdrive-projector": 16.875,
    "overdrive-dome": 10.625,
}

ANTI_AIR_PUR = {"scatter", "parallax"}
ALIAS_RESSOURCES = {"plastinum": "plastanium", "plastinium": "plastanium"}


def phase0_validation(largeur: int, hauteur: int, ressources: list, data_path: str) -> Tuple[set, set]:
    if not (5 <= largeur <= 100 and 5 <= hauteur <= 100):
        raise ValueError(f"Dimensions invalides: {largeur}x{hauteur} (attendu entre 5 et 100)")
    if not os.path.isfile(data_path):
        raise FileNotFoundError(f"Fichier data.json introuvable: {data_path}")
    res_norm = [ALIAS_RESSOURCES.get(r.lower(), r.lower()) for r in ressources]
    mat_dispo = {r for r in res_norm if r not in CAPACITES_SPECIALES}
    cap_dispo = {r for r in res_norm if r in CAPACITES_SPECIALES}
    return mat_dispo, cap_dispo


def fabricable(bloc: Bloc, mat_dispo: set, cap_dispo: set) -> bool:
    return (set(bloc.materiaux.keys()) <= mat_dispo and bloc.capacites <= cap_dispo)


def ammo_autorisee(bloc: Bloc, ammo_dispo: set) -> bool:
    if not ammo_dispo or bloc.ammo_optional or not bloc.ammo_type or bloc.ammo_type == "power":
        return True
    if bloc.ammo_dps:
        if "power" in bloc.ammo_dps:
            return True
        return bool(set(bloc.ammo_dps.keys()) & ammo_dispo)
    return bloc.ammo_type in ammo_dispo


def parse_bloc(d: dict, type_bloc: str, cap_dispo: set) -> Bloc:
    bid = d.get("id", d.get("nom", "unknown"))
    materiaux = {
        k[5:]: v for k, v in d.items()
        if k.startswith("cost_") and isinstance(v, (int, float)) and v > 0
    }
    energy_consume = d.get("energy_consume", 0.0) or 0.0
    consomme_energie = energy_consume > 0
    capacites = set(d.get("capacites", []))
    boosters = d.get("boosters", [])
    accepte_liquide = (bool(boosters) or "liquids" in capacites) and ("liquids" in cap_dispo)
    vitesse = d.get("speed", d.get("flow", d.get("vitesse_transport", 0.0))) or 0.0
    l_range = d.get("laser_range", 6.0) or 6.0
    s_boost = d.get("speed_boost", 1.0) or 1.0

    t_air = d.get("targets_air", bid in ANTI_AIR_PUR)
    t_gnd = d.get("targets_ground", bid not in ANTI_AIR_PUR)

    if type_bloc == "soin":
        portee = d.get("range_phase_boost", PORTEES_BOOST_PHASE.get(bid, d.get("range", 0.0)))
    else:
        portee = VRAIES_PORTEES.get(bid, d.get("range", d.get("portee", 0.0)))

    return Bloc(
        id=bid,
        nom=d.get("name_fr", d.get("nom", bid)),
        largeur=d.get("width", d.get("largeur", 1)),
        hauteur=d.get("height", d.get("hauteur", 1)),
        rotation=d.get("rotation", 0),
        type=type_bloc,
        kind=d.get("kind", ""),
        materiaux=materiaux,
        capacites=capacites,
        dps_brut=d.get("dps", d.get("dps_brut", 0.0)),
        portee=float(portee),
        rate=d.get("rate", 1.0) or 1.0,
        speed_boost=float(s_boost),
        consomme_energie=consomme_energie,
        consomme_liquide=accepte_liquide,
        targets_air=bool(t_air and not t_gnd),
        targets_ground=bool(t_gnd),
        laser_range=float(l_range),
        ammo_type=d.get("ammo_type", ""),
        ammo_optional=d.get("ammo_optional", False if type_bloc == "turret" else True),
        ammo_dps=d.get("ammo_dps", {}),
        health=d.get("health", 0.0),
        vitesse_transport=float(vitesse),
    )


def calculer_dps_reel(bloc: Bloc, ammo_dispo: set) -> Tuple[float, str]:
    if bloc.ammo_dps and ammo_dispo:
        cand = [(val, nom) for nom, val in bloc.ammo_dps.items() if nom in ammo_dispo or nom == "power"]
        if cand:
            cand.sort(reverse=True)
            best_val, best_nom = next(iter(cand))
            return float(best_val), str(best_nom)
    if bloc.ammo_dps:
        cand = [(val, nom) for nom, val in bloc.ammo_dps.items()]
        cand.sort(reverse=True)
        if cand:
            best_val, best_nom = next(iter(cand))
            return float(best_val), str(best_nom)
    return float(bloc.dps_brut), str(bloc.ammo_type or "")


def phase1_chargement(data_path: str, mat_dispo: set, cap_dispo: set, ammo_dispo: set):
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    tourelles, logistique, liquides, protection, energie, soin = [], [], [], [], [], []
    off_raw = dict(data.get("turrets_offense", {}))
    off_raw.setdefault("scatter", {
        "name_fr": "Eparpilleur", "dps": 90, "ammo_type": "lead", "rate": 6.6, "range": 22.5,
        "ammo_dps": {"scrap": 45, "lead": 65, "metaglass": 90},
        "cost_copper": 85, "cost_lead": 45, "width": 2, "height": 2,
        "targets_air": True, "targets_ground": False, "boosters": ["water", "cryofluid"]
    })

    for bid, d in off_raw.items():
        if not isinstance(d, dict):
            continue
        d = dict(d, id=bid)
        if bid in ("meltdown", "spectre", "foreshadow"):
            d["width"], d["height"] = 4, 4
        elif bid in ("wave", "parallax", "scatter"):
            d["width"], d["height"] = 2, 2
        if bid == "foreshadow":
            d.setdefault("cost_surge-alloy", 300)
            d.setdefault("cost_plastanium", 200)
            d["ammo_type"] = "surge-alloy"
            d["ammo_dps"] = {"surge-alloy": d.get("dps", 500)}
        elif bid in ("meltdown", "tsunami", "wave", "parallax"):
            d["ammo_type"] = "power"
            d["ammo_dps"] = {"power": d.get("dps", 180)}
        b = parse_bloc(d, "turret", cap_dispo)
        if not fabricable(b, mat_dispo, cap_dispo) or not ammo_autorisee(b, ammo_dispo):
            continue
        if b.dps_brut <= 0 or b.portee <= 0 or (b.consomme_energie and "energy" not in cap_dispo):
            continue
        b.dps_reel, b.best_ammo = calculer_dps_reel(b, ammo_dispo)
        b.dps_par_taille = b.dps_reel / b.taille()
        b.dps_par_cout = b.dps_reel / b.cout_total()
        b.dps_par_surface = b.dps_par_taille
        tourelles.append(b)

    dist_raw = dict(data.get("distribution_blocks", {}))
    dist_raw.setdefault("container", {"width": 2, "height": 2, "kind": "storage", "cost_titanium": 100})
    dist_raw.setdefault("vault", {"width": 3, "height": 3, "kind": "storage", "cost_titanium": 250, "cost_thorium": 125})
    for bid, d in dist_raw.items():
        b = parse_bloc(dict(d, id=bid), "logistique", cap_dispo)
        if fabricable(b, mat_dispo, cap_dispo):
            logistique.append(b)

    liq_raw = dict(data.get("liquid_blocks", {}))
    liq_raw.setdefault("pulse-conduit", {"width": 1, "height": 1, "kind": "conduit", "flow": 16, "cost_titanium": 2, "cost_metaglass": 1})
    liq_raw.setdefault("liquid-router", {"width": 1, "height": 1, "kind": "router", "flow": 4, "cost_graphite": 4, "cost_metaglass": 2})
    liq_raw.setdefault("bridge-conduit", {"width": 1, "height": 1, "kind": "bridge", "flow": 4, "range": 4, "cost_graphite": 4, "cost_metaglass": 8})
    liq_raw.setdefault("liquid-container", {"width": 2, "height": 2, "kind": "storage", "flow": 0, "cost_titanium": 10, "cost_metaglass": 15})
    for bid, d in liq_raw.items():
        if "pump" in bid.lower() or "extractor" in bid.lower():
            continue
        b = parse_bloc(dict(d, id=bid), "liquide", cap_dispo)
        if not b.kind:
            b.kind = "bridge" if "bridge" in bid else ("storage" if ("tank" in bid or "container" in bid) else ("router" if "router" in bid else "conduit"))
        if fabricable(b, mat_dispo, cap_dispo):
            liquides.append(b)

    for bid, d in data.get("walls", {}).items():
        b = parse_bloc(dict(d, id=bid), "protection", cap_dispo)
        if fabricable(b, mat_dispo, cap_dispo):
            protection.append(b)

    for bid, d in data.get("energy_sources", {}).items():
        b = parse_bloc(dict(d, id=bid), "energie", cap_dispo)
        if fabricable(b, mat_dispo, cap_dispo):
            energie.append(b)

    prot_raw = dict(data.get("turrets_protection", {}))
    prot_raw.setdefault("force-projector", {"width": 3, "height": 3, "kind": "shield", "range": 12.7, "range_phase_boost": 17.7, "energy_consume": 240, "cost_lead": 100, "cost_titanium": 75, "cost_silicon": 125, "boosters": ["water", "cryofluid"]})
    prot_raw.setdefault("overdrive-projector", {"width": 2, "height": 2, "kind": "overdrive", "range": 10.0, "range_phase_boost": 16.875, "speed_boost": 2.25, "energy_consume": 210, "cost_lead": 100, "cost_titanium": 75, "cost_silicon": 75, "cost_plastanium": 30})
    prot_raw.setdefault("overdrive-dome", {"width": 3, "height": 3, "kind": "overdrive", "range": 10.625, "range_phase_boost": 10.625, "speed_boost": 2.5, "energy_consume": 450, "cost_lead": 200, "cost_titanium": 130, "cost_silicon": 130, "cost_plastanium": 80, "cost_surge-alloy": 120})
    for bid, d in prot_raw.items():
        d = dict(d, id=bid)
        if not d.get("kind"):
            d["kind"] = "shield" if "force" in bid else ("overdrive" if "overdrive" in bid else "healer")
        b = parse_bloc(d, "soin", cap_dispo)
        if (not b.consomme_energie or "energy" in cap_dispo) and fabricable(b, mat_dispo, cap_dispo):
            soin.append(b)

    tourelles.sort(key=lambda t: (-t.dps_par_surface, -t.dps_reel))
    logistique.sort(key=lambda l: (0 if l.kind == "conveyor" else 1, -l.vitesse_transport))
    liquides.sort(key=lambda lq: (0 if lq.kind == "conduit" else 1, -lq.vitesse_transport))
    protection.sort(key=lambda w: (-w.health, w.cout_total()))
    return tourelles, logistique, liquides, protection, energie, soin
    

# ─────────────────────────────────────────────────────────────────────────────
# BLOC 3 / 8 : Phase 2 (Cible à -2), Couloirs Alignés & Soin sur 14 Lignes
# ─────────────────────────────────────────────────────────────────────────────

def phase2_ciblage(tourelles: list, largeur: int, hauteur: int) -> Tuple[float, float, Tuple[float, float], int]:
    if not tourelles:
        raise ValueError("Aucune tourelle offensive fabricable disponible.")
    portee_max = max(t.portee for t in tourelles)
    distance_cible = 2
    position_cible = (largeur / 2.0, -2.0)
    return portee_max, distance_cible, position_cible, hauteur


def calculer_zone_tourelles(largeur: int, hauteur: int, no_wall: bool) -> Tuple[Tuple[int, int, int, int], int, str]:
    if no_wall:
        return (0, largeur, 0, hauteur), 0, "none"
    m = max(largeur, hauteur)
    if m < 10:
        return (0, largeur, 0, hauteur - 1), 1, "simple_rear_line"
    elif m <= 12:
        return (1, largeur - 1, 1, hauteur - 1), 1, "small_lateral_loop"
    else:
        return (2, largeur - 2, 2, hauteur - 2), 2, "large_2x2_loop"


def _lignes_couloirs_internes(zone: Tuple[int, int, int, int], largeur: int,
                              hauteur: int, avec_liquides: bool = False) -> Tuple[Set[int], Set[int]]:
    x_min, x_max, y_min, y_max = zone
    if min(largeur, hauteur) < 10:
        return {max(y_min, y_max - 1)}, set()

    lignes_ammo = {y_min, y_max - 1}
    lignes_liq = set()

    if avec_liquides and (y_max - y_min) >= 14:
        y_liq_bas = y_max - 2
        lignes_liq.add(y_liq_bas)
        y_ammo_bas = y_liq_bas - 4
        if y_ammo_bas > y_min + 4:
            lignes_ammo.add(y_ammo_bas)
        else:
            y_ammo_bas = y_liq_bas

        y = y_min
        toggle_liq = True
        rang = 0
        while True:
            pas = 4 if rang < 2 else 5
            if y + pas >= y_ammo_bas - 2:
                if toggle_liq and (y_ammo_bas - y) >= 4:
                    lignes_liq.add((y + y_ammo_bas) // 2)
                break
            y += pas
            if toggle_liq:
                lignes_liq.add(y)
            else:
                lignes_ammo.add(y)
            toggle_liq = not toggle_liq
            rang += 1
    else:
        y = y_min + 7
        while y < y_max - 1:
            lignes_ammo.add(y)
            y += 7

    return lignes_ammo, lignes_liq


def _zone_interieure_tourelles(zone: Tuple[int, int, int, int], largeur: int,
                               hauteur: int, avec_liquides: bool = False) -> Tuple[int, int, int, int]:
    x_min, x_max, y_min, y_max = zone
    if min(largeur, hauteur) >= 14:
        marge_g = 3 if avec_liquides else 1
        marge_d = 4 if avec_liquides else 2
        return (x_min + marge_g, x_max - marge_d, y_min + 1, y_max - 1)
    return (x_min + 1, max(x_min + 2, x_max - 1), y_min + 1, max(y_min + 2, y_max - 1))


def placer_soin_minimal_avant(grille: Grille, soin_blocs: list,
                              zone: Tuple[int, int, int, int], largeur: int,
                              hauteur: int, no_wall: bool, avec_liquides: bool = False) -> list:
    healers = [s for s in soin_blocs if s.kind == "healer" or s.id in ("mender", "mend-projector")]
    if not healers:
        return []

    x_min, x_max, y_min, y_max = zone
    ix_min, ix_max, _, _ = _zone_interieure_tourelles(zone, largeur, hauteur, avec_liquides)
    lignes_ammo, lignes_liq = _lignes_couloirs_internes(zone, largeur, hauteur, avec_liquides)

    cibles_murs = set()
    if not no_wall:
        for y in range(0, min(y_min, hauteur)):
            for x in range(0, largeur):
                cibles_murs.add((x, y))
        for y in range(0, min(14, hauteur)):
            for x in range(0, x_min):
                cibles_murs.add((x, y))
            for x in range(x_max, largeur):
                cibles_murs.add((x, y))
    else:
        for x in range(x_min, x_max):
            cibles_murs.add((x, y_min))

    soin_tries = sorted(healers, key=lambda s: (-s.portee, s.taille()))
    couverts = set()
    places = []

    while len(couverts) < len(cibles_murs):
        m_proto, m_pos, m_gain, m_couv = None, None, 0, set()
        for s_proto in soin_tries:
            r = s_proto.portee
            for y in range(y_min + 1, min(y_max - s_proto.hauteur, y_min + 15)):
                if any((y + dy) in lignes_ammo or (y + dy) in lignes_liq for dy in range(s_proto.hauteur)):
                    continue
                for x in range(ix_min, ix_max - s_proto.largeur + 1):
                    if not grille.peut_placer(s_proto, x, y):
                        continue
                    cx, cy = x + s_proto.largeur / 2.0, y + s_proto.hauteur / 2.0
                    couv = {(mx, my) for (mx, my) in cibles_murs if math.hypot((mx + 0.5) - cx, (my + 0.5) - cy) <= r}
                    gain = len(couv - couverts)
                    if gain > m_gain:
                        m_gain, m_proto, m_pos, m_couv = gain, s_proto, (x, y), couv

        if m_proto is None or m_gain == 0:
            break
        s = deepcopy(m_proto)
        px, py = m_pos
        grille.placer(s, px, py)
        places.append(s)
        couverts |= m_couv

    return places


# ─────────────────────────────────────────────────────────────────────────────
# BLOC 4 / 8 : Top 2 Munitions (Garantie Anti-Air), Quota 15% & Stratification
# ─────────────────────────────────────────────────────────────────────────────

def _couloir_proche(t: Bloc, y: int, lignes_c: set) -> int:
    for yc in sorted(lignes_c):
        if yc == y - 1 or yc == y + t.hauteur:
            return yc
    return -1


def distance_a_cible(tourelle: Bloc, x: int, y: int, y_cible_min: int) -> float:
    centre_y = y + tourelle.hauteur / 2.0
    return abs(centre_y - y_cible_min)


def peut_couvrir_cible(tourelle: Bloc, x: int, y: int, y_cible_min: int) -> bool:
    return distance_a_cible(tourelle, x, y, y_cible_min) <= tourelle.portee


def selectionner_top_2_munitions(tourelles: list, ammo_dispo: set, y_cible_min: int,
                                 y_depart: int) -> Tuple[List[str], List[Bloc]]:
    scores_ammo = defaultdict(float)
    scores_aa_ammo = defaultdict(float)
    aa_electrique_dispo = any(
        t.targets_air and (t.ammo_type == "power" or "power" in t.ammo_dps)
        for t in tourelles
    )

    for t in tourelles:
        if not t.ammo_dps:
            continue
        for am, val in t.ammo_dps.items():
            if am == "power":
                continue
            if not ammo_dispo or am in ammo_dispo:
                dps_surf = float(val) / t.taille()
                if t.targets_air and dps_surf > scores_aa_ammo[am]:
                    scores_aa_ammo[am] = dps_surf
                if t.portee >= abs((y_depart + t.hauteur / 2.0) - y_cible_min):
                    if dps_surf > scores_ammo[am]:
                        scores_ammo[am] = dps_surf

    ammo_triees = sorted(scores_ammo.keys(), key=lambda a: (-scores_ammo[a], a))
    top_2 = list(islice(ammo_triees, 0, 2))

    if not aa_electrique_dispo and scores_aa_ammo:
        best_aa_am = max(scores_aa_ammo.keys(), key=lambda a: (scores_aa_ammo[a], scores_ammo.get(a, 0.0)))
        if best_aa_am not in top_2:
            if len(top_2) < 2:
                top_2.append(best_aa_am)
            else:
                top_2[-1] = best_aa_am

    top_set = set(top_2)
    tourelles_filtrees = []
    for t in tourelles:
        t_copie = deepcopy(t)
        if t_copie.ammo_type == "power" or "power" in t_copie.ammo_dps:
            t_copie.best_ammo = "power"
            tourelles_filtrees.append(t_copie)
            continue
        cand = [(val, nom) for nom, val in t_copie.ammo_dps.items() if nom in top_set]
        if cand:
            cand.sort(reverse=True)
            best_val, best_nom = next(iter(cand))
            t_copie.dps_reel = float(best_val)
            t_copie.best_ammo = str(best_nom)
            t_copie.dps_par_taille = t_copie.dps_reel / t_copie.taille()
            t_copie.dps_par_surface = t_copie.dps_par_taille
            t_copie.dps_par_cout = t_copie.dps_reel / t_copie.cout_total()
            tourelles_filtrees.append(t_copie)

    return top_2, tourelles_filtrees


def remplir_glouton_stratifie(grille: Grille, tourelles: list, zone: Tuple[int, int, int, int],
                              y_cible_min: int, avec_liquides: bool, ratio_aa: float = 0.15) -> list:
    ix_min, ix_max, iy_min, iy_max = _zone_interieure_tourelles(
        zone, grille.largeur, grille.hauteur, avec_liquides
    )
    lignes_ammo, lignes_liq = _lignes_couloirs_internes(
        zone, grille.largeur, grille.hauteur, avec_liquides
    )

    t_sol_dps    = sorted([t for t in tourelles if not t.targets_air], key=lambda t: (-round(t.dps_par_surface, 1), t.portee, -t.dps_reel))
    t_sol_portee = sorted([t for t in tourelles if not t.targets_air], key=lambda t: (-t.portee, -t.dps_par_surface, -t.dps_reel))
    t_aa_pures   = sorted([t for t in tourelles if t.targets_air], key=lambda t: (-t.dps_par_surface, -t.portee))

    sentinelle = Bloc(id="__res__", nom="Res", largeur=1, hauteur=1)
    cases_res = []
    for y in range(iy_min, iy_max):
        for x in range(ix_min, ix_max):
            if (y in lignes_ammo or y in lignes_liq) and grille.cellules[y][x] is None:
                grille.cellules[y][x] = sentinelle
                cases_res.append((x, y))

    placements = []
    ammo_par_couloir = {}
    nb_aa = 0

    for y in range(iy_min, iy_max):
        if y in lignes_ammo or y in lignes_liq:
            continue
        for x in range(ix_min, ix_max):
            if grille.cellules[y][x] is not None:
                continue

            besoin_aa = bool(t_aa_pures) and ((nb_aa / max(1, len(placements) + 1)) < ratio_aa)
            groupes = (
                [(t_aa_pures, False), (t_sol_dps, True), (t_sol_portee, False)]
                if besoin_aa else
                [(t_sol_dps, True), (t_sol_portee, False), (t_aa_pures, False)]
            )

            placee = False
            for candidats, exiger_portee in groupes:
                if placee:
                    break
                for t_proto in candidats:
                    if x + t_proto.largeur > ix_max or y + t_proto.hauteur > iy_max:
                        continue
                    if exiger_portee and not peut_couvrir_cible(t_proto, x, y, y_cible_min):
                        continue
                    yc_ammo = _couloir_proche(t_proto, y, lignes_ammo)
                    if t_proto.best_ammo and t_proto.best_ammo != "power":
                        if yc_ammo == -1:
                            continue
                        if yc_ammo in ammo_par_couloir and ammo_par_couloir[yc_ammo] != t_proto.best_ammo:
                            continue
                    if avec_liquides and t_proto.consomme_liquide and lignes_liq:
                        yc_liq = _couloir_proche(t_proto, y, lignes_liq)
                        touche_flanc_liq = (x == ix_min or x + t_proto.largeur == ix_max)
                        if yc_liq == -1 and not touche_flanc_liq:
                            continue
                    if grille.peut_placer(t_proto, x, y):
                        t = deepcopy(t_proto)
                        grille.placer(t, x, y)
                        placements.append(t)
                        if t.targets_air:
                            nb_aa += 1
                        if yc_ammo != -1 and t.best_ammo and t.best_ammo != "power":
                            ammo_par_couloir[yc_ammo] = t.best_ammo
                        placee = True
                        break

    for rx, ry in cases_res:
        if grille.cellules[ry][rx] is sentinelle:
            grille.cellules[ry][rx] = None
    return placements
    

# ─────────────────────────────────────────────────────────────────────────────
# BLOC 5 / 8 : Boucliers, Accélérants & Stockages Collés (Fixes 1 & C)
# ─────────────────────────────────────────────────────────────────────────────

def _placer_boucliers_et_accelerants(grille: Grille, tourelles_placees: list, soin_blocs: list,
                                     zone: Tuple[int, int, int, int], largeur: int, hauteur: int,
                                     y_cible_min: int, avec_liquides: bool) -> list:
    if len(tourelles_placees) <= 25:
        return []
    ix_min, ix_max, iy_min, iy_max = _zone_interieure_tourelles(zone, largeur, hauteur, avec_liquides)
    lignes_ammo, lignes_liq = _lignes_couloirs_internes(zone, largeur, hauteur, avec_liquides)
    places = []

    shields = [s for s in soin_blocs if s.kind == "shield" or s.id == "force-projector"]
    if shields and largeur > 20 and hauteur > 20:
        sh_proto = next(iter(shields))
        w, h, r = sh_proto.largeur, sh_proto.hauteur, sh_proto.portee
        protegees = set()
        while len(protegees) < math.ceil(0.85 * len(tourelles_placees)) and len(tourelles_placees) > 25:
            best_pos, best_score = None, 0.0
            for y in range(iy_min, iy_max - h + 1):
                if any((y + dy) in lignes_ammo or (y + dy) in lignes_liq for dy in range(h)):
                    continue
                if avec_liquides and lignes_liq and _couloir_proche(sh_proto, y, lignes_liq) == -1:
                    continue
                for x in range(ix_min, ix_max - w + 1, 2):
                    if any(grille.cellules[y + dy][x + dx] is not None and grille.cellules[y + dy][x + dx].type != "turret" for dy in range(h) for dx in range(w)):
                        continue
                    cx, cy = x + w / 2.0, y + h / 2.0
                    cov = {id(t) for t in tourelles_placees if math.hypot((t.x + t.largeur / 2.0) - cx, (t.y + t.hauteur / 2.0) - cy) <= r}
                    nouv = [t for t in tourelles_placees if id(t) in (cov - protegees)]
                    score = sum(100.0 / (t.y + 5.0) for t in nouv)
                    if score > best_score:
                        best_score, best_pos = score, (x, y)
            if best_pos is None or best_score <= 0:
                break
            bx, by = best_pos
            grille.liberer_zone(bx, by, w, h, tourelles_placees)
            sh = deepcopy(sh_proto)
            grille.placer(sh, bx, by)
            places.append(sh)
            protegees = {id(t) for t in tourelles_placees if any(math.hypot((t.x + t.largeur / 2.0) - (p.x + p.largeur / 2.0), (t.y + t.hauteur / 2.0) - (p.y + p.hauteur / 2.0)) <= p.portee for p in places if p.id == sh_proto.id)}

    overdrives = sorted([s for s in soin_blocs if s.kind == "overdrive" or "overdrive" in s.id], key=lambda s: -s.speed_boost)
    if overdrives and largeur > 14 and hauteur > 14 and len(tourelles_placees) > 25:
        od_proto = next(iter(overdrives))
        w, h, r, mult = od_proto.largeur, od_proto.hauteur, od_proto.portee, (od_proto.speed_boost - 1.0)
        boostees = set()
        while len(boostees) < math.ceil(0.80 * len(tourelles_placees)) and len(tourelles_placees) > 25:
            best_pos, best_gain, best_cov = None, 0.0, set()
            for y in range(iy_min, iy_max - h + 1):
                if any((y + dy) in lignes_ammo or (y + dy) in lignes_liq for dy in range(h)):
                    continue
                for x in range(ix_min, ix_max - w + 1, 2):
                    if any(grille.cellules[y + dy][x + dx] is not None and grille.cellules[y + dy][x + dx].type != "turret" for dy in range(h) for dx in range(w)):
                        continue
                    cx, cy = x + w / 2.0, y + h / 2.0
                    victimes = [t for t in tourelles_placees if not (t.x + t.largeur <= x or t.x >= x + w or t.y + t.hauteur <= y or t.y >= y + h)]
                    perte = sum(t.dps_reel for t in victimes)
                    cov = {id(t) for t in tourelles_placees if t not in victimes and math.hypot((t.x + t.largeur / 2.0) - cx, (t.y + t.hauteur / 2.0) - cy) <= r}
                    gain = sum(t.dps_reel * mult for t in tourelles_placees if id(t) in (cov - boostees) and peut_couvrir_cible(t, t.x, t.y, y_cible_min)) - perte
                    if gain > best_gain:
                        best_gain, best_pos, best_cov = gain, (x, y), cov
            if best_pos is None or best_gain <= 50.0:
                break
            bx, by = best_pos
            grille.liberer_zone(bx, by, w, h, tourelles_placees)
            od = deepcopy(od_proto)
            grille.placer(od, bx, by)
            places.append(od)
            boostees |= best_cov
    return places


def phase3_optimisation_dps(grille: Grille, tourelles: list, soin_blocs: list,
                            zone: Tuple[int, int, int, int], largeur: int,
                            hauteur: int, y_cible_min: int, cap_dispo: set,
                            ammo_dispo: set, ratio_aa: float = 0.15):
    avec_liq = "liquids" in cap_dispo
    _, _, y_min, _ = zone
    top_2_ammo, tourelles_top2 = selectionner_top_2_munitions(tourelles, ammo_dispo, y_cible_min, y_min + 1)
    tourelles_placees = remplir_glouton_stratifie(grille, tourelles_top2, zone, y_cible_min, avec_liq, ratio_aa)
    _placer_boucliers_et_accelerants(
        grille, tourelles_placees, soin_blocs, zone, largeur, hauteur, y_cible_min, avec_liq
    )
    score_global = sum(t.dps_reel for t in tourelles_placees)
    return grille, tourelles_placees, tourelles_top2, top_2_ammo, score_global


def _placer_tampons_crise(grille: Grille, tourelles_placees: list, zone: Tuple[int, int, int, int],
                          lignes_ammo: set, lignes_liq: set, logistique_blocs: list,
                          liquides_blocs: list, avec_liquides: bool, top_2_ammo: List[str]) -> Tuple[list, set]:
    nb = len(tourelles_placees)
    if nb < 25 or grille.largeur <= 16 or grille.hauteur <= 16:
        return [], set()
    x_min, x_max, y_min, y_max = zone
    cx = (x_min + x_max) // 2
    places, couloirs_stockage = [], set()

    v_proto  = next((b for b in logistique_blocs if b.id == "vault"), None)
    c_proto  = next((b for b in logistique_blocs if b.id == "container"), None)
    u_proto  = next((b for b in logistique_blocs if b.id == "unloader"), None)
    l_conv   = next((b for b in logistique_blocs if b.kind == "conveyor"), None)
    tk_proto = next((b for b in liquides_blocs if b.id == "liquid-tank"), None)
    lc_proto = next((b for b in liquides_blocs if b.id == "liquid-container"), tk_proto)

    st_item = v_proto if (nb > 50 and v_proto) else c_proto
    st_liq  = tk_proto if (nb > 50 and tk_proto) else lc_proto
    if not st_item:
        return [], set()
    w, h = st_item.largeur, st_item.hauteur

    if nb <= 70:
        l_ammo_int = sorted(y for y in lignes_ammo if y_min < y < y_max - 2) or sorted(lignes_ammo)
        ya = next(islice(l_ammo_int, len(l_ammo_int) // 2, len(l_ammo_int) // 2 + 1))
        ty = ya + 1 if (ya + 1 + h < y_max - 2) else ya - h
        xa = cx - w
        configs_pos = [(xa, ty, xa + w, ty, ya, True)]
    else:
        y_haut = y_min + 1
        y_ammo_bas = max(y for y in lignes_ammo if y < y_max - 1)
        y_bas = y_ammo_bas + 1
        configs_pos = [
            (x_min + 3 + w, y_haut, x_min + 3, y_haut, y_min, False),
            (x_max - 4 - 2 * w, y_haut, x_max - 4 - w, y_haut, y_min, True),
            (x_min + 3 + w, y_bas, x_min + 3, y_bas, y_ammo_bas, False),
            (x_max - 4 - 2 * w, y_bas, x_max - 4 - w, y_bas, y_ammo_bas, True),
        ]

    for vx, vy, tx, ty, yc_proche, unl_gauche in configs_pos:
        couloirs_stockage.add(yc_proche)
        ux = vx - 1 if unl_gauche else vx + w
        cx_ret = vx - 2 if unl_gauche else vx + w + 1
        x_deb_z, x_fin_z = min(vx, tx, ux, cx_ret), max(vx + w, tx + w, ux + 1, cx_ret + 1)
        grille.liberer_zone(x_deb_z, vy, x_fin_z - x_deb_z, h, tourelles_placees)
        it_b = deepcopy(st_item)
        it_b.kind = "storage"
        grille.placer(it_b, vx, vy)
        places.append(it_b)
        if avec_liquides and st_liq:
            lq_b = deepcopy(st_liq)
            lq_b.kind = "storage"
            grille.placer(lq_b, tx, ty)
            places.append(lq_b)
        if u_proto and l_conv and top_2_ammo:
            for idx_a, am_cfg in enumerate(islice(top_2_ammo, 0, min(2, h))):
                uy = vy + idx_a
                un = deepcopy(u_proto)
                un.kind = "storage_io"
                un.rotation = 1
                un.best_ammo = am_cfg
                grille.placer(un, ux, uy)
                places.append(un)
                if idx_a == 1:
                    for ry in (vy + 1, vy):
                        cv = deepcopy(l_conv)
                        cv.kind = "storage_io"
                        cv.rotation = 1
                        grille.placer(cv, cx_ret, ry)
                        places.append(cv)
    return places, couloirs_stockage


# ─────────────────────────────────────────────────────────────────────────────
# BLOC 6 / 8 : Ponts Paires Garanties, Distributeurs & Réseau Électrique Connexe
# ─────────────────────────────────────────────────────────────────────────────

def _couloir_a_besoin_ammo(grille: Grille, y_c: int, x_min: int, x_max: int,
                           top_2_ammo: List[str] = None) -> str:
    touche_stockage = False
    for x in range(x_min + 1, x_max - 1):
        for ny in (y_c - 1, y_c + 1):
            if 0 <= ny < grille.hauteur:
                c = grille.cellules[ny][x]
                if c is not None:
                    if c.type == "turret" and c.best_ammo and c.best_ammo != "power":
                        return c.best_ammo
                    if c.kind in ("storage", "storage_io"):
                        touche_stockage = True
    if touche_stockage and top_2_ammo:
        return next(iter(top_2_ammo), "")
    return ""


def _choisir_distributeurs(blocs_dispo: list, kind_base: str):
    lignes = [b for b in blocs_dispo if b.kind == kind_base]
    principal = next(iter(lignes), next(iter(blocs_dispo), None))
    trieur_entree = next((b for b in blocs_dispo if b.id == "sorter"), principal)
    repartiteur = (
        next((b for b in blocs_dispo if b.id == "underflow-gate"), None)
        or next((b for b in blocs_dispo if b.id == "liquid-router"), None)
        or next((b for b in blocs_dispo if b.kind in ("gate", "router")), principal)
    )
    router_bloc = (
        next((b for b in blocs_dispo if b.id in ("router", "liquid-router")), None)
        or next((b for b in blocs_dispo if b.kind == "router"), principal)
    )
    ponts = [b for b in blocs_dispo if b.kind == "bridge" or "bridge" in b.id.lower()]
    ponts.sort(key=lambda b: -b.vitesse_transport)
    pont = next(iter(ponts), None)
    return principal, trieur_entree, repartiteur, router_bloc, pont


def _densifier_par_ponts(grille: Grille, lignes_c: set, x_deb: int, x_fin: int,
                         pont_proto: Bloc, places: list):
    if pont_proto is None or x_deb >= x_fin:
        return
    for yc in sorted(lignes_c):
        rot_l = 2
        for xs in range(x_deb, x_fin + 1):
            cs = grille.cellules[yc][xs]
            if cs is not None and cs.kind in ("conveyor", "conduit") and cs.rotation in (0, 2):
                rot_l = cs.rotation
                break
        if rot_l == 2:
            x = x_fin
            while x - 1 >= x_deb:
                c1, c2 = grille.cellules[yc][x], grille.cellules[yc][x - 1]
                if (c1 and c2 and c1.kind in ("conveyor", "conduit") and c2.kind == c1.kind and
                        c1.rotation == 2 and c2.rotation == 2):
                    grille.retirer(c1)
                    grille.retirer(c2)
                    if c1 in places: places.remove(c1)
                    if c2 in places: places.remove(c2)
                    p_a, p_b = deepcopy(pont_proto), deepcopy(pont_proto)
                    p_a.rotation = p_b.rotation = 2
                    grille.placer(p_a, x, yc)
                    grille.placer(p_b, x - 1, yc)
                    places.extend([p_a, p_b])
                    x -= 2
                else:
                    x -= 1
        else:
            x = x_deb
            while x + 1 <= x_fin:
                c1, c2 = grille.cellules[yc][x], grille.cellules[yc][x + 1]
                if (c1 and c2 and c1.kind in ("conveyor", "conduit") and c2.kind == c1.kind and
                        c1.rotation == 0 and c2.rotation == 0):
                    grille.retirer(c1)
                    grille.retirer(c2)
                    if c1 in places: places.remove(c1)
                    if c2 in places: places.remove(c2)
                    p_a, p_b = deepcopy(pont_proto), deepcopy(pont_proto)
                    p_a.rotation = p_b.rotation = 0
                    grille.placer(p_a, x, yc)
                    grille.placer(p_b, x + 1, yc)
                    places.extend([p_a, p_b])
                    x += 2
                else:
                    x += 1


def _densifier_colonnes_par_ponts(grille: Grille, cols_x: list, y_deb: int, y_fin: int,
                                  pont_proto: Bloc, places: list):
    if pont_proto is None or y_deb >= y_fin:
        return
    for xc in cols_x:
        y = y_deb
        while y + 1 <= y_fin:
            c1, c2 = grille.cellules[y][xc], grille.cellules[y + 1][xc]
            if (c1 and c2 and c1.kind in ("conveyor", "conduit") and c2.kind == c1.kind and
                    c1.rotation == 3 and c2.rotation == 3):
                grille.retirer(c1)
                grille.retirer(c2)
                if c1 in places: places.remove(c1)
                if c2 in places: places.remove(c2)
                p_a, p_b = deepcopy(pont_proto), deepcopy(pont_proto)
                p_a.rotation = p_b.rotation = 3
                grille.placer(p_a, xc, y)
                grille.placer(p_b, xc, y + 1)
                places.extend([p_a, p_b])
                y += 2
            else:
                y += 1


def _placer_energie_connectee(grille: Grille, energie_blocs: list,
                              zone: Tuple[int, int, int, int], tourelles_placees: list,
                              lignes_interdites: set) -> list:
    nodes_cand = [e for e in energie_blocs if e.id == "power-node" or "node" in e.id]
    if not nodes_cand:
        return []
    e_proto = next(iter(nodes_cand))
    r_laser = getattr(e_proto, "laser_range", 6.0) or 6.0
    x_min, x_max, y_min, y_max = zone

    def poser_node(nx: int, ny: int, autoriser_remplacement_1x1: bool = False):
        if ny in lignes_interdites or not (x_min + 3 <= nx < x_max - 4 and y_min < ny < y_max - 1):
            return None
        if grille.peut_placer(e_proto, nx, ny):
            n = deepcopy(e_proto)
            grille.placer(n, nx, ny)
            return n
        if autoriser_remplacement_1x1:
            ex = grille.cellules[ny][nx]
            if ex is not None and ex.type == "turret" and ex.largeur == 1 and ex.hauteur == 1:
                grille.retirer(ex)
                if ex in tourelles_placees:
                    tourelles_placees.remove(ex)
                n = deepcopy(e_proto)
                grille.placer(n, nx, ny)
                return n
        return None

    cibles, vus = [], set()
    for y in range(grille.hauteur):
        for x in range(grille.largeur):
            b = grille.cellules[y][x]
            if b is not None and id(b) not in vus and (b.consomme_energie or b.type == "soin"):
                vus.add(id(b))
                cibles.append(b)

    noeuds_places = []
    for cb in cibles:
        cx, cy = cb.x + cb.largeur / 2.0, cb.y + cb.hauteur / 2.0
        if not any(math.hypot((n.x + 0.5) - cx, (n.y + 0.5) - cy) <= r_laser for n in noeuds_places):
            for remp in (False, True):
                place = False
                for ny in range(max(y_min + 1, cb.y - 3), min(y_max - 1, cb.y + cb.hauteur + 3)):
                    for nx in range(max(x_min + 3, cb.x - 3), min(x_max - 4, cb.x + cb.largeur + 3)):
                        if math.hypot((nx + 0.5) - cx, (ny + 0.5) - cy) <= r_laser:
                            n = poser_node(nx, ny, remp)
                            if n:
                                noeuds_places.append(n)
                                place = True
                                break
                    if place:
                        break
                if place:
                    break

    for _ in range(30):
        if len(noeuds_places) <= 1:
            break
        adj = {i: [] for i in range(len(noeuds_places))}
        for i, n1 in enumerate(noeuds_places):
            for j, n2 in enumerate(noeuds_places):
                if i < j and math.hypot(n1.x - n2.x, n1.y - n2.y) <= r_laser:
                    adj[i].append(j)
                    adj[j].append(i)
        vis, comps = set(), []
        for i in range(len(noeuds_places)):
            if i not in vis:
                comp, q = [], [i]
                vis.add(i)
                while q:
                    curr = q.pop(0)
                    comp.append(curr)
                    for nb in adj[curr]:
                        if nb not in vis:
                            vis.add(nb)
                            q.append(nb)
                comps.append(comp)
        if len(comps) <= 1:
            break
        best_d, best_pair = 999999.0, None
        c_first = next(iter(comps))
        for i1 in c_first:
            for comp2 in islice(comps, 1, None):
                for i2 in comp2:
                    n1, n2 = next(islice(noeuds_places, i1, i1 + 1)), next(islice(noeuds_places, i2, i2 + 1))
                    d = math.hypot(n1.x - n2.x, n1.y - n2.y)
                    if d < best_d:
                        best_d, best_pair = d, (n1, n2)
        if best_pair is None:
            break
        n1, n2 = best_pair
        ratio = min(5.0, r_laser - 0.5) / max(best_d, 1.0)
        tx, ty = int(round(n1.x + (n2.x - n1.x) * ratio)), int(round(n1.y + (n2.y - n1.y) * ratio))
        relais = None
        for remp in (False, True):
            for dy in (0, -1, 1, -2, 2):
                for dx in (0, -1, 1, -2, 2):
                    rx, ry = tx + dx, ty + dy
                    if math.hypot(rx - n1.x, ry - n1.y) <= r_laser:
                        relais = poser_node(rx, ry, remp)
                        if relais:
                            break
                if relais:
                    break
            if relais:
                break
        if relais:
            noeuds_places.append(relais)
        else:
            break
    return noeuds_places


# ─────────────────────────────────────────────────────────────────────────────
# BLOC 7 / 8 : Phase 4 Infrastructure (Sauts Droite->Gauche & Parité Paire)
# ─────────────────────────────────────────────────────────────────────────────

def phase4_infrastructure(grille: Grille, tourelles_placees: list, tourelles_dispo: list,
                          logistique_blocs: list, liquides_blocs: list, energie_blocs: list,
                          zone: Tuple[int, int, int, int], largeur: int, hauteur: int,
                          y_cible_min: int, cap_dispo: set, top_2_ammo: List[str],
                          ratio_aa: float = 0.15):
    x_min, x_max, y_min, y_max = zone
    avec_liq = "liquids" in cap_dispo and bool(liquides_blocs)
    lignes_ammo, lignes_liq = _lignes_couloirs_internes(zone, largeur, hauteur, avec_liq)
    blocs_infra = []

    tampons, couloirs_stockage = _placer_tampons_crise(
        grille, tourelles_placees, zone, lignes_ammo, lignes_liq,
        logistique_blocs, liquides_blocs, avec_liq, top_2_ammo
    )
    blocs_infra += tampons

    couloirs_ammo_actifs = {y_min, y_max - 1} | set(couloirs_stockage)
    ammo_par_yc = {}
    for yc in sorted(lignes_ammo - {y_max - 1}):
        am = _couloir_a_besoin_ammo(grille, yc, x_min, x_max, top_2_ammo)
        if am:
            couloirs_ammo_actifs.add(yc)
            ammo_par_yc[yc] = am

    if "energy" in cap_dispo and energie_blocs:
        blocs_infra += _placer_energie_connectee(
            grille, energie_blocs, zone, tourelles_placees, couloirs_ammo_actifs | lignes_liq
        )

    # Fix 3 : Combler les cases vides restantes en maintenant dynamiquement le quota Anti-Air (ratio_aa)
    ix_min, ix_max, iy_min, iy_max = _zone_interieure_tourelles(zone, largeur, hauteur, avec_liq)
    t_aa_fill  = sorted([t for t in tourelles_dispo if t.targets_air], key=lambda t: (-t.dps_par_surface, -t.portee))
    t_sol_fill = sorted([t for t in tourelles_dispo if not t.targets_air], key=lambda t: (-t.dps_par_surface, -t.portee))

    for y in range(iy_min, iy_max):
        if y in couloirs_ammo_actifs or y in lignes_liq:
            continue
        for x in range(ix_min, ix_max):
            if grille.cellules[y][x] is not None:
                continue
            nb_aa_cur = sum(1 for t in tourelles_placees if t.targets_air)
            besoin_aa = bool(t_aa_fill) and ((nb_aa_cur / max(1, len(tourelles_placees) + 1)) < ratio_aa)
            listes_cand = (t_aa_fill + t_sol_fill) if besoin_aa else (t_sol_fill + t_aa_fill)
            for tp in listes_cand:
                if x + tp.largeur > ix_max or y + tp.hauteur > iy_max:
                    continue
                if not peut_couvrir_cible(tp, x, y, y_cible_min):
                    continue
                if any((y + dy) in couloirs_ammo_actifs or (y + dy) in lignes_liq for dy in range(tp.hauteur)):
                    continue
                if tp.best_ammo and tp.best_ammo != "power":
                    yc_a = _couloir_proche(tp, y, couloirs_ammo_actifs)
                    if yc_a == -1:
                        continue
                    if yc_a not in couloirs_stockage and yc_a in ammo_par_yc and ammo_par_yc[yc_a] != tp.best_ammo:
                        continue
                if grille.peut_placer(tp, x, y):
                    nt = deepcopy(tp)
                    grille.placer(nt, x, y)
                    tourelles_placees.append(nt)
                    break

    l_conv, sorter_b, gate_b, router_b, pont_b = _choisir_distributeurs(logistique_blocs, "conveyor")
    multi_ammo = len(set(ammo_par_yc.values())) > 1 or len(top_2_ammo) > 1

    def poser(x: int, y: int, proto: Bloc, rot: int, cfg: str = "", k_override: str = ""):
        if proto is None or not (0 <= x < largeur and 0 <= y < hauteur):
            return
        ex = grille.cellules[y][x]
        if ex is not None and (ex.type in ("turret", "soin", "energie") or ex.kind in ("storage", "storage_io", "bridge_io")):
            return
        if ex is not None:
            if ex in blocs_infra:
                blocs_infra.remove(ex)
            grille.retirer(ex)
        b = deepcopy(proto)
        b.rotation = rot
        b.best_ammo = cfg
        if k_override:
            b.kind = k_override
        grille.placer(b, x, y)
        blocs_infra.append(b)

    # 1. Peigne Liquides continu (sans aucun pont vertical sur x_min+2 ni x_max-4)
    if avec_liq and lignes_liq:
        lq_cond, _, lq_rout, _, pont_lq = _choisir_distributeurs(liquides_blocs, "conduit")
        p_l = pont_lq if pont_lq else pont_b
        y_liq_bas, y_liq_haut = max(lignes_liq), min(lignes_liq)
        x_liq_g, x_liq_d = x_min + 2, x_max - 4

        for y in range(y_liq_bas, y_liq_haut - 1, -1):
            poser(x_liq_d, y, lq_rout if y in lignes_liq else lq_cond, 1)
            poser(x_liq_g, y, lq_rout if y in lignes_liq else lq_cond, 3)
        for yl in sorted(lignes_liq):
            rot_l = 0 if (yl == y_liq_bas and len(lignes_liq) > 1) else 2
            for x in range(x_liq_d - 1, x_liq_g, -1):
                poser(x, yl, lq_cond, rot_l)
        poser(x_liq_g, y_liq_bas, lq_rout, 0)

        if hauteur > y_max and p_l:
            poser(x_max - 3, hauteur - 1, p_l, 1, "", "bridge_io")
            poser(x_max - 3, y_liq_bas, p_l, 1, "", "bridge_io")
            poser(x_liq_d, y_liq_bas, lq_rout, 1, "", "bridge_io")

        _densifier_par_ponts(grille, lignes_liq - {y_liq_bas}, x_liq_g + 1, x_liq_d - 1, pont_lq, blocs_infra)
        _densifier_par_ponts(grille, {y_liq_bas}, x_liq_g + 1, x_liq_d - 1, pont_lq, blocs_infra)

    # 2. Peigne Munitions : Sauts horizontaux (rot=2) par-dessus x_liq_d et x_liq_g, Fix A sur couloirs_stockage
    if l_conv:
        for y in range(y_max - 1, y_min, -1):
            poser(x_max - 1, y, gate_b if (y in couloirs_ammo_actifs and y != y_max - 1) else l_conv, 1)
        poser(x_max - 1, y_min, l_conv, 2)

        for y in range(y_min, y_max - 1):
            poser(x_min, y, l_conv, 3, "", "storage_io" if (y in couloirs_ammo_actifs or (y - 1) in couloirs_ammo_actifs) else "")
        for x in range(x_min, x_max - 1):
            poser(x, y_max - 1, l_conv, 0)

        for yc in sorted(couloirs_ammo_actifs - {y_max - 1}):
            filtrer_yc = (yc != y_min and yc not in couloirs_stockage and multi_ammo and yc in ammo_par_yc)
            if avec_liq and pont_b and yc >= min(lignes_liq):
                poser(x_max - 2, yc, sorter_b if filtrer_yc else l_conv, 2, ammo_par_yc.get(yc, "") if filtrer_yc else "", "storage_io")
                poser(x_max - 3, yc, pont_b, 2, "", "bridge_io")
                poser(x_max - 5, yc, pont_b, 2, "", "bridge_io")
                for x in range(x_max - 6, x_min + 3, -1):
                    poser(x, yc, l_conv, 2)
                poser(x_min + 3, yc, pont_b, 2, "", "bridge_io")
                poser(x_min + 1, yc, pont_b, 2, "", "bridge_io")
                _densifier_par_ponts(grille, {yc}, x_min + 4, x_max - 6, pont_b, blocs_infra)
            else:
                for x in range(x_max - 2, x_min, -1):
                    poser(x, yc, l_conv, 2)
                if filtrer_yc:
                    poser(x_max - 2, yc, sorter_b, 2, ammo_par_yc[yc], "storage_io")
                _densifier_par_ponts(grille, {yc}, x_min + 1, x_max - 1 if yc == y_min else x_max - 3, pont_b, blocs_infra)

        _densifier_par_ponts(grille, {y_max - 1}, x_min + 1, x_max - 3, pont_b, blocs_infra)
        _densifier_colonnes_par_ponts(grille, [x_min], y_min + 1, y_max - 2, pont_b, blocs_infra)

        if hauteur > y_max and pont_b:
            poser(x_max - 1, hauteur - 1, pont_b, 1, "", "bridge_io")
            poser(x_max - 1, y_max - 1, pont_b, 1, "", "bridge_io")

    return blocs_infra, l_conv


# ─────────────────────────────────────────────────────────────────────────────
# BLOC 8 / 8 : Phases 6, 7 (Murs Sans Trou), 8 (5 Rapports), --anti-air & Main
# ─────────────────────────────────────────────────────────────────────────────

def calculer_besoin_munitions(tourelles_placees: list) -> float:
    return sum(max(0.2, min(t.rate, 3.0) * 0.4) for t in tourelles_placees if t.best_ammo != "power")


def evaluer_viabilite_approvisionnement(tourelles_placees: list, logistique_bloc: Bloc,
                                        largeur: int, hauteur: int) -> float:
    if not logistique_bloc or not tourelles_placees:
        return 1.0
    vitesse = logistique_bloc.vitesse_transport or 4.2
    capacite_reseau = vitesse * ((largeur + hauteur) * 1.5)
    besoin = calculer_besoin_munitions(tourelles_placees)
    return min(capacite_reseau / max(besoin, 0.1), 1.0)


def phase6_logistique_finale(grille: Grille, tourelles_placees: list, blocs_infra: list,
                             l_best: Bloc, largeur: int, hauteur: int):
    vus = set()
    tourelles_reelles = []
    for y in range(grille.hauteur):
        for x in range(grille.largeur):
            b = grille.cellules[y][x]
            if b is not None and b.type == "turret" and id(b) not in vus:
                vus.add(id(b))
                tourelles_reelles.append(b)
    tourelles_placees[:] = tourelles_reelles
    facteur_reel = evaluer_viabilite_approvisionnement(tourelles_placees, l_best, largeur, hauteur)
    score_global = sum(t.dps_reel for t in tourelles_placees)
    return score_global, facteur_reel, blocs_infra


def phase7_protection_compaction(grille: Grille, protection_blocs: list,
                                 zone: Tuple[int, int, int, int], largeur: int,
                                 hauteur: int, no_wall: bool, mat_dispo: set, cap_dispo: set) -> list:
    if no_wall:
        return []
    x_min, x_max, y_min, y_max = zone
    blocs_protection = []
    murs_fab = [b for b in protection_blocs if fabricable(b, mat_dispo, cap_dispo)]
    for m_proto in murs_fab:
        w, h = m_proto.largeur, m_proto.hauteur
        for y in range(0, hauteur - h + 1):
            for x in range(0, largeur - w + 1):
                dans_couronne = (
                    (y + h <= y_min) or (y >= y_max) or
                    (x + w <= x_min) or (x >= x_max)
                )
                if dans_couronne and grille.peut_placer(m_proto, x, y):
                    m = deepcopy(m_proto)
                    grille.placer(m, x, y)
                    blocs_protection.append(m)
    return blocs_protection


def phase8_generer_fichiers(grille: Grille, sortie_dir: str = "."):
    os.makedirs(sortie_dir, exist_ok=True)
    legend, char_for_key = {}, {}
    char_iter = iter(CHAR_RESERVOIR)

    uniques, vus = [], set()
    for y in range(grille.hauteur):
        for x in range(grille.largeur):
            b = grille.cellules[y][x]
            if b is not None and id(b) not in vus:
                vus.add(id(b))
                uniques.append(b)

    for b in uniques:
        cfg = b.best_ammo if (b.id in ("sorter", "inverted-sorter", "unloader") and getattr(b, "best_ammo", "")) else ""
        cle = (b.id, b.rotation, cfg)
        if cle not in char_for_key:
            char_for_key[cle] = next(char_iter, "?")
        b.char = char_for_key[cle]
        entry = {"id": b.id, "width": b.largeur, "height": b.hauteur, "rotation": b.rotation}
        if cfg:
            entry["config"] = cfg
        legend[b.char] = entry

    schema = [[' ' for _ in range(grille.largeur)] for _ in range(grille.hauteur)]
    for b in uniques:
        schema[b.y][b.x] = b.char
        for dy in range(b.hauteur):
            for dx in range(b.largeur):
                if (dy != 0 or dx != 0) and 0 <= b.y + dy < grille.hauteur and 0 <= b.x + dx < grille.largeur:
                    schema[b.y + dy][b.x + dx] = '*'

    schema_txt = "\n".join("".join(row) for row in schema)
    with open(os.path.join(sortie_dir, "schema.txt"), "w", encoding="utf-8") as f:
        f.write(schema_txt)
    with open(os.path.join(sortie_dir, "legend.json"), "w", encoding="utf-8") as f:
        json.dump(legend, f, ensure_ascii=False, indent=2)

    dps_rep = {
        "score_global": sum(b.dps_reel for b in uniques if b.type == "turret"),
        "dps_par_taille": sum((b.dps_par_taille for b in uniques if b.type == "turret"), 0.0),
        "dps_par_cout": sum((b.dps_par_cout for b in uniques if b.type == "turret"), 0.0),
        "tourelles": [b.id for b in uniques if b.type == "turret"],
    }
    with open(os.path.join(sortie_dir, "dps_report.txt"), "w", encoding="utf-8") as f:
        json.dump(dps_rep, f, ensure_ascii=False, indent=2)

    infra_rep = {
        "logistique": [b.id for b in uniques if b.type == "logistique"],
        "liquides":   [b.id for b in uniques if b.type == "liquide"],
        "energie":    [b.id for b in uniques if b.type == "energie"],
        "protection": [b.id for b in uniques if b.type == "protection"],
        "soin":       [b.id for b in uniques if b.type == "soin"],
    }
    with open(os.path.join(sortie_dir, "infrastructure_report.txt"), "w", encoding="utf-8") as f:
        json.dump(infra_rep, f, ensure_ascii=False, indent=2)

    val_rep = {
        "nb_tourelles": len([b for b in uniques if b.type == "turret"]),
        "nb_tourelles_anti_air": len([b for b in uniques if b.type == "turret" and b.targets_air]),
        "nb_infra": len([b for b in uniques if b.type != "turret"]),
        "surface_blocs": sum(b.taille() for b in uniques),
    }
    with open(os.path.join(sortie_dir, "validation_report.txt"), "w", encoding="utf-8") as f:
        json.dump(val_rep, f, ensure_ascii=False, indent=2)

    return legend, schema_txt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("largeur", type=int)
    parser.add_argument("hauteur", type=int)
    parser.add_argument("ressources", nargs="+")
    parser.add_argument("--data", default=None)
    parser.add_argument("--no-wall", action="store_true")
    parser.add_argument("--duree", type=float, default=30.0)
    parser.add_argument("--anti-air", type=float, default=15.0)
    parser.add_argument("--out", default=".")
    parser.add_argument("--ammo", nargs="*", default=[])
    args = parser.parse_args()

    largeur, hauteur, ressources = args.largeur, args.hauteur, args.ressources
    ammo_dispo = set(args.ammo) if args.ammo else set()
    data_path = ressources.pop() if (ressources and ressources[-1].lower().endswith(".json")) else args.data
    ratio_aa = max(0.0, min(100.0, args.anti_air)) / 100.0

    mat_dispo, cap_dispo = phase0_validation(largeur, hauteur, ressources, data_path)
    tourelles, logistique, liquides, protection, energie, soin = phase1_chargement(data_path, mat_dispo, cap_dispo, ammo_dispo)
    phase2_ciblage(tourelles, largeur, hauteur)
    zone, _, _ = calculer_zone_tourelles(largeur, hauteur, args.no_wall)

    grille = Grille(largeur, hauteur)
    y_cible_min = -2

    placer_soin_minimal_avant(grille, soin, zone, largeur, hauteur, args.no_wall, "liquids" in cap_dispo)
    grille, tourelles_placees, tourelles_top2, top_2_ammo, _ = phase3_optimisation_dps(
        grille, tourelles, soin, zone, largeur, hauteur, y_cible_min, cap_dispo, ammo_dispo, ratio_aa
    )
    blocs_infra, l_best = phase4_infrastructure(
        grille, tourelles_placees, tourelles_top2, logistique, liquides, energie, zone, largeur, hauteur, y_cible_min, cap_dispo, top_2_ammo, ratio_aa
    )
    score_global, facteur_reel, _ = phase6_logistique_finale(grille, tourelles_placees, blocs_infra, l_best, largeur, hauteur)
    phase7_protection_compaction(grille, protection, zone, largeur, hauteur, args.no_wall, mat_dispo, cap_dispo)
    phase8_generer_fichiers(grille, args.out)
    nb_aa = sum(1 for t in tourelles_placees if t.targets_air)
    pct_aa = (100.0 * nb_aa / max(1, len(tourelles_placees)))
    print(f"\n[OK V9.6] Tourelles: {len(tourelles_placees)} | Anti-Air Pur: {pct_aa:.0f}% | Top2 Ammo: {top_2_ammo} | DPS: {score_global:.0f}")


if __name__ == "__main__":
    main()

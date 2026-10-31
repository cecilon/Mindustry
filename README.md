# 🧠 Gemini_Intelligence_Mindustry.md — Référentiel Algorithmique & Règles Métier (v9.6)

Ce document constitue la **source de vérité unique** du générateur de complexes de tourelles Mindustry (`turret_complex.py`, `ascii_to_tiles.py`, `data.json`). Toute modification du code doit respecter 100 % des règles ci-dessous sans jamais créer de régression.

---

## 1. Constantes & Physique Officielle Mindustry v7 (`Blocks.java`)
Dans le moteur interne de Mindustry, `1 bloc (tile) = 8 unités-monde`. Toutes les portées et dimensions dans `data.json` et `turret_complex.py` sont exprimées en **blocs exacts** (`range_interne / 8`).

### 1.1 Dimensions et Portées Exactes des Tourelles Offensives
* **1x1** : `duo` (portée `20.0`), `scorch` (`7.5`), `hail` (`29.375`), `arc` (`11.25`, électrique).
* **2x2** : `scatter` (`22.5`, Anti-Air pur), `wave` (`13.75`, liquide), `lancer` (`20.625`, électrique), `salvo` (`19.0`), `swarmer` (`30.0`), `parallax` (`28.75`, Anti-Air pur, électrique).
* **3x3** : `ripple` (`36.25`), `cyclone` (`25.0`), `fuse` (`11.25`), `tsunami` (`23.75`, liquide).
* **4x4** : `spectre` (`32.5`), `meltdown` (`24.375`, électrique + liquide obligatoire), `foreshadow` (`62.5`, électrique + `surge-alloy` obligatoire en coût de construction `cost_surge-alloy: 300`, `cost_plastanium: 200` et en munition).

### 1.2 Portées Boostées au Tissu Phasé (`range_phase_boost`) des Blocs de Soutien
Les calculs de couverture utilisent obligatoirement la **portée boostée par la ressource Tissu Phasé (`phase-fabric`)** :
* `mender` (Gardien, `1x1`) : base `5.0` → boostée **`8.5`**.
* `mend-projector` (Projecteur soignant, `2x2`) : base `10.0` → boostée **`16.25`**.
* `force-projector` (Projecteur de champ de force, `3x3`) : base `12.7` → boostée **`17.7`**.
* `overdrive-projector` (Projecteur accélérant, `2x2`, requiert `plastanium`) : base `10.0` → boostée **`16.875`** (vitesse `2.25x`).
* `overdrive-dome` (Dôme accélérant, `3x3`, requiert `plastanium` + `surge-alloy`) : **`10.625`** (vitesse `2.5x`).

---

## 2. Pipeline Algorithmique Phase par Phase

### Phase 0 & Phase 1 : Validation, Alias & Chargement (`phase0_validation`, `phase1_chargement`)
1. **Normalisation des ressources :** Correction automatique des fautes de frappe courantes en entrée (`plastinum` / `plastinium` → `plastanium`).
2. **Filtrage strict de fabricabilité :** Un bloc n'est retenu que si **100 % de ses `cost_<ressource>`** et de ses capacités (`energy`, `liquids`) figurent dans les ressources passées en paramètre.
3. **Définition stricte de l'Anti-Air Pur :**
   * Une tourelle qui peut cibler les unités au sol (`targets_ground == True`) **n'est PAS comptée comme anti-aérienne**.
   * Seules les tourelles **exclusivement anti-aériennes** (`targets_air == True` et `targets_ground == False`, soit `scatter` et `parallax`) comptent dans le quota `--anti-air`.

### Phase 2 : Ciblage & Géométrie des Couloirs (`phase2_ciblage`, `_lignes_couloirs_internes`)
1. **Ligne cible à 2 cases devant le complexe :**
   * La ligne cible est fixée à **`y_cible_min = -2`** (soit 2 cases à l'extérieur devant le mur avant `y = 0`).
   * Une tourelle posée en `y` couvre la cible si `portee >= (y + hauteur / 2.0) - (-2)`.
2. **Couronne de murs :** Épaisseur de `2` cases sur les 4 faces (`x_min = 2`, `x_max = largeur - 2`, `y_min = 2`, `y_max = hauteur - 2`) dès que `max(largeur, hauteur) > 12`.
3. **Entrelacement des couloirs internes (`lignes_ammo` et `lignes_liq`) :**
   * En haut : `y_min` (`y = 2`, Ammo) et `y_min + 4` (`y = 6`, Liquide) encadrent une travée de **3 cases** (`y = 3..5`) idéale pour loger les `3x3` (`fuse`, `vault`, `liquid-tank`).
   * Au milieu : travées de **4 cases** (`pas = 5`) encadrées par 1 couloir Ammo et 1 couloir Liquide pour loger sans chevauchement les tourelles `4x4` (`spectre`, `meltdown`, `foreshadow`).
   * En bas : `y_max - 6` (Ammo) et `y_max - 2` (`y_liq_bas`, Liquide) encadrent une travée de **3 cases** pour les `vault` / `liquid-tank` des coins inférieurs, et `y_max - 1` est le collecteur retour bas de Munitions.

### Phase 2.5 : Couverture de Soin (`placer_soin_minimal_avant`)
* Place le nombre **minimum** de `mend-projector` / `mender` (avec leur portée boostée au tissu phasé) pour couvrir **100 % des murs avant (`y = 0..1`) ET les 14 premières lignes de murs latéraux (`y = 0..13`)** à gauche et à droite.
* Ces blocs (`type == "soin"`) sont **sanctuarisés** : aucune phase ultérieure (boucliers, accélérants, coffres, logistique) n'a le droit de les écraser.

### Phase 3 : Top 2 Munitions, Quota Anti-Air (15 %) & Stratification DPS (`phase3_optimisation_dps`)
1. **Sélection des 2 meilleures munitions (`selectionner_top_2_munitions`) :**
   * Parmi la liste `--ammo`, sélectionne au maximum les **2 munitions solides** (ou 1 seule si 1 seule fournie) qui maximisent le DPS/surface à la ligne cible `y_cible_min = -2` (l'énergie `"power"` et les liquides ne sont pas limités).
   * **Garantie Anti-Air (Fix 3) :** Si aucune tourelle anti-aérienne électrique (`parallax`) n'est fabricable, l'une des 2 munitions retenues inclut obligatoirement la meilleure munition compatible avec `scatter` (`metaglass` ou `lead`).
2. **Quota `--anti-air` (15 % par défaut) :**
   * Garantit qu'au moins **15 %** des tourelles du complexe sont des tourelles exclusivement anti-aériennes (`scatter`, `parallax`), tant lors du placement initial (`remplir_glouton_stratifie`) que lors du comblement final des trous en Phase 4.
3. **Priorité stricte de portée au fond :**
   * Interdiction de placer une tourelle qui n'atteint pas `y_cible_min = -2` tant qu'une tourelle à longue portée (`foreshadow` 62.5, `ripple` 36.25, `spectre` 32.5, `swarmer` 30.0, `hail` 29.375) peut s'y loger.
4. **Projecteurs de champ de force (`force-projector`) :**
   * Si `nb_tourelles > 25` et `largeur > 20 and hauteur > 20`, place le minimum de `force-projector` (portée `17.7`) **en contact direct avec un couloir de liquide** pour couvrir **>= 85 % des tourelles** (priorité pondérée vers l'avant).
5. **Blocs accélérants (`overdrive-projector` / `overdrive-dome`) :**
   * Si `nb_tourelles > 25` et `largeur > 14 and hauteur > 14`, place le minimum d'accélérants maximisant le gain net de DPS vers la ligne cible.

### Phase 4 : Stockages Tampons, Énergie Connexe & Double Peigne Logistique (`phase4_infrastructure`)
1. **Règles de placement des Coffres-forts / Conteneurs & Réservoirs (`_placer_tampons_crise`) :**
   * Actif si `largeur > 16 and hauteur > 16` et `nb_tourelles >= 25`.
   * **25 à 50 tourelles** : `1 container (2x2)` + `1 liquid-container (2x2)` **au centre et collés l'un à côté de l'autre**.
   * **51 à 70 tourelles** : `1 vault (3x3)` + `1 liquid-tank (3x3)` **au centre et collés l'un à côté de l'autre**.
   * **71 tourelles et plus** : `4 vaults (3x3)` + `4 liquid-tanks (3x3)` **placés exactement aux 4 angles internes, collés aux bordures et collés deux à deux**.
   * **Alimentation & Déchargeurs (`unloader`) :**
     * Chaque `vault`/`container` touche directement un couloir de munitions actif (`couloirs_stockage`) qui le remplit avec les 2 munitions (aucun `sorter` mono-munition ne bloque l'entrée de ce couloir — **Fix A**).
     * Chaque `vault`/`container` est connecté sur son flanc libre à **1 ou 2 `unloader`** configurés sur les **2 (ou 1) munitions retenues** (`config` exportée dans `legend.json`), qui réinjectent dans le couloir sans jamais toucher le `liquid-tank`.
2. **Réseau Électrique 100 % Couvert et Connexe (`_placer_energie_connectee`) :**
   * Exécuté **avant** le comblement final des trous (et autorisé à remplacer une tourelle `1x1` si nécessaire) pour qu'il soit impossible d'avoir 0 `power-node`.
   * Relie par BFS tous les `power-node` en ajoutant des nœuds relais jusqu'à obtenir **exactement 1 seule composante connexe** (`distance <= 6.0`).
3. **Architecture du Double Peigne sans collision et Ponts 100 % Pairs :**
   * **Suppression des couloirs inutiles :** Un couloir horizontal de munitions n'est tracé que s'il borde au moins une tourelle à munition solide ou un stockage tampon.
   * **Boucle de Liquide continue (Colonnes `x_max - 4` à droite et `x_min + 2` à gauche) :**
     * Aucun pont vertical de saut sur les colonnes de liquide : les colonnes de liquide sont 100 % continues en `pulse-conduit` / `liquid-router`.
     * Le seul pont vertical de liquide est le **pont d'entrée arrière** (`x_max - 3`, de `hauteur - 1` vers `y_liq_bas`), évitant tout lien parasite.
   * **Boucle de Munitions & Franchissement horizontal (`rot = 2`) :**
     * Les ressources montent à droite (`x_max - 1`, `rot = 1`).
     * À chaque jonction de couloir intermédiaire : une `underflow-gate` (`rot = 1`) sur `x_max - 1` et un **`sorter` (Trieur normal, `rot = 2`) collé à sa gauche en `x_max - 2`**, suivi d'un pont horizontal `(x_max - 3 -> x_max - 5)` (`rot = 2`) qui **saute par-dessus la colonne de liquide droite (`x_max - 4`)**.
     * En haut à droite (`x_max - 1, y_min`) : **aucun `sorter`**, mais un convoyeur `rot = 2` pour que tout le surplus tourne à gauche par défaut.
     * À gauche de chaque couloir (`yc >= min(lignes_liq)`) : un pont horizontal `(x_min + 3 -> x_min + 1)` (`rot = 2`) **saute par-dessus la colonne de liquide gauche (`x_min + 2`)** et déverse ses items dans le convoyeur descendant `(x_min, yc)` (`rot = 3`), qui descend jusqu'au collecteur bas (`y_max - 1`, `rot = 0`) et reboucle à droite !
   * **Chaîne de ponts bout-à-bout et Parité Paire Stricte :**
     * Zéro `underflow-gate` intermédiaire entre les ponts d'un couloir : les paires de ponts sont collées bout-à-bout.
     * Le nombre de têtes de ponts par ligne `(y, bid, rot)` et par colonne `(x, bid, rot)` est **strictement pair (`count % 2 == 0`)**.

### Phase 7 & Phase 8 : Fermeture Étanche des Murs & Export (`phase7_protection_compaction`, `phase8_generer_fichiers`)


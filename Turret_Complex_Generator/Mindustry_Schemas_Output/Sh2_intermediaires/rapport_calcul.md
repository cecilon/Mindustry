# Rapport de calcul - Complexe de tourelles Mindustry

## 1. Parametres

- Dimensions : 40 x 40 (surface 1600 cases)
- Ressources : coal, copper, graphite, lead, metaglass, plastanium, sand, silicon, surge-alloy, thorium
- Capacites : energy
- Duree de simulation : 20 s
- Murs : actives (mode applique : `ring2`)
- Fichier de donnees : `data.json`

## 2. Blocs utilisables (Phase 2)

- Tourelles offensives : duo, scorch, hail, arc, lancer, fuse
- Tourelles de protection : mender
- Distribution : conveyor, junction, bridge-conveyor, sorter, inverted-sorter, router, distributor, overflow-gate, underflow-gate
- Sources d'energie : combustion-generator, solar-panel, large-solar-panel
- Crafting : aucun
- Mur retenu : petit = `surge-wall`, grand = `surge-wall-large`

## 3. Optimisation DPS offensif (Phase 3)

Critere glouton : DPS / nombre de cases (l'espace est la contrainte, les ressources ne sont pas plafonnees), ex-aequo departages par le cout. Le ratio DPS/cout du cahier des charges est conserve en departage. Espace tourelles plafonne a 80% de l'interieur utile (1036 cases).

| Tourelle | Munition | DPS unitaire | Quantite | DPS cumule |
|---|---|---|---|---|
| arc | power | 35.0 | 8 | 280.0 |
| scorch | coal | 170.0 | 272 | 46240.0 |

- Nombre de tourelles : **280**
- DPS moyen par tourelle : **166.14**
- Duree : 20 s
- **DPS_total = 280 x 166.14 x 20 = 930400.0**

Configurations explorees :
- crafting=False, limite tourelles a energie=8 -> DPS/s=46520.0

## 4. Energie / liquides / utilitaires

- Consommation : 1584/s ; production : 1584/s (264 x `solar-panel`) ; noeuds d'energie : 28
- Crafting : non utilise.
- Liquides : non fournis.

## 5. Murs (Phase 5)

- Mode : `ring2` ; cases de mur : 303

## 6. Chaine d'approvisionnement (R6 / R7)

- Zone utile : x 2..37, y 2..35 ; contour de distribution en BOUCLE FERMEE (sens horaire)
- Alternance convoyeur/routeur pour alimenter les tourelles adjacentes ; lignes d'alimentation intermediaires en y = [4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34]
- Entree unique : colonne x=19 a l'arriere (bas), pont par-dessus les murs
- Convention de rotation : 0 = `>`, 1 = `v`, 2 = `<`, 3 = `^` (convention du cahier des charges)

## 7. Protection (Phase 7 / R13)

- Aucune protection posee (ressources/energie insuffisantes ou espace epuise).

## 8. Cout total de construction

- copper : 19113
- graphite : 5996
- lead : 496
- silicon : 3960
- surge-alloy : 1818

Blocs poses : arc x8, bridge-conveyor x2, conveyor x359, power-node x28, router x322, scorch x272, solar-panel x264, surge-wall x3, surge-wall-large x75

## 9. Verification Blocs Multi-Tuiles

Bloc (Ancre) : `W`
- ID : surge-wall-large
- Dimensions : 2 x 2
- Tuiles occupees par bloc : 4
- Continuations par bloc : 3 x `*`
- Nombre d'instances : 75

Total `*` dans schema.txt : 225 (tous referencent l'entree `*` unique de legend.json)

## 10. Validations (Phase 8)

OK R2 - Aucun bloc ne depasse les frontieres

OK R6 - Toutes les tourelles a munitions touchent un routeur de la chaine (272/272)

OK R6 - Boucle fermee de distribution (>= 10x10), 136 cases

OK R7 - Chaine d'entree unique a l'arriere (colonne [19])

OK R8 - Murs places (303 cases de mur, mode ring2)

ECHEC R13 - Protection non constructible avec les ressources fournies

OK Multi-tuiles - nombre de '*' (225) = somme des continuations attendues (225)

OK Multi-tuiles - '*' n'est jamais un identifiant de bloc

OK R10 - Energie : 1584/s produits pour 1584/s consommes

## 11. Hypotheses et limites

- Valeurs du `data.json` approximatives (v7), compilees manuellement ; remplacez-les par un scraping du wiki si besoin.
- Les generateurs a combustible sont poses au contact d'un routeur ; les noeuds d'energie doivent etre relies (laser) en jeu.
- Les protections (reparateurs) ont leur munition optionnelle ignoree ; elles ne sont pas raccordees a la chaine.
- Le DPS est theorique (cible terrestre, tourelles en feu continu, sans recharge de portee/cible).

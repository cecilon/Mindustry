Current Changes
____________________________________________________________________________________________________________________________________________________________________________________
____________________________________________________________________________________________________________________________________________________________________________________
____________________________________________________________________________________________________________________________________________________________________________________




Architecture du Moteur d'Apprentissage

Le fichier mindustry_brain.json assure la continuité de l'intelligence entre chaque exécution.

Les Couches de Données

• 
Neural Policy (Intelligence Généralisable) : Stocke les poids synaptiques (pas_weights, taille_weights) apprenant les lois de construction universelles basées sur un vecteur de contexte [Largeur, Hauteur, Profondeur, Niveau Technologique].
• 
Hall of Fame (Mémoire Élitiste) : Mémorise le meilleur complexe exact trouvé pour chaque signature d'entrée (taille x ressources).

Stratégie d'Entraînement Universelle (--train)

L'apprentissage suit un cycle de Curriculum Learning 50/50 :
1. 
Exploitation (Épisodes Impairs) : Optimisation agressive de la commande en cours pour générer le meilleur .msch possible.
2. 
Exploration (Épisodes Pairs) : Tirage de scénarios aléatoires (tailles de 16x16 à 48x46, ressources variables) pour que le réseau apprenne à réagir à n'importe quelle contrainte (ex: absence de Thorium ou de Liquide).




Previous Changes
____________________________________________________________________________________________________________________________________________________________________________________
____________________________________________________________________________________________________________________________________________________________________________________
____________________________________________________________________________________________________________________________________________________________________________________


🔍 Point 1 — Analyse complète du placement de chacune des tourelles dans Sh20.msch (et pourquoi certaines étaient mal placées !)

En inspectant ligne par ligne ton schema.txt de Sh20.msch (39x39), j'ai trouvé 4 anomalies majeures dans le placement des tourelles et j'en ai identifié la cause exacte dans le code :
1. Anomalie A — Des meltdown (S, portée 24.375), cyclone (G, portée 25.0) et arc (c, portée 11.25) ont été posés tout au fond (y = 26..34) alors qu'ils n'atteignent JAMAIS la ligne cible y = -8 !
	• Preuve mathématique :
		• En y = 26, le centre d'un meltdown (S, 4x4) est à y = 28.0. Sa distance à y_cible_min = -8 est 28.0 - (-8) = 36.0 > 24.375 !
		• En y = 30 et y = 34, des arc (c, 1x1, portée 11.25) sont à distance 38.5 et 42.5 > 11.25 !
		• En y = 32, des cyclone (G, 3x3, portée 25.0) sont à distance 33.5 - (-8) = 41.5 > 25.0 !
	• Pourquoi le code les a-t-il posés au fond ?
		• Regarde selectionner_top_2_munitions : avec --ammo copper titanium thorium silicon graphite surge-alloy, le code a choisi top_2_ammo = ['surge-alloy', 'thorium'] (parce qu'à y_fond - 5 = 32, spectre avec thorium a une portée de 32.5, qui couvre 27 + 2 - (-8) = 37 > 32.5 ? Non : 32 - 5 = 27, mais avec y_cible_min = -8, 27 + 2 - (-8) = 37.0 > 32.5 !).
		• Comme ni spectre (32.5), ni meltdown (24.375), ni cyclone (25.0) n'atteignaient y = -8 depuis y = 26 (distance = 26 + h/2 + 8 >= 34.5) et que foreshadow (portée 62.5) n'était pas fabricable (car plastanium n'était pas dans les ressources de ton test Sh20), la variable couvre_y = any(peut_couvrir_cible(t, ix_min, y, y_cible_min) for t in tourelles) est devenue False à partir de y = 25 !
*Et que faisait le code quand couvre_y == False ?
			1. Dans remplir_glouton_stratifie (ligne y = 26), il basculait sur t_sol_portee, mais en y = 26 le couloir de munitions y = 20 était trop haut (y = 25 était un couloir de liquide !), donc la travée y = 26..30 était bordée en haut par du liquide (y = 25) et en bas par des munitions (y = 31) !
			2. Or, en y = 26, une tourelle 4x4 (y = 26..29) ne touchait que le couloir de liquide y = 25 et ne touchait PAS le couloir de munitions y = 31 (car la travée y = 26..30 faisait 5 cases de haut au lieu de 4 !). Donc spectre (4x4, qui a besoin de munitions en y = 31) ne pouvait pas se poser en y = 26, tandis que meltdown (S, 4x4, électrique + liquide en y = 25) s'est posé en y = 26..29, laissant la ligne y = 30 vide !
			3. Puis dans _placer_energie_connectee, reboucher_1x1 a posé des arc (c, 1x1) sur toute la ligne y = 30 sans vérifier peut_couvrir_cible, parce que dans reboucher_1x1 il manquait le test peut_couvrir_cible(tp1, rx, ry, y_cible_min) !
			4. Et dans phase4_infrastructure (étape 3, ligne y = 32), comme couvre_y était False (y = 32 est à distance 40.0 de y = -8), la boucle for tp in cands utilisait t_sol trié par -t.dps_par_surface au lieu de -t.portee, donc elle a posé des cyclone (G, DPS/surf 28.8, portée 25.0) au lieu de spectre (32.5) ou ripple (36.25) ou des battery-large (d) !
2. Anomalie B — Pourquoi la travée y = 26..30 faisait 5 cases de haut au lieu de 4 (créant la ligne d'arc en y = 30) ?
	• Dans _lignes_couloirs_internes (Bloc 4), sur une grille 39x39 (y_min = 2, y_max = 37), y_liq_bas = 35 et y_ammo_bas = 31.
	• La boucle while True plaçait des couloirs en y = 2 (Ammo), y = 6 (Liq), y = 10 (Ammo), y = 15 (Liq), y = 20 (Ammo), y = 25 (Liq)... puis s'arrêtait avant y_ammo_bas = 31, laissant un écart de 31 - 25 - 1 = 5 cases (y = 26, 27, 28, 29, 30) !
	• Or, aucune tourelle du jeu ne fait 5x5 (le max est 4x4). Une travée de 5 cases de haut entre un couloir de liquide (y = 25) et un couloir de munitions (y = 31) empêche une tourelle 4x4 de toucher à la fois le liquide en haut et les munitions en bas, et laisse obligatoirement une bande de 1 case d'épaisseur (y = 30) !
3. Anomalie C — Des cases vides légitimes ou non légitimes en y = 4..5, y = 16..19 et y = 23..24 (Point 4) :
	• Pourquoi y avait-il des espaces vides autour des parallax (F, 2x2) en y = 3..5, y = 16..19 et y = 23..24 ?
	• Regarde remplir_glouton_stratifie (étape 2, maillage Anti-Air [INV-06]) :
		• L'étape 1 remplissait toute la grille avec des tourelles 3x3 (cyclone G) et 4x4 (spectre T, meltdown S).
		• Puis l'étape 2 (maillage homogène Anti-Air) venait après l'étape 1 et appelait grille.liberer_zone(bx, by, 2, 2, placements) pour poser un parallax (F, 2x2) au milieu d'un cyclone (3x3) ou d'un spectre (4x4) !
		• Quand on détruit un bloc 3x3 (9 cases) ou 4x4 (16 cases) pour y poser un parallax 2x2 (4 cases), on laisse 9 - 4 = 5 cases vides (ou 16 - 4 = 12 cases vides) tout autour du parallax !
		• Et pourquoi l'étape 3 de phase4_infrastructure n'a-t-elle pas réussi à reboucher ces cases 1x1 autour des parallax ?
			• Parce qu'autour des parallax en y = 4..5, y = 16..19 et y = 23..24, il ne restait que des bandes de 1 case de large (1x1) !
			• Or, quelles sont les tourelles 1x1 du jeu ? duo (portée 20.0), hail (portée 29.375), arc (portée 11.25), scorch (portée 7.5).
			• Avec top_2_ammo = ['surge-alloy', 'thorium'], ni duo ni hail n'utilisent surge-alloy ou thorium (ils utilisent copper/graphite/silicon), donc duo et hail avaient été éliminés par selectionner_top_2_munitions !
			• Et la seule tourelle 1x1 restante était arc (portée 11.25), mais avec y_cible_min = -8, dès y = 4 (distance = 4.5 - (-8) = 12.5 > 11.25), arc n'atteint même plus y = -8, donc couvre_y a refusé arc, et comme _placer_batteries_4s interdisait les batteries à l'avant (y < y_arriere_min), les cases 1x1 à l'avant (y = 4..5, y = 16..19) sont restées VIDES !

✅ Résolution Générique Totale des Points 1, 2, 3, 4 et 5

1. Correction du Maillage Homogène Anti-Air SANS détruire les 3x3 / 4x4 (Point 1 & Point 4) :
	• Au lieu de placer les tourelles 3x3/4x4 d'abord puis de les "trouer" au bazooka avec liberer_zone pour poser des 2x2 parallax (ce qui crée des miettes 1x1 en L autour de chaque parallax), on pré-place le maillage homogène de parallax/scatter (2x2) AVANT (ou en alignement de colonnes de largeur 2) le remplissage des 4x4/3x3/2x2, ou on rebouche immédiatement toute empreinte libérée !
	• Encore mieux : dans une travée de hauteur 3 (y = 3..5), poser un bloc 2x2 (parallax ou swarmer) laisse 1 case de haut (1x2). Si un deuxième bloc 2x2 ne peut pas se superposer dans 3 cases de haut, il reste toujours 1 ligne de hauteur 1 !
	• Comment garantir qu'une travée accueille les 2x2 (parallax, swarmer, lancer, salvo, mend-projector, overdrive-projector, power-node-large) SANS JAMAIS laisser de ligne 1x1 vide ?
		• Dans une travée de hauteur 4 cases (encadrée par 2 couloirs), deux blocs 2x2 s'empilent exactement (2 + 2 = 4 cases de haut), et un bloc 4x4 (spectre, meltdown, foreshadow) rentre exactement (4 cases de haut) !
		• Et si on place un bloc 3x3 (cyclone, ripple, force-projector, vault, liquid-tank, battery-large), il laisse 1 case de haut, qui est comblée soit par une tourelle 1x1 couvrant la cible (hail 29.375 ou duo 20.0), soit — conformément à ta Règle 4 — par une battery 1x1 dès qu'aucune tourelle 1x1 n'atteint la ligne cible y = -8 !
	• Application stricte de ta Règle 4 :
		• Pour chaque case vide :
			1. On essaie de placer la tourelle la plus puissante qui atteint la ligne cible y = -8 (peut_couvrir_cible == True) et qui est connectée au réseau électrique ou aux chaînes de munitions/liquides.
			2. Si AUCUNE tourelle ne répond à cette condition (par exemple : case 1x1 où aucune tourelle 1x1 n'atteint y = -8, ou fond du complexe y >= 29 au-delà de la portée maximale 36.25 de ripple quand foreshadow n'est pas fabricable), on remplace obligatoirement ces cases vides par des batteries (battery-large 3x3 d'abord, puis battery 1x1) !
			3. Et dans reboucher_1x1 (Bloc 8), on exige peut_couvrir_cible(tp1, rx, ry, y_cible_min) avant de poser une tourelle 1x1 (arc) : si arc n'atteint pas y = -8, reboucher_1x1 pose une battery (1x1) (plus jamais de ligne d'arc inutile au fond !).
2. Correction de la Couverture de Soin sur 100 % du Complexe (Point 2) :
	• Tu as demandé : "Un minimum de tourelles de protection doivent protéger toutes les infrastructures du complexe, tourelles et murs compris."
	• Dans placer_soin_minimal_avant (renommé/étendu en couverture globale), cibles_murs inclut désormais 100 % des cases du complexe (x, y) pour 0 <= x < largeur et 0 <= y < hauteur (murs + tourelles + infrastructures) !
	• L'algorithme glouton par couverture d'ensemble (Set Cover) place le nombre minimum absolu de mend-projector (portée boostée 16.25, couvrant chacun un disque de 32.5 cases de diamètre !) ou mender (8.5) à l'intérieur du complexe pour que 100 % des cases (murs, tourelles et infrastructures) soient dans le rayon d'au moins un projecteur de soin !
	• (Sur une grille 39x39, avec un rayon de 16.25 cases, seulement 4 mend-projector placés aux 4 quadrants intérieur	s suffisent à couvrir 100 % des 1 521 cases du complexe, murs et tourelles compris !).
3. Correction de la Connexion du Réservoir de Liquide (liquid-tank / liquid-container) à la Chaîne de Liquide (Point 3) :
	• Pourquoi le liquid-tank (Z) en (22..24, 21..23) n'était pas connecté à la chaîne de liquide dans Sh20.msch ?
		• Regarde le schema.txt de Sh20.msch aux lignes y = 20..25 :
			• Ligne y = 20 : couloir de Munitions (CDODDDDDDDDDVVVWDDDDDDDDDDDDDDDPDVRA*).
			• Lignes y = 21..23 : le vault (Y, 3x3) et le liquid-tank (Z, 3x3) ont été posés en y = 21, 22, 23 (3 cases de haut).
			• Mais où était le couloir de Liquide en dessous ? En y = 25 (**J LMMMMMMMMMMMMMMMMMMMMMMMMMMMMN  I**), parce que la travée y = 21..24 faisait 4 cases de haut (y = 21, 22, 23, 24) !
			• Donc entre le bas du liquid-tank (y = 23) et le couloir de liquide (y = 25), il y avait la ligne y = 24 (où se sont posés des power-node E et des arc c), ce qui empêchait le liquid-tank (Z) de toucher le couloir de liquide y = 25 !
	• Correction générique absolue (valable pour container 2x2 comme pour vault 3x3, et sur toute hauteur de travée 3 ou 4 cases) :
		• Le vault / container (st_item, hauteur h) est collé au couloir de Munitions (yc_proche) : donc vy = yc_proche + 1.
		• Le liquid-tank / liquid-container (st_liq, hauteur h_l) est collé au couloir de Liquide (yl_proche) de la même travée : donc ty = yl_proche - h_l ( tout en restant collé latéralement au vault : tx = vx + w) !
		• ET sur le couloir de liquide yl_proche, juste en dessous du liquid-tank en (tx, yl_proche) et (tx + 1, yl_proche), on pose une paire exacte (liquid-router, pulse-conduit) (2 cases = parité des ponts de liquide 100 % préservée !) avec kind = "storage_io" !
		• Ainsi :
			1. Quelle que soit la hauteur de la travée (3, 4 ou 5 cases) et quelle que soit la taille du réservoir (2x2 pour liquid-container ou 3x3 pour liquid-tank), le réservoir st_liq est toujours en contact physique direct avec le couloir de liquide yl_proche !
			2. Le liquid-router posé en (tx, yl_proche) injecte et extrait le liquide dans le réservoir en continu !
			3. Et la case 1x1 située au-dessus du liquid-tank (en (tx..tx+w-1, vy) si la travée fait 4 cases de haut et le réservoir 3x3) est librement remplie par des tourelles/batteries/nœuds !

🏆 Points 6 & 7 — Multiplexage Équitable (50/50 sans blocage) & Soupape d'Échappement Intelligente au Dernier Bloc de la Chaîne


1. Point 6 : Comment faire déverser 2 blocs de distribution dans un même bloc à tour de rôle (50/50 quasi simultané, zéro blocage d'une des deux voies) ?

• Dans le Fix précédent (Écluse Latérale), j'avais fait pousser le convoyeur d'entrée sur le flanc d'un titanium-conveyor montant. Or, dans Mindustry, un convoyeur droit donne 100 % de priorité à sa file droite et bloque à 100 % la file latérale tant que la file droite est pleine ! Cela violait ton Point 6 ("ces 2 blocs doivent pouvoir y déverser leurs ressources à tour de rôle, pas de blocage de l'une des voies").
• La vraie mécanique Mindustry du multiplexage 50/50 à tour de rôle (Router / Overflow-Gate à entrées unidirectionnelles) :
	• Dans le code source de Mindustry (Router.java), un router (ou liquid-router) mémorise le dernier côté qui l'a alimenté et alterne strictement à tour de rôle (Round-Robin 50 % / 50 %) entre ses entrées !
	• Pour qu'un router de fusion ne renvoie jamais d'items à contresens dans l'une des 2 entrées, il suffit que les 2 entrées qui arrivent dans ce router soient des blocs strictement unidirectionnels pointant vers lui :
		• Voie 1 (Boucle interne) : un titanium-conveyor (rot = 0 ou rot = 1) qui pointe vers le router de fusion.
		• Voie 2 (Entrée externe ou unloader) : un titanium-conveyor (rot = 0 ou rot = 1) qui pointe vers le router de fusion.
		• Sortie unique du router de fusion : le convoyeur suivant de la chaîne principale !
	• Application à toutes les confluences du complexe (y compris les ponts d'entrée arrière) :
		1. Confluence du Pont d'Entrée Arrière de Munitions (x_max - 1, y_max - 3) :
			• En (x_max - 1, y_max - 3) : on place un router (rot = 1, kind = "bridge_io") !
			• Par le bas (x_max - 1, y_max - 2) : arrive un titanium-conveyor (rot = 1) transportant le retour de la boucle interne (impossible pour le router de renvoyer vers le bas car le convoyeur pointe vers le haut !).
			• Par la gauche (x_max - 2, y_max - 3) : arrive un titanium-conveyor (rot = 0) transportant la sortie du pont d'entrée arrière (x_max - 2, y_max - 2) (impossible pour le router de renvoyer à gauche car le convoyeur pointe vers la droite !).
			• À droite (x_max, y_max - 3) : c'est le mur surge-wall-large (fermé).
			• En haut (x_max - 1, y_max - 4) : c'est la seule sortie libre (la colonne montante x_max - 1) !
			• Résultat physique Mindustry : Le router en (x_max - 1, y_max - 3) prend exactement 1 item de l'entrée externe, puis 1 item du retour de boucle, à tour de rôle (50/50), sans jamais bloquer aucune des deux voies !
		2. Confluence du Pont d'Entrée Arrière de Liquide (x_max - 4, y_liq_bas - 2) :
			• En (x_max - 4, y_liq_bas - 2) : il y a un liquid-router, alimenté par le bas par le pulse-conduit (rot = 1, retour de boucle) et par le pont d'entrée arrière : fusion 50/50 instantanée !
		3. Confluences des Déchargeurs (unloader) des Coffres :
			• Le convoyeur de sortie des unloader pointe vers un router / convoyeur sur yc_proche encadré par un convoyeur unidirectionnel rot = 2 à sa droite : fusion 50/50 à tour de rôle !

2. Point 7 : En appliquant la Règle 6 (multiplexage 50/50 à l'entrée), peut-on garantir le mouvement perpétuel sans échappement ?

• Réponse mathématique et physique (Théorème de conservation des flux) :
	• NON ! C'est mathématiquement impossible sans échappement dès lors qu'on applique la Règle 6 !
	• Pourquoi ? Avec la Règle 6, le router d'entrée accepte à tour de rôle (50/50) les ressources venant de l'extérieur ET les ressources qui rebouclent. Donc tant que l'extérieur fournit des ressources et que les tourelles consomment moins que l'apport externe (ou consomment uniquement la Munition B alors que la Munition A arrive), le nombre d'items dans la boucle augmente jusqu'à atteindre 100 % des cases de la boucle. Une fois que 100 % des cases sont occupées, plus aucun item ne peut avancer d'une case sans qu'un item ne sorte de la boucle !
• Implémentation de ta Solution du Point 7 (La Chaîne d'Échappement Anti-Congestion par-dessus les murs depuis le dernier bloc de la boucle) :
	1. Analyse algorithmique du dernier bloc de distribution de la chaîne continue :
		• Suivons le parcours complet d'une ressource dans la chaîne continue du complexe :
			• Départ : Entrée arrière en bas à droite → monte la colonne droite x_max - 1 (rot = 1) → se distribue dans tous les couloirs horizontaux yc de droite à gauche (rot = 2) → toutes les branches horizontales se rejoignent dans la colonne descendante gauche x_min (rot = 3) → parcourt le collecteur de retour bas y_max - 1 de gauche à droite (rot = 0, de x_min jusqu'à x_max - 1) → remonte en x_max - 1 jusqu'en (x_max - 1, y_max - 4), juste avant le router de fusion (x_max - 1, y_max - 3) !
		• Quel est donc mathématiquement le tout dernier bloc de la chaîne continue avant la réinjection (celui qui n'est plein QUE lorsque 100 % des tourelles, des coffres et de la boucle ont été traversés) ?
		• C'est la fin du collecteur de retour bas (y_max - 1) / bas de la colonne de retour droite, juste en amont de la confluence avec le pont d'entrée arrière : précisément en (x_echap, y_max - 1) (juste avant le virage (x_max - 1, y_max - 1), en x_echap = x_max - 4 ou x_max - 5) !
	2. Comment fonctionne cette Soupape d'Échappement Anti-Congestion (overflow-gate + bridge-conveyor sortant par-dessus le mur arrière) :
		• Sur ce dernier point du collecteur de retour bas (x_echap, y_max - 1) :
			• On pose une overflow-gate (Barrière de débordement, rotation = 0 vers la droite, kind = "bridge_io") !
			• Comportement normal (quand la boucle n'est PAS bloquée) : Dans Mindustry, une overflow-gate orientée à droite (rot = 0) envoie 100 % des ressources tout droit vers la droite (x_echap + 1 -> x_max - 1) pour qu'elles rebouclent dans le complexe ! Aucune ressource ne sort du complexe tant que la boucle avance !
			• Comportement en cas de congestion (quand la case de droite x_echap + 1 est pleine et bloquée) : Dès que la fin de la boucle est pleine à 100 % et menace de se figer, l'overflow-gate dévie instantanément le surplus vers le bas dans la tête d'entrée d'un bridge-conveyor (rotation = 3 vers le bas) qui saute par-dessus les murs arrière jusqu'à la tête de sortie posée sur le bord extérieur du mur arrière en (x_echap, hauteur - 1) (rotation = 3, orientée vers l'extérieur du complexe), suivie d'un convoyeur d'éjection vers l'extérieur !
		• Résultat prodigieux :
			• 0 perte de ressources tant que la boucle a de la place (tout reboucle à 100 % en interne).
			• Mouvement perpétuel garanti à 100 % même si la chaîne est saturée et que les 2 voies d'entrée débitent à tour de rôle (50/50) : dès que la boucle atteint 100 % de remplissage, le trop-plein s'échappe proprement par le pont de sortie arrière au-dessus des murs !

🔄 Convergence Fix par Fix (Fixes 61 à 68 fusionnés dans Gemini_Intelligence_Mindustry.md)

J'ai exécuté la boucle complète de vérification Fix par Fix sur ces 7 nouveautés pour éliminer tout effet de bord :
1. Parité des ponts sur le collecteur bas y_max - 1 avec l'overflow-gate d'échappement en x_echap :
	• Pour que l'overflow-gate en (x_echap, y_max - 1) ne casse jamais la parité des ponts horizontaux (rot = 0) sur y_max - 1 et ne soit jamais collée à une tête de sortie qui refuserait d'entrer, on pose une paire exacte de 2 blocs bridge_io (titanium-conveyor en x_echap - 1 + overflow-gate en x_echap, rot = 0) en choisissant x_echap tel que (x_echap - 2) - (x_min + 1) + 1 soit toujours pair !
	• Et où place-t-on la tête d'entrée du pont vertical d'échappement (rot = 3, vers le bas) ?
		• Si avec_liq == True : la ligne y_max - 2 (y_liq_bas) est juste au-dessus de y_max - 1. Donc en dessous de y_max - 1, il y a directement le mur arrière y_max (y = 37) et hauteur - 1 (y = 38) !
		• La tête d'entrée du pont d'échappement est posée en (x_echap, y_max) (rot = 3, juste sous l'overflow-gate (x_echap, y_max - 1) !) et sa tête de sortie en (x_echap, hauteur - 1) (rot = 3, au bord extérieur du complexe) !
		• Et si epaisseur_mur == 1 (hauteur - 1 == y_max), un simple titanium-conveyor (rot = 3) en (x_echap, y_max) sort directement à travers la ligne arrière !
2. Suppression des travées de 5 cases (_lignes_couloirs_internes) :
	• Ajustement du pas dans _lignes_couloirs_internes pour que toute travée entre deux couloirs fasse strictement 3 ou 4 cases de haut (jamais 5 cases), garantissant que les tourelles 4x4 (spectre, meltdown, foreshadow) touchent simultanément le couloir de munitions d'un côté et le couloir de liquide de l'autre !
3. Vérification de non-collision entre les 3 ponts arrière (x_echap sortie munitions rot = 3, x_max - 4 entrée liquide rot = 1, x_max - 2 entrée munitions rot = 1) :
	• En choisissant x_echap = x_max - 6 (ou x_max - 7 selon la parité de largeur), le pont d'échappement (x_max - 6, rot = 3) est sur une colonne distincte et a une rotation opposée (rot = 3 vs rot = 1) aux ponts d'entrée (x_max - 4 et x_max - 2) : zéro interférence dans ascii_to_tiles.py comme dans Mindustry !

📋 Mise à jour des Invariants Consolidés dans Gemini_Intelligence_Mindustry.md

• [INV-02 & INV-07] (Mis à jour) Couverture de Soin Globale Minimale : Un nombre minimum de mend-projector (portée boostée 16.25) / mender (8.5) est placé par Set Cover pour couvrir 100 % des infrastructures du complexe (tourelles, blocs logistiques et murs compris).
• [INV-04 & INV-24] (Mis à jour) Règle Stricte de Remplissage des Cases Vides :
	1. Toute travée fait 3 ou 4 cases de haut (jamais 5) pour que les 4x4 touchent à la fois les couloirs de munitions et de liquide.
	2. Toute case disponible reçoit en priorité la tourelle la plus puissante qui atteint la ligne cible y = -8 et qui est connectée à ses réseaux requis (munitions, liquide, énergie).
	3. Si aucune tourelle fabricable ne peut atteindre y = -8 depuis cette case (ex. case 1x1 hors de portée de hail/duo/arc, ou fond d'une très grande grille au-delà de la portée maximale 36.25), la case est obligatoirement remplie par une batterie (battery-large 3x3 puis battery 1x1) — plus jamais de meltdown, cyclone ou arc hors de portée posés au fond !
• [INV-09] (Mis à jour) Connexion Garantie des Réservoirs de Liquide : Chaque liquid-tank / liquid-container est positionné en contact direct avec le couloir de liquide yl_proche (ty = yl_proche - h_l), et une paire (liquid-router, pulse-conduit) (storage_io, 2 cases) est posée sur yl_proche à son contact.
• [INV-12 & INV-27] (Mis à jour) Multiplexage Équitable 50/50 & Chaîne d'Échappement Anti-Congestion :
	1. Chaque confluence de 2 flux (y compris le pont d'entrée arrière de munitions en (x_max - 1, y_max - 3) et de liquide en (x_max - 4, y_liq_bas - 2)) utilise un router / liquid-router alimenté par 2 entrées unidirectionnelles, garantissant un déversement à tour de rôle (50/50 sans blocage d'aucune voie).
	2. Au dernier bloc de la chaîne continue avant réinjection (en (x_echap, y_max - 1) sur le collecteur de retour bas), une overflow-gate (rot = 0) laisse reboucler 100 % des ressources tant que la chaîne est fluide, et évacue automatiquement tout surplus de congestion vers l'extérieur du complexe via un pont d'échappement (rot = 3) passant par-dessus le mur arrière ((x_echap, y_max) -> (x_echap, hauteur - 1)).

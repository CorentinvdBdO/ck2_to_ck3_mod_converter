# Last converter run

Overwritten by `ck2ck3` on every run; do not edit by hand.

- when: 2026-09-12 18:34:19
- config: `configs/faerun.toml`
- mode: write
- source: `/home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun`
- output: `/home/cvdbdo/git/paradox/ck3/wt/_out/province-edges`
- steps: clean, descriptor, tc_template, map, dynasties, cultures, religions, titles, history_titles, bookmarks, traits, characters, loc, decisions, events, tests
- files written: 1486
- warnings: 302
- total time: 208.9 s

## Steps

| step | seconds | files | counts | summary |
|---|---|---|---|---|
| clean | 0.00 | 0 | - | refused to clean /home/cvdbdo/git/paradox/ck3/wt/_out/province-edges (does not look like the generated mod) |
| descriptor | 0.00 | 2 | tags=3, replace_paths=13 | descriptor.mod: 'Faerun (CK2 conversion, raw)' 0.1.0 for CK3 1.19.*, 13 replace_path |
| tc_template | 0.02 | 227 | rows=74, folders=32, shadows=204, neutralised=23, kept=42, replace_paths=0 | tc_template: 204 empty shadows and 23 key-only stubs over 32 vanilla folders, 42 folders deliberately kept |
| map | 193.93 | 59 | provinces=4275, land=3914, baronies=3704, baronies_demoted=153, counties=2125, sea=180, lakes=95, river_provinces=86, impassable=210, lost=3, regrown=2, province_edges_changed_px=455890, province_edges_max_shift_px=1.414, province_edges_p95_shift_px=1.0, province_edges_reverted_px=20271, adjacencies=319, trees_placed=703425, trees_dropped=26413, colormap_px=3527680, locators_ck2_anchors=2103, locators_ck2_anchor_candidates=2113, locators_moved_instances=24550, terrain_override_counties=899, terrain_override_provinces_changed=947, terrain_override_applied_capital=562, terrain_override_applied_weak=385, terrain_override_kept_bitmap=357, terrain_override_already_agreed=551, terrain_override_unmapped=0, terrain_override_class_px_moved=3731736, heightmap_fill_min_cycles_per_km=0.05, heightmap_erosion_slope_ceiling_steps=0.5, heightmap_distinct_values=39714, heightmap_clamp_floor_px=93468, heightmap_excursion_limited_px=178415, heightmap_detail_seconds=68 | map 8320x6784 at scale 1.9543 (2.9 -> 1.4839 km/px): 4275 provinces, 3704 baronies in 2125 counties, 153 demoted, 3 lost; organic province borders sigma 0.6 source px, relief warp 5847180 px, 455890 px changed id (max 1.414 / p95 1.0 canvas px, bound 1.9543); heightmap detail cliff_aware/eroded/vanilla_curve, fill>=0.05 c/km, slope ceiling 0.5 steps, 0.353 % of land on the clamp floor |
| dynasties | 1.17 | 9 | names=11952, cultures=11951, dynasties=11952, dynasties_without_culture=1, duplicate_ids=1, dropped_used_for_random=754, dropped_coat_of_arms=20, dropped_religion=4, loc_keys=11951, loc_key_collisions=2 | 11952 dynasties in 3 files, 11951 name loc keys, 20 CK2 coats of arms dropped |
| cultures | 1.31 | 28 | culture_groups=67, cultures=419, name_lists=419, name_loc_keys=44231, dynasty_names_cultures=396, dynasty_names_below_minimum=23, placeholder_ethnicities=37, traditions_emitted=916, cultures_with_traditions=392, cultures_without_traditions=27, groups_no_traditions_by_design=11, missing_tradition_overrides=0, opinion_formats=417, opinion_formats_vanilla_already=2, missing_race_overrides=0, missing_ethnicity_overrides=0 | 67 culture groups -> 67 heritage + 67 language pillars; 419 cultures with 419 name lists; 37 placeholder ethnicities |
| religions | 0.26 | 18 | religion_groups=15, families=15, faiths=94, holy_site_types=254, holy_site_links=469, faiths_without_holy_site=0, holy_sites_dropped_dead_county=1, pagan_roots_religions=6, loc_rename_rows=367, opinion_formats=124, opinion_formats_vanilla_already=0 | 15 religion groups -> 15 families + 15 religions; 94 faiths with 469 holy sites over 254 counties |
| titles | 2.39 | 3 | b_titles=3704, c_titles=2125, d_titles=979, e_titles=65, k_titles=267, commented_titles=11659, cultural_name_keys=724, coats_of_arms=3436, ck2_flags_recorded=3415, placement_demoted=153, placement_placed=3704, placement_unbuilt=11338 | 7140 CK3 titles (65 e_, 267 k_, 979 d_, 2125 c_, 3704 b_), 11659 commented out, placement mode barony_set |
| history_titles | 0.12 | 173 | titles_with_history=3227, history_stubs=246, history_commented_out=193, files=166, province_blocks=3704 | 3227 title histories, 193 commented out, 3704 province blocks in 166 files |
| bookmarks | 0.05 | 85 | bookmarks=17, bookmark_characters=82, positioned_from_map=63, positioned_on_grid=19 | 17 bookmarks, 82 characters (63 placed from the CK2 map, 19 on the fallback grid), default 1357.1.1 |
| traits | 0.23 | 170 | ck2_traits=1417, ported=400, race=117, deduped=142, dropped=7, sexuality=1, commented=867, icons=168, placeholder_comments=93, field_comments=678, modifier_comments=87, trigger_blocks_commented=66, duplicate_keys=81, grouped=69, genetic_conflicts=124, race_lifespan=16, race_lifespan_blank=92, compatibility=3, race_immortal=9, wrong_scope_comments=1 | 400 traits ported (117 race), 142 deduped to CK3 vanilla, 7 dropped (no CK3 counterpart), 1 became a CK3 sexuality, 867 commented out |
| characters | 2.36 | 80 | traits_dropped=10154, traits=32497, traits_renamed=4690, nicknames_dropped=821, dated_blocks=47107, death_reason_exact=2165, deaths=18124, characters=18124, relations=1122, effect_blocks=2519, effect_blocks_added=3433, nicknames=219, death_reason_fallback=272, death_reason_approx=671, traits_dropped_no_ck3=140, traits_sexuality=22, traits_conflict_dropped=6, modifiers_dropped=75, empty_names=54, files=80, dynasties_referenced=5739, integrity_same-sex_spouse=8 | 18124 characters in 80 files, 47107 dated blocks, 15925 CK2 entries commented out, 8 integrity problems |
| loc | 2.14 | 484 | files=484, keys_english=156800, keys_french=156800, keys_german=156800, keys_spanish=156800, codes=147711, codes_converted=134472, codes_unconverted=13239, colour_codes=72295, icon_codes=28, stray_brackets=39, stray_colour_marks=2, name_list_keys=44231, custom_loc_markered=43558, custom_loc_names=4573, named_scope_markered=64803, named_scope_names=2566, duplicate_keys=1265, invalid_keys=23, key_map_keys=30636 | localisation: 484 yml in 4 languages, 156800 english keys, 91.0% of 147711 text codes converted |
| decisions | 0.30 | 37 | emitted=3, hidden=393, skipped_group=253, skipped_other=181, files=37 | 3 decisions ported live, 393 below min_score (is_shown off, inspectable), 253 out-of-scope groups, 181 other skips, 37 files |
| events | 2.32 | 110 | live=160, stub=1544, skipped_scope=58, skipped_status=11695, not_found=0, files=110, namespaces=97, fixpoint_passes=3, unmapped_keys=1330, loc_key_misses=40 | 160 events live, 1544 inert stubs, 58 skipped by scope, 110 files, 97 namespaces; top unmapped: character_event(1345), trait(990), mother_even_if_dead(907), true_father_even_if_dead(857), add_trait(710) |
| tests | 2.36 | 1 | tests=108, bookmark_characters_skipped=0, bookmark_characters=6, title_holders=50, title_holders_available=2638, provinces=50, provinces_available=3704, aggregate=1 | 108 scripted tests at 1357.1.1 (6 bookmark characters, 50/2638 title holders, 50/3704 provinces) -> tests/fae_generated_tests.txt |

## Warnings

- /home/cvdbdo/git/paradox/ck3/wt/_out/province-edges holds no descriptor.mod, README.md or .git: refusing to clean it
- CK2 province 2314 dropped (1 source pixels)
- CK2 province 2316 dropped (1 source pixels)
- CK2 province 2698 dropped (0 source pixels)
- 75607 county pixels were unreachable from any seed (a detached piece of the county); attached to the nearest barony
- rivers: 19 of 350 sources did not survive (they fall on a pixel the province map says is water)
- rivers: 24 of 308 merges did not survive (they fall on a pixel the province map says is water)
- adjacency 1691->1686 (major_river): CK2 gives no Through province and CK3 requires one; row dropped
- adjacency 1690->1686 (major_river): CK2 gives no Through province and CK3 requires one; row dropped
- adjacency 1687->1686 (major_river): CK2 gives no Through province and CK3 requires one; row dropped
- adjacency 1690->1687 (major_river): CK2 gives no Through province and CK3 requires one; row dropped
- loc key dynn_fae_109 collides with a vanilla key's MURMUR3A hash; renamed to dynn_fae_109_x
- loc key dynn_fae_1215 collides with a vanilla key's MURMUR3A hash; renamed to dynn_fae_1215_x
- CK2 dynasty 644 has no culture
- CK2 dynasty id 15817 is defined more than once; CK3 will see a duplicate fae_ id
- dynasties: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/dynasties/00_dynasties.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- dynasties: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/dynasties/01_animal_dynasties.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- dynasties: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/dynasties/Faerun_Dynasties.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- 23 cultures have fewer than 2 dynasty names even after pooling their culture group, because CK2 defines no dynasty of that group: horse, cat, bear, hedgehog_culture, duck_culture, dog_culture, elephant_culture, dragon_culture, red_panda, lich, undead_creature, undead_human ... (+11). Each is one culture_name_lists.cpp:169, and CK3 has no name to mint a generated character's dynasty from. Needs human input (overrides), not a derivation
- gur_opinion is already declared by vanilla CK3; not re-declared (common/modifier_definition_formats is not a replace_path)
- mari_opinion is already declared by vanilla CK3; not re-declared (common/modifier_definition_formats is not a replace_path)
- cultures: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/99_animals.txt: not valid UTF-8 (invalid continuation byte at byte 315), decoded as cp1252
- cultures: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/demihuman.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- cultures: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/dragons.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- cultures: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/dwarves.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- cultures: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/elves.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- cultures: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/giants.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- cultures: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/human.txt: not valid UTF-8 (invalid start byte at byte 14018), decoded as cp1252
- cultures: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/littlefolk.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- cultures: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/monsters.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- cultures: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/outsiders.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- cultures: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/scalykind.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- religions: holy site laduguer -> c_barakuir dropped: the map step placed no barony in that county, so the titles step does not declare it
- religions: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/landed_titles/01_laerakond.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- religions: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/landed_titles/01_landed_titles.txt: not valid UTF-8 (invalid continuation byte at byte 51113), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/landed_titles/01_laerakond.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/landed_titles/01_landed_titles.txt: not valid UTF-8 (invalid continuation byte at byte 51113), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/provinces/346 - Thentia.txt: not valid UTF-8 (invalid start byte at byte 224), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/b_jaw_long.txt: not valid UTF-8 (invalid start byte at byte 248), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_atai.txt: not valid UTF-8 (invalid start byte at byte 129), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_bulobo.txt: not valid UTF-8 (invalid continuation byte at byte 106), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_chaikou_hills.txt: not valid UTF-8 (invalid start byte at byte 99), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_daong_forest.txt: not valid UTF-8 (invalid continuation byte at byte 88), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_elghal.txt: not valid UTF-8 (invalid continuation byte at byte 603), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_fertile_moon.txt: not valid UTF-8 (invalid continuation byte at byte 125), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_guihar.txt: not valid UTF-8 (invalid start byte at byte 99), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_hai_jungle.txt: not valid UTF-8 (invalid continuation byte at byte 88), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_halu.txt: not valid UTF-8 (invalid start byte at byte 129), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_hengfena.txt: not valid UTF-8 (invalid continuation byte at byte 125), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_jaria.txt: not valid UTF-8 (invalid start byte at byte 260), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_maerimydra.txt: not valid UTF-8 (invalid start byte at byte 134), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_palevash.txt: not valid UTF-8 (invalid start byte at byte 255), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_quchang.txt: not valid UTF-8 (invalid start byte at byte 126), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_saigai.txt: not valid UTF-8 (invalid continuation byte at byte 126), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_sumbria.txt: not valid UTF-8 (invalid continuation byte at byte 425), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/c_wellspring_hills.txt: not valid UTF-8 (invalid start byte at byte 126), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/d_silverymoon.txt: not valid UTF-8 (invalid continuation byte at byte 1127), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/titles/k_blade_kingdoms.txt: not valid UTF-8 (invalid continuation byte at byte 101), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/1-1000 Miscellaneous.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/1001-2000 Deities.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/11001-13000 Dragon Coast and Inner Sea.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/13001-15000 Luskan.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/15001-17000 Neverwinter.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/17001-20000 Dwarves.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/20001-23000 Cormyr.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/2001-3000 Baldurs gate.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/23001-24000 Uthgardt.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/24001-26000 Impiltur.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/26001-28000 Dalelands.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/28001-30000 Tethyr.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/30001-30299 Narfelli.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/3001-5000 High Moor.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/30300-30599 Orcs.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/30600-30899 Gnomes.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/30900-31000 Thinguth.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/31001-32000 Erlkazar.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/32001-33000 Nelanther.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/33001-35000 Amn.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/35001-36000 Yikarians.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/36001-37000 Thinguth II.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/37001-38000 Tuigan.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/38001-39000 Semphar.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/39001-40000 Ra-Khati and Khazari.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/40001-40500 Mulhorand.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/40500-40749 Chessentan.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/40750-41000 Untheric.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/41001-42000 Savage Frontier.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/42001-44000 Calimshan.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/44001-45000 Arnaden.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/45001-46000 Evermeet.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/46001-47000 High Forest.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/47001-48000 Minor Elf Realms.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/48001-49000 Cormanthor.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/49001-50000 Vilhon Reach.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/50001-51000 Moonshae Isles.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/5001-7000 Silver Marches.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/51001-52000 Sembia.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/52001-52100 Thinguth.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/52101-52200 Vaasa.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/52201-52400 Shaaran.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/52401-52500 Sossrim.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/52501-52800 Ulutiun.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/52801-53000 Chult.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/53001-54000 Thay.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/54001-55000 Border Kingdoms.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/55001-56000 Dambrath.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/56001-57000 Moonsea and Zhentilar.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/57001-58000 Najara and Serpentes.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/58001-58200 Luiren.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/58201-59000 Lapaliiya.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/59001-60000 Aglarond.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/60001-60100 Shou Lung offmap.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/61001-62000 Anauroch.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/62001-63000 Zakhara.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/63001-63500 Shao Shan and Sempadan.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/63501-63700 The Vast.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/63701-64000 Damara.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/64001-64500 Halruaa.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/64501-65000 Shining Lands.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/65001-65200 Ama Basin.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/65201-65500 Rashemi.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/65501-65800 Utter East.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/65801-66200 Shou Lung.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/66201-66400 Outsiders.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/66401-67000 Elven vassals.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/67001-68000 Shining Lands II.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/68001-69000 Akota.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/69001-70000 Laerakond.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/70001-71000 Thesk.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/7001-9000 Waterdeep.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/71001-72000 Magisters.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/90000-100000 Monsters.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/9001-11000 Western Heartlands.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/99_animals.txt: not valid UTF-8 (invalid continuation byte at byte 315), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/demihuman.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/dragons.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/dwarves.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/elves.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/giants.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/human.txt: not valid UTF-8 (invalid start byte at byte 14018), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/littlefolk.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/monsters.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/outsiders.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- titles: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/common/cultures/scalykind.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- traits: creature_outsider: CK2 icon gfx/traits/creature_outsider.tga is not a .dds; CK3 reads .dds only, no icon emitted (no format conversion in the converter)
- traits: creature_slaad: CK2 icon gfx/traits/creature_slaad.tga is not a .dds; CK3 reads .dds only, no icon emitted (no format conversion in the converter)
- traits: stasis_clone: CK2 icon gfx/traits/statis_clone.tga is not a .dds; CK3 reads .dds only, no icon emitted (no format conversion in the converter)
- traits: 168 CK2 trait icons copied unchanged at 24x24; CK3 1.19 vanilla trait icons are 120x120 (gfx/interface/icons/traits/brave.dds) - the submod must rescale
- integrity same-sex spouse: 8 - fae_200 (1-1000 Miscellaneous.txt) add_spouse fae_190; fae_403 (1-1000 Miscellaneous.txt) marry fae_402; fae_20847 (20001-23000 Cormyr.txt) add_spouse fae_20848; fae_2282 (2001-3000 Baldurs gate.txt) add_spouse fae_2281; fae_33274 (33001-35000 Amn.txt) add_spouse fae_33275 (+3 more)
- CK2 character has a blank name; kept verbatim because CK3 requires the field (needs a human or an overrides row)
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/1-1000 Miscellaneous.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/1001-2000 Deities.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/11001-13000 Dragon Coast and Inner Sea.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/13001-15000 Luskan.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/15001-17000 Neverwinter.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/17001-20000 Dwarves.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/20001-23000 Cormyr.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/2001-3000 Baldurs gate.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/23001-24000 Uthgardt.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/24001-26000 Impiltur.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/26001-28000 Dalelands.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/28001-30000 Tethyr.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/30001-30299 Narfelli.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/3001-5000 High Moor.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/30300-30599 Orcs.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/30600-30899 Gnomes.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/30900-31000 Thinguth.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/31001-32000 Erlkazar.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/32001-33000 Nelanther.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/33001-35000 Amn.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/35001-36000 Yikarians.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/36001-37000 Thinguth II.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/37001-38000 Tuigan.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/38001-39000 Semphar.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/39001-40000 Ra-Khati and Khazari.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/40001-40500 Mulhorand.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/40500-40749 Chessentan.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/40750-41000 Untheric.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/41001-42000 Savage Frontier.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/42001-44000 Calimshan.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/44001-45000 Arnaden.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/45001-46000 Evermeet.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/46001-47000 High Forest.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/47001-48000 Minor Elf Realms.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/48001-49000 Cormanthor.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/49001-50000 Vilhon Reach.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/50001-51000 Moonshae Isles.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/5001-7000 Silver Marches.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/51001-52000 Sembia.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/52001-52100 Thinguth.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/52101-52200 Vaasa.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/52201-52400 Shaaran.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/52401-52500 Sossrim.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/52501-52800 Ulutiun.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/52801-53000 Chult.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/53001-54000 Thay.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/54001-55000 Border Kingdoms.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/55001-56000 Dambrath.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/56001-57000 Moonsea and Zhentilar.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- characters: /home/cvdbdo/git/paradox/ck3/wt/province-edges/Faerun/Faerun/history/characters/57001-58000 Najara and Serpentes.txt: not valid UTF-8 (invalid continuation byte at byte 3), decoded as cp1252
- … 102 more

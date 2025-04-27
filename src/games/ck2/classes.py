from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Tuple, Union, Literal, Any
from enum import Enum

# All objects in CK2

class Definition(BaseModel):
    id: int
    r: Optional[int] = None
    g: Optional[int] = None
    b: Optional[int] = None
    name: str

class OceanRegion(BaseModel):
    sea_zones:List[int] = []

class DefaultDotMap(BaseModel):
    max_provinces:int
    definitions:str = "definition.csv"
    provinces:str = "provinces.bmp"
    positions:str = "positions.txt"
    terrain:str = "terrain.bmp"
    rivers:str = "rivers.bmp"
    terrain_definition:str = "terrain.txt"
    heightmap:str = "topology.bmp"
    tree_definition:str = "trees.bmp"
    continent:str = "continent.txt"
    adjacencies:str = "adjacencies.csv"
    climate:str = "climate.txt"
    region:str = "island_region.txt"
    geographical_region:str = "geographical_region.txt"
    static:str = "statics"
    seasons:str = "seasons.txt"

    externals:List[int] = []
    sea_zones:Dict[int, List[int]] = {}
    ocean_regions:Dict[int, OceanRegion] = {}
    major_rivers: List[int] = []

    tree: List[int] = []

class Terrain(BaseModel):
    name: str
    color: Tuple[int, int, int]
    is_water: Optional[bool] = None
    movement_cost: Optional[float] = None
    supply_limit: Optional[int] = None
    bottleneck_chance: Optional[int] = None
    max_attrition: Optional[float] = None
    defence: Optional[float] = None


class LandedTitle(BaseModel):
    """
    Completed from list: https://ck2.paradoxwikis.com/Title_modding
    """
    rank: int
    title_name: str
    capital: Optional[int] = None
    color: Optional[Tuple[int, int, int]] = None
    color2: Optional[Tuple[int, int, int]] = None
    cultural_names: Optional[Dict[str, str]] = {}    
    has_top_de_jure_capital: Optional[bool] = None
    top_de_jure_capital: Optional[bool] = None
    allow: Optional[Dict] = None
    religion: Optional[str] = None
    culture: Optional[str] = None
    graphical_culture: Optional[str] = None
    landless: Optional[bool] = None
    primary: Optional[bool] = None
    title: Optional[str] = None
    title_female: Optional[str] = None
    foa: Optional[str] = None
    title_prefix: Optional[str] = None
    short_name: Optional[bool] = None
    name_tier: Optional[str] = None
    coat_of_arms: Optional[Dict] = None
    pagan_coat_of_arms: Optional[Dict] = None
    mercenary: Optional[bool] = None
    mercenary_type: Optional[str] = None
    independent: Optional[bool] = None
    holy_order: Optional[bool] = None
    modifiers: Optional[List[str]] = None
    strength_growth_per_century: Optional[float] = None
    religion_crusade_target: Optional[Dict[str, int]] = None
    religion_group_crusade_target: Optional[Dict[str, int]] = None
    male_names: Optional[List[str]] = None
    female_names: Optional[List[str]] = None
    controls_religion: Optional[str] = None
    tribe: Optional[bool] = None
    creation_requires_capital: Optional[bool] = None
    caliphate: Optional[bool] = None
    dynasty_title_names: Optional[bool] = None
    used_for_dynasty_names: Optional[bool] = None
    purple_born_heirs: Optional[bool] = None
    cultural_names: Optional[Dict[str, str]] = None
    location_ruler_title: Optional[bool] = None
    dignity: Optional[int] = None
    holy_site_for: Optional[List[str]] = None
    pentarchy: Optional[Union[bool, str]] = None
    assimilate: Optional[bool] = None
    duchy_revocation: Optional[bool] = None
    gain_effect: Optional[str] = None
    monthly_income: Optional[int] = None
    can_be_claimed: Optional[bool] = None
    can_be_usurped: Optional[bool] = None
    extra_ai_eval_troops: Optional[int] = None
    hire_range: Optional[int] = None

    children: Optional[List["LandedTitle"]] = []


class Empire(LandedTitle):
    rank: int = 1
    pass

class Kingdom(LandedTitle):
    rank: int = 2
    pass

class Duchy(LandedTitle):
    rank: int = 3
    pass

class County(LandedTitle):
    rank: int = 4
    pass

class Barony(LandedTitle):
    rank: int = 5
    pass

# TODO: Offmap powers

class Change(BaseModel):
    key: str
    value: Union[Any]

class History(BaseModel):
    history: Dict[str, List[Change]] = Field(default_factory=dict) # date: changes

class TitleChangeKeys(Enum):
    HOLDER = "holder"
    LIEGE = "liege"
    LAWS = "laws"
    HOLDING_DYNASTY = "holding_dynasty"
    ACTIVE = "active"

class TitleChange(Change):
    key: TitleChangeKeys
    value: Optional[Union[int, str, bool]] = None

class TitleHistory(History):
    changes: Dict[str, List[TitleChange]] = Field(default_factory=dict)

class CountyProvinceHistory(History):
    """
    Completed from list: https://ck2.paradoxwikis.com/Province_modding
    Ignore non active baronies
    """
    id: int
    definition_name: str
    title: Optional[str] = None
    max_settlements: Optional[int] = None
    culture: Optional[str] = None
    religion: Optional[str] = None
    terrain: Optional[str] = None
    # title, culture, religion, b_name
    # history: Dict[str, List[CountyProvinceChange]] = Field(default_factory=dict) # Changes in culture and religion

class CharacterChangeKeys(Enum):
    """
    See https://ck2.paradoxwikis.com/Character_modding
    """
    BIRTH = "birth"
    DEATH = "death"
    ADD_CLAIM = "add_claim"
    REMOVE_CLAIM = "remove_claim"
    ADD_SPOUSE = "add_spouse"
    REMOVE_SPOUSE = "remove_spouse"
    ADD_MATRILINEAL_SPOUSE = "add_matrilineal_spouse"
    ADD_CONSORT = "add_consort"
    ADD_LOVER = "add_lover"
    EMPLOYER = "employer"
    GIVE_JOB_TITLE = "give_job_title"
    GIVE_NICKNAME = "give_nickname"
    PRESTIGE = "prestige"
    PIETY = "piety"
    DECADENCE = "decadence"
    WEALTH = "wealth"
    REMOVE_TRAIT = "remove_trait"
    ADD_TRAIT = "add_trait"
    TRAIT = "trait"
    CAPITAL = "capital"
    DYNASTY = "dynasty"
    EFFECT = "effect"
    EFFECT_EVEN_IF_DEAD = "effect_even_if_dead"
    RAISE_LEVIES = "raise_levies"
    IMMORTAL_AGE = "immortal_age"

class DeathReason(BaseModel):
    """
    This or Yes
    """
    name: Optional[str] = None
    violent: Optional[bool] = None
    execution: Optional[bool] = None
    long_desc: Optional[str] = None
    death_date_desc: Optional[str] = None
    can_nokiller: Optional[bool] = None
    sounds_list: Optional[Dict[str, str]] = None # Male or Female
    icon: Optional[int] = None
    murder_unknown: Optional[bool] = None

class CharacterDeath(BaseModel):
    death_reason: str               # DeathReason.name
    killer: Optional[int] = None

class CharacterChange(Change):
    key: CharacterChangeKeys

class CharacterHistory(History):
    changes: Dict[str, List[CharacterChange]] = Field(default_factory=dict)

class Character(BaseModel):
    """
    Completed from list: https://ck2.paradoxwikis.com/Character_modding
    """
    id: int
    name: str
    female: Optional[bool] = False

    dynasty: Optional[int] = None
    father: Optional[int] = None
    real_father: Optional[int] = None
    mother: Optional[int] = None

    dna: Optional[str] = None
    properties: Optional[List[str]] = None
    
    martial: Optional[int] = None
    diplomacy: Optional[int] = None
    intrigue: Optional[int] = None
    stewardship: Optional[int] = None
    learning: Optional[int] = None
    health: Optional[int] = None
    fertility: Optional[float] = None

    religion: Optional[str] = None
    secret_religion: Optional[str] = None
    culture: Optional[str] = None
    race: Optional[str] = None
    traits: Optional[List[str]] = None
    disallow_random_traits: Optional[bool] = None
    occluded: Optional[bool] = None
    historical: Optional[bool] = None
    easter_egg: Optional[bool] = None

    history: CharacterHistory = Field(default_factory=CharacterHistory)

class Culture(BaseModel):
    """
    https://ck2.paradoxwikis.com/Culture_modding
    """
    name: str
    graphical_cultures: Optional[List[str]] = None
    unit_graphical_cultures: Optional[List[str]] = None
    secondary_event_pictures: Optional[List[str]] = None
    color: Optional[Tuple[float, float, float]] = None
    horde: Optional[bool] = None
    used_for_random: Optional[bool] = None
    allow_in_ruler_designer: Optional[bool] = None
    dukes_called_kings: Optional[bool] = None
    baron_titles_hidden: Optional[bool] = None
    count_titles_hidden: Optional[bool] = None
    parent: Optional[str] = None
    modifiers: Optional[List[str]] = None
    character_modifier: Optional[List[str]] = None
    founder_named_dynasties: Optional[bool] = None
    dynasty_title_names: Optional[bool] = None
    dishinerit_from_blinding:Optional[bool] = None
    allow_looting: Optional[bool] = None
    seafarer: Optional[bool] = None
    dynasty_name_first: Optional[bool] = None
    feminist: Optional[bool] = None

    male_patronym: Optional[str] = None
    female_patronym: Optional[str] = None
    prefix: Optional[bool] = None
    grammar_transform: Optional[str] = None

    from_dynasty_prefix: Optional[bool] = None
    from_dynasty_suffix: Optional[bool] = None
    bastard_dynasty_prefix: Optional[bool] = None

    pat_grf_name_chance: Optional[int] = None
    mat_grf_name_chance: Optional[int] = None
    father_name_chance: Optional[int] = None
    pat_grm_name_chance: Optional[int] = None
    mat_grm_name_chance: Optional[int] = None
    mother_name_chance: Optional[int] = None


class Religion(BaseModel):
    """
    https://ck2.paradoxwikis.com/Religion_modding
    """
    name: str
    ai_convert_same_group: int
    ai_convert_other_group: int
    graphical_culture: str
    icon: int
    color: Tuple[float, float, float]
    crusade_name: str
    scripture_name: str 
    god_names: List[str]
    high_god_name: str
    evil_god_names: List[str]
    piety_name: str
    priest_title: str
    investiture: bool

    # Optional
    can_demand_religious_conversions: Optional[bool] = None
    can_excommunicate: Optional[bool] = None
    can_grant_divorce: Optional[bool] = None
    can_grant_invasion_cb: Optional[bool] = None
    can_grant_claim: Optional[bool] = None
    can_call_crusade: Optional[bool] = None
    can_have_antipopes: Optional[bool] = None
    can_retire_to_monastery: Optional[bool] = None
    parent: Optional[str] = None
    priests_can_marry: Optional[bool] = None
    priests_can_inherit: Optional[bool] = None
    feminist: Optional[bool] = None
    pacifist: Optional[bool] = None
    bs_marriage: Optional[bool] = None
    pc_marriage: Optional[bool] = None
    psc_marriage: Optional[bool] = None
    cousin_marriage: Optional[bool] = None
    matrilineal_marriage: Optional[bool] = None
    intermarry_religions: Optional[List[str]] = None
    max_wives: Optional[int] = None
    allow_viking_invasion: Optional[bool] = None
    allow_looting: Optional[bool] = None
    seafarer: Optional[bool] = None
    allow_rivermovement: Optional[bool] = None
    female_temple_holder: Optional[bool] = None
    male_temple_holder: Optional[bool] = None
    short_reign_opinion_year_mult: Optional[int] = None
    aggression: Optional[float] = None
    max_consorts: Optional[int] = None
    religious_clothing_head: Optional[int] = None
    religious_clothing_priest: Optional[int] = None
    secondary_event_pictures: Optional[Any] = None
    autocephaly: Optional[bool] = None
    pentarchy: Optional[bool] = None
    divine_blood: Optional[bool] = None
    has_heir_designation: Optional[bool] = None
    ignores_defensive_attrition: Optional[bool] = None
    heresy_icon: Optional[int] = None
    independence_war_score_bonus: Optional[int] = None
    peace_prestige_loss: Optional[bool] = None
    raised_vassal_opinion_loss: Optional[bool] = None
    reformed: Optional[str] = None # Religion
    reformer_head_of_religion: Optional[bool] = None
    pre_reformed: Optional[bool] = None
    unit_modifiers: Optional[Dict[str, Any]] = None
    unit_home_modifier: Optional[Dict[str, Any]] = None
    character_modifier: Optional[Dict[str, Any]] = None
    expel_modifier: Optional[str] = None   # Modifier 
    landed_kin_prestige_bonus: Optional[bool] = None
    allow_in_ruler_designer: Optional[bool] = None
    dislike_tribal_organization: Optional[bool] = None
    uses_decadence: Optional[bool] = None
    uses_jizya_tax: Optional[bool] = None
    attacking_same_religion_piety_loss: Optional[bool] = None
    hard_to_convert: Optional[bool] = None
    men_can_take_consort: Optional[bool] = None
    women_can_take_consort: Optional[bool] = None
    interface_skin: Optional[str] = None # Interface
    castes: Optional[bool] = None
    caste_opinion: Optional[bool] = None
    has_coa_on_barony_only: Optional[bool] = None
    join_crusade_if_bordering_hostile: Optional[bool] = None
    merge_republic_interface: Optional[bool] = None
    rel_head_defense: Optional[bool] = None


class ReligionGroup(BaseModel):
    name: str
    color: Optional[Tuple[float, float, float]] = None
    graphical_culture: Optional[str] = None
    has_coa_on_barony_only: Optional[bool] = None
    hostile_within_group: Optional[bool] = None
    crusade_cb: Optional[str] = None
    playable: Optional[bool] = None
    ai_peaceful: Optional[bool] = None
    ai_fabricate_claims: Optional[bool] = None
    merge_republic_interface: Optional[bool] = None


    religions: List["Religion"] = []

# TODO: Technology
# TODO: Wr history

class Modifiers(Enum):
    """
    https://ck2.paradoxwikis.com/Modifiers#List_of_modifiers

    These have different scopes: charcater, trait, province, councillor, tech, holding, building, laws.
    The scopes are documented on the wiki.
    """
    # Character
    diplomacy = "diplomacy"
    diplomacy_penalty = "diplomacy_penalty"
    stewardship = "stewardship"
    stewardship_penalty = "stewardship_penalty"
    intrigue = "intrigue"
    intrigue_penalty = "intrigue_penalty"
    learning = "learning"
    learning_penalty = "learning_penalty"
    martial = "martial"
    martial_penalty = "martial_penalty"
    fertility = "fertility"
    fertility_penalty = "fertility_penalty"
    health = "health"
    health_penalty = "health_penalty"
    combat_rating = "combat_rating"
    threat_decay_speed = "threat_decay_speed"

    # Realm
    demesne_size = "demesne_size"
    vassal_limit = "vassal_limit"
    global_revolt_risk = "global_revolt_risk"
    local_revolt_risk = "local_revolt_risk"
    disease_defence = "disease_defence"
    culture_flex = "culture_flex"
    religion_flex = "religion_flex"
    short_reign_length = "short_reign_length"
    moved_capital_months_mult = "moved_capital_months_mult"

    # intrigue
    assassinate_chance_modifier = "assassinate_chance_modifier"
    arrest_chance_modifier = "arrest_chance_modifier"
    plot_power_modifier = "plot_power_modifier"
    murder_plot_power_modifier = "murder_plot_power_modifier"
    defensive_plot_power_modifier = "defensive_plot_power_modifier"
    plot_discovery_chance = "plot_discovery_chance"

    # wealth, prestige, piety
    tax_income = "tax_income"
    global_tax_modifier = "global_tax_modifier"
    local_tax_modifier = "local_tax_modifier"
    _holding_type_tax_modifier = "{holding_type}_tax_modifier"
    _holding_type_vassal_tax_modifier = "{holding_type}_vassal_tax_modifier"
    nomad_tax_modifier = "nomad_tax_modifier"
    monthly_character_prestige = "monthly_character_prestige"
    liege_prestige = "liege_prestige"
    add_prestige_modifier = "add_prestige_modifier"
    monthly_character_piety = "monthly_character_piety"
    liege_piety = "liege_piety"
    add_piety_modifier = "add_piety_modifier"
    monthly_character_wealth = "monthly_character_wealth"

    # AI behavior
    ai_rationality = "ai_rationality"
    ai_zeal = "ai_zeal"
    ai_greed = "ai_greed"
    ai_honor = "ai_honor"
    ai_ambition = "ai_ambition"
    ai_feudal_modifier = "ai_feudal_modifier"
    ai_republic_modifier = "ai_republic_modifier"

    # Construction
    build_cost_modifier = "build_cost_modifier"
    build_cost_castle_modifier = "build_cost_castle_modifier"
    build_cost_city_modifier = "build_cost_city_modifier"
    build_cost_temple_modifier = "build_cost_temple_modifier"
    build_cost_tribal_modifier = "build_cost_tribal_modifier"
    build_time_modifier = "build_time_modifier"
    build_time_castle_modifier = "build_time_castle_modifier"
    build_time_city_modifier = "build_time_city_modifier"
    build_time_temple_modifier = "build_time_temple_modifier"
    build_time_tribal_modifier = "build_time_tribal_modifier"
    local_build_cost_modifier = "local_build_cost_modifier"
    local_build_cost_castle_modifier = "local_build_cost_castle_modifier"
    local_build_cost_city_modifier = "local_build_cost_city_modifier"
    local_build_cost_temple_modifier = "local_build_cost_temple_modifier"
    local_build_cost_tribal_modifier = "local_build_cost_tribal_modifier"
    local_build_time_modifier = "local_build_time_modifier"
    local_build_time_castle_modifier = "local_build_time_castle_modifier"
    local_build_time_city_modifier = "local_build_time_city_modifier"
    local_build_time_temple_modifier = "local_build_time_temple_modifier"
    local_build_time_tribal_modifier = "local_build_time_tribal_modifier"

    # Opinion
    ambition_opinion = "ambition_opinion"
    vassal_opinion = "vassal_opinion"
    sex_appeal_opinion = "sex_appeal_opinion"
    same_opinion = "same_opinion"
    same_opinion_if_same_religion = "same_opinion_if_same_religion"
    opposite_opinion = "opposite_opinion"
    liege_opinion = "liege_opinion"
    general_opinion = "general_opinion"
    twin_opinion = "twin_opinion"
    dynasty_opinion = "dynasty_opinion"
    male_dynasty_opinion = "male_dynasty_opinion"
    female_dynasty_opinion = "female_dynasty_opinion"
    child_opinion = "child_opinion"
    oldest_child_opinion = "oldest_child_opinion"
    youngest_child_opinion = "youngest_child_opinion"
    spouse_opinion = "spouse_opinion"
    male_opinion = "male_opinion"
    female_opinion = "female_opinion"
    _religion_opinion = "{religion}_opinion"
    _religion_group_opinion = "{religion_group}_opinion"
    same_religion_opinion = "same_religion_opinion"
    infidel_opinion = "infidel_opinion"
    _religion_group_church_opinion = "{religion_group}_church_opinion"
    church_opinion = "church_opinion"
    temple_opinion = "temple_opinion"
    temple_all_opinion = "temple_all_opinion"
    town_opinion = "town_opinion"
    city_opinion = "city_opinion"
    castle_opinion = "castle_opinion"
    feudal_opinion = "feudal_opinion"
    tribal_opinion = "tribal_opinion"
    unreformed_tribal_opinion = "unreformed_tribal_opinion"
    rel_head_opinion = "rel_head_opinion"
    free_invest_vassal_opinion = "free_invest_vassal_opinion"
    clan_sentiment = "clan_sentiment"

    # Warfare
    levy_size = "levy_size"
    global_levy_size = "global_levy_size"
    levy_reinforce_rate = "levy_reinforce_rate"
    army_reinforce_rate = "army_reinforce_rate"
    _phase_attack = "phase_{phase}_attack"
    _phase_defense = "phase_{phase}_defense"
    _unit = "{unit}"
    _unit_max_levy = "{unit}_max_levy"
    _unit_min_levy = "{unit}_min_levy"
    _unit_offensice = "{unit}_offensice"
    _unit_defensive = "{unit}_defensive"
    _unit_morale = "{unit}_morale"
    _holding_type_levy_size = "{holding_type}_levy_size"
    _holding_type_vassal_min_levy = "{holding_type}_vassal_min_levy"
    _holding_type_vassal_max_levy = "{holding_type}_vassal_max_levy"
    land_morale = "land_morale"
    land_organisation = "land_organisation"
    regiment_reinforcement_speed = "regiment_reinforcement_speed"
    garrison_size = "garrison_size"
    global_garrison_size = "global_garrison_size"
    garrison_growth = "garrison_growth"
    fort_level = "fort_level"
    global_defensive = "global_defensive"
    land = "land"
    global_supply_limit = "global_supply_limit"
    global_winter_supply = "global_winter_supply"
    supply_limit = "supply_limit"
    max_attrition = "max_attrition"
    attrition = "attrition"
    days_of_supply = "days_of_supply"
    siege_defense = "siege_defense"
    siege_speed = "siege_speed"
    global_movement_speed = "global_movement_speed"
    local_movement_speed = "local_movement_speed"
    galleys_perc = "galleys_perc"
    retinuesize = "retinuesize"
    retinuesize_perc = "retinuesize_perc"
    retinue_maintenance_cost = "retinue_maintenance_cost"
    horde_maintenance_cost = "horde_maintenance_cost"

    # Technology
    tech_growth_modifier = "tech_growth_modifier"
    commander_limit = "commander_limit"
    _tech_growth_modifier_tech_type = "tech_growth_modifier_{tech_type}"
    _tech_type_tech_points = "{tech_type}_tech_points"

    # Trade
    max_tradeposts = "max_tradeposts"
    tradevalue = "tradevalue"
    trade_route_wealth = "trade_route_wealth"
    trade_route_value = "trade_route_value"
    global_max_tradeposts = "global_max_tradeposts"
    global_tradevalue = "global_tradevalue"
    global_trade_route_wealth = "global_trade_route_wealth"
    global_trade_route_value = "global_trade_route_value"
    multiplicative_trade_post_income_modifier = "multiplicative_trade_post_income_modifier"

    # Population

    population_growth = "population_growth"
    manpower_growth = "manpower_growth"
    max_population_mult = "max_population_mult"
    max_manpower_mult = "max_manpower_mult"
    max_population = "max_population"

class CustomModifiers(Enum):
    """
    Standardized types of modifiers
    """
    special_unit = "{special_unit}"
    special_unit_offensive = "{special_unit}_offensive"
    special_unit_defensive = "{special_unit}_defensive"
    special_unit_morale = "{special_unit}_morale"

    culture_opinion = "{culture}_opinion"
    culture_group_opinion = "{culture_group}_opinion"

    religion_opinion = "{religion}_opinion"
    religion_group_opinion = "{religion_group}_opinion"

    trait_opinion = "{trait}_opinion"
    opinion_of_trait = "opinion_of_{trait}"

class CustomModifier(BaseModel):
    """
    fromcommon/modifier_definitions/X.txt
    """
    name: str
    is_good: Optional[bool] = None
    is_monthly: Optional[bool] = None
    is_hidden: Optional[bool] = None
    max_decimals: Optional[int] = None
    show_value: Optional[bool] = None

class SpriteType(BaseModel):
    name: str
    texturefile: str

class Trait(BaseModel):
    name: str
    agnatic: Optional[bool] = None
    attribute: Optional[str] = None # Intrigue, Learning, Martial, Stewardship, Diplomacy...
    birth: Optional[float] = None
    blinding: Optional[bool] = None
    both_parent_has_trait_inherit_chance: Optional[int] = None
    cached: Optional[bool] = None
    can_hold_titles: Optional[bool] = None
    cannot_inherit: Optional[bool] = None
    cannot_marry: Optional[bool] = None
    caste_tier: Optional[int] = None
    childhood: Optional[bool] = None
    customizer: Optional[bool] = None
    education: Optional[bool] = None
    enatic: Optional[bool] = None
    hidden: Optional[bool] = None
    hidden_from_others: Optional[bool] = None
    immortal: Optional[bool] = None
    in_hiding: Optional[bool] = None
    inbred: Optional[bool] = None
    incapacitating: Optional[bool] = None
    inherit_chance: Optional[int] = None
    is_epidemic: Optional[bool] = None
    is_health: Optional[bool] = None
    is_illness: Optional[bool] = None
    is_symptom: Optional[bool] = None
    is_visible: Optional[Dict] = None
    leader: Optional[bool] = None
    leadership_traits: Optional[int] = None
    lifestyle: Optional[bool] = None
    opposites: Optional[List]= None    
    personality: Optional[bool] = None
    pilgrimage: Optional[bool] = None
    prevent_decadence: Optional[bool] = None
    priest: Optional[bool] = None
    random: Optional[bool] = None
    rebel_inherited: Optional[bool] = None
    religious: Optional[bool] = None
    religious_branch: Optional[str] = None # Religion
    ruler_designer_cost: Optional[int] = None
    same_trait_visibility: Optional[bool] = None
    succession_gfx: Optional[bool] = None
    tolerated_religious_group: Optional[Union[str, List[str]]] = None
    vice: Optional[bool] = None
    virtue: Optional[bool] = None

    modifiers: Optional[Dict[str, Any]] = None
    
    male_compliment: Optional[str] = None
    male_compliment_adj: Optional[str] = None
    female_compliment: Optional[str] = None
    female_compliment_adj: Optional[str] = None
    male_insult: Optional[str] = None
    female_insult: Optional[str] = None
    male_insult_adj: Optional[str] = None
    female_insult_adj: Optional[str] = None
    child_compliment: Optional[str] = None
    child_compliment_adj: Optional[str] = None
    child_insult: Optional[str] = None
    child_insult_adj: Optional[str] = None

    command_modifier: Optional["CommandModifier"] = None
    potential: Optional[Dict] = None

class ModifiersPrefix(Enum):
    # Special Units
    _OFFENSIVE = "_offensive"
    _DEFENSIVE = "_defensive"
    _MORALE = "_morale"

    _OPINION = "_opinion" # Culture (group), Religion (group), Trait

class ModifiersSuffix(Enum):
    OPINION_OF_ = "opinion_of_" # Trait



class VanillaModifiersIcons(Enum):
    """
    gfx/interface/modifier_icons.dds
    https://ck2.paradoxwikis.com/Modifiers#Event_modifiers
    """
    MARTIAL_POSITIVE = 1
    LEARNING_POSITIVE = 2
    DIPLOMACY_POSITIVE = 3
    STEWARDSHIP_POSITIVE = 4
    INTRIGUE_POSITIVE = 5
    MONEY_POSITIVE = 6
    PRESTIGE_POSITIVE = 7
    PIETY_POSITIVE = 8
    TITLES_POSITIVE = 9
    COUNCIL_POSITIVE = 10
    LAWS_POSITIVE = 11
    TECH_POSITIVE = 12
    MILITARY_POSITIVE = 13
    PLOTS_POSITIVE = 14
    MESSAGES_POSITIVE = 15
    DIPLOMATIC_ACTIONS_POSITIVE = 16
    CHURCH_POSITIVE = 17
    CHARACTERS_POSITIVE = 18
    MARTIAL_NEGATIVE = 19
    LEARNING_NEGATIVE = 20
    DIPLOMACY_NEGATIVE = 21
    STEWARDSHIP_NEGATIVE = 22
    INTRIGUE_NEGATIVE = 23
    MONEY_NEGATIVE = 24
    PRESTIGE_NEGATIVE = 25
    PIETY_NEGATIVE = 26
    TITLES_NEGATIVE = 27
    COUNCIL_NEGATIVE = 28
    LAWS_NEGATIVE = 29
    TECH_NEGATIVE = 30
    MILITARY_NEGATIVE = 31
    PLOTS_NEGATIVE = 32
    MESSAGES_NEGATIVE = 33
    DIPLOMATIC_ACTIONS_NEGATIVE = 34
    CHURCH_NEGATIVE = 35
    CHARACTERS_NEGATIVE = 36
    PRISON_POSITIVE = 37
    PRISON_NEGATIVE = 38
    LOVE_POSITIVE = 39
    LOVE_NEGATIVE = 40
    DEATH = 41
    DEATH_NEGATIVE = 42
    INDIAN_RELIGION = 43
    INDIAN_RELIGION_NEGATIVE = 44
    DOG = 45
    CAT = 46
    OWL = 47
    PAGAN_RELIGION = 48
    PAGAN_RELIGION_NEGATIVE = 49
    STAFF_OF_ASCLEPIUS = 50
    STAFF_OF_ASCLEPIUS_NEGATIVE = 51
    MYSTIC = 52
    MYSTIC_NEGATIVE = 53
    BONESAW = 54
    BONESAW_NEGATIVE = 55
    HORSESHOE = 56
    HORSESHOE_NEGATIVE = 57
    PARROT = 58
    HAM = 59
    HAM_NEGATIVE = 60
    ANCHOR = 61
    ANCHOR_NEGATIVE = 62
    JEWISH_RELIGION = 63
    JEWISH_RELIGION_NEGATIVE = 64
    DOG_NEGATIVE = 65
    CAT_NEGATIVE = 66
    OWL_NEGATIVE = 67
    PARROT_NEGATIVE = 68
    BED = 69
    BED_NEGATIVE = 70
    WOLF = 71
    WOLF_NEGATIVE = 72
    RAVEN = 73
    RAVEN_NEGATIVE = 74
    DEMON_HORNS = 75
    DEMON_HORNS_NEGATIVE = 76
    TRIDENT = 77
    TRIDENT_NEGATIVE = 78
    STARS = 79
    STARS_NEGATIVE = 80
    EYE = 81
    EYE_NEGATIVE = 82
    TEST_TUBES = 83
    TEST_TUBES_NEGATIVE = 84
    SCIENCE_FLASK = 85
    SCIENCE_FLASK_NEGATIVE = 86
    FLOWER = 87
    FLOWER_NEGATIVE = 88
    RATS = 89
    RATS_NEGATIVE = 90
    OTTER = 91
    OTTER_NEGATIVE = 92
    HEDGEHOG = 93
    HEDGEHOG_NEGATIVE = 94
    TAOIST = 95
    TAOIST_NEGATIVE = 96
    PAPER = 97
    PAPER_NEGATIVE = 98
    BAMBOO_BOOK = 99
    BAMBOO_BOOK_NEGATIVE = 100
    PAGODA = 101
    PAGODA_NEGATIVE = 102
    FIREWORK = 103
    FIREWORK_NEGATIVE = 104
    TORCH = 105
    TORCH_NEGATIVE = 106
    PANDA = 107
    PANDA_NEGATIVE = 108
    DRAGON = 109
    DRAGON_NEGATIVE = 110
    EAGLE = 111
    EAGLE_NEGATIVE = 112
    PREGNANCY = 113
    PREGNANCY_NEGATIVE = 114
    EVIL_SWORD = 115
    EVIL_SWORD_NEGATIVE = 116
    COMBAT_SKILL = 117
    COMBAT_SKILL_NEGATIVE = 118
    BROKEN_BONE = 119
    BROKEN_BONE_NEGATIVE = 120
    CHICKEN = 121
    CHICKEN_NEGATIVE = 122
    COMBAT_SKILL_NEW = 123
    COMBAT_SKILL_NEW_NEGATIVE = 124
    BEAR = 125
    BEAR_NEGATIVE = 126
    LION = 127
    LION_NEGATIVE = 128
    RAIN_GOOD = 129
    RAIN_GOOD_NEGATIVE = 130
    RAIN_STORM = 131
    RAIN_STORM_NEGATIVE = 132
    SUN = 133
    SUN_NEGATIVE = 134

class EventModifier(BaseModel):
    icon: Optional[str] = None
    modifiers: Optional[Dict[str, Any]] = None

class TriggeredModifier(BaseModel):
    potential: Dict
    trigger: Dict
    icon: int
    active: bool
    modifiers: Dict[str, Any]

class ReligionModifier(BaseModel):
    authority: int
    years: int

# Skipped: Society modifiers

class OpinionModifier(BaseModel):
    opinion: float
    years: Optional[int] = None
    months: Optional[int] = None
    inherit: Optional[bool] = None
    decay: Optional[bool] = None
    revoke_reason: Optional[bool] = None
    prison_reason: Optional[bool] = None
    execute_reason: Optional[bool] = None
    banish_reason: Optional[bool] = None
    preparing_adventure_against_me: Optional[bool] = None
    preparing_invasion: Optional[bool] = None
    enemy: Optional[bool] = None
    crime: Optional[bool] = None
    disable_non_aggression_pact: Optional[bool] = None
    non_aggression_pact: Optional[bool] = None
    obedient: Optional[bool] = None
    non_interference: Optional[bool] = None

class CommandModifier(BaseModel):
    morale_offense: Optional[float] = None
    morale_defense: Optional[float] = None
    defense: Optional[float] = None
    speed: Optional[float] = None
    retreat: Optional[float] = None
    damage: Optional[float] = None
    siege: Optional[float] = None
    random: Optional[float] = None
    flank: Optional[float] = None
    center: Optional[float] = None
    cavalry: Optional[float] = None
    religious_enemy: Optional[float] = None
    terrain: Optional[Union[str, List[str]]] = None
    narrow_flank: Optional[float] = None
    winter_supply: Optional[float] = None
    winter_combat: Optional[float] = None
    phase_effects: Optional[Dict[str, float]] = None
    unit_type_effects: Optional[Dict[str, float]] = None

class Event(BaseModel):
    name: str

title_from_id = {
    "e": Empire,
    "k": Kingdom,
    "d": Duchy,
    "c": County,
    "b": Barony
}
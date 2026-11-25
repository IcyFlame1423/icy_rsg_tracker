"""All vanilla advancements in Minecraft 1.16.1, in in-game tab order.

Each one gets a column in runs.csv, named by its id without the
"minecraft:" prefix (e.g. "story/iron_tools").
"""

ADVANCEMENTS = [
    # Minecraft (story)
    "story/root", "story/mine_stone", "story/upgrade_tools", "story/smelt_iron",
    "story/obtain_armor", "story/lava_bucket", "story/iron_tools", "story/deflect_arrow",
    "story/form_obsidian", "story/mine_diamond", "story/enter_the_nether", "story/shiny_gear",
    "story/enchant_item", "story/cure_zombie_villager", "story/follow_ender_eye",
    "story/enter_the_end",
    # Nether
    "nether/root", "nether/return_to_sender", "nether/find_bastion",
    "nether/obtain_ancient_debris", "nether/fast_travel", "nether/find_fortress",
    "nether/obtain_crying_obsidian", "nether/distract_piglin", "nether/ride_strider",
    "nether/uneasy_alliance", "nether/loot_bastion", "nether/use_lodestone",
    "nether/netherite_armor", "nether/get_wither_skull", "nether/obtain_blaze_rod",
    "nether/charge_respawn_anchor", "nether/explore_nether", "nether/summon_wither",
    "nether/brew_potion", "nether/create_beacon", "nether/all_potions",
    "nether/create_full_beacon", "nether/all_effects",
    # The End
    "end/root", "end/kill_dragon", "end/dragon_egg", "end/enter_end_gateway",
    "end/respawn_dragon", "end/dragon_breath", "end/find_end_city", "end/elytra",
    "end/levitate",
    # Adventure
    "adventure/root", "adventure/voluntary_exile", "adventure/kill_a_mob", "adventure/trade",
    "adventure/honey_block_slide", "adventure/ol_betsy", "adventure/sleep_in_bed",
    "adventure/hero_of_the_village", "adventure/throw_trident", "adventure/shoot_arrow",
    "adventure/kill_all_mobs", "adventure/totem_of_undying", "adventure/summon_iron_golem",
    "adventure/two_birds_one_arrow", "adventure/whos_the_pillager_now",
    "adventure/arbalistic", "adventure/adventuring_time", "adventure/very_very_frightening",
    "adventure/sniper_duel", "adventure/bullseye",
    # Husbandry
    "husbandry/root", "husbandry/safely_harvest_honey", "husbandry/breed_an_animal",
    "husbandry/tame_an_animal", "husbandry/fishy_business", "husbandry/silk_touch_nest",
    "husbandry/plant_seed", "husbandry/bred_all_animals", "husbandry/complete_catalogue",
    "husbandry/tactical_fishing", "husbandry/balanced_diet",
    "husbandry/obtain_netherite_hoe",
]

ADVANCEMENT_SET = frozenset(ADVANCEMENTS)

# In-game titles (1.16), for showing advancements to people.
NAMES = {
    "story/root": "Minecraft", "story/mine_stone": "Stone Age",
    "story/upgrade_tools": "Getting an Upgrade", "story/smelt_iron": "Acquire Hardware",
    "story/obtain_armor": "Suit Up", "story/lava_bucket": "Hot Stuff",
    "story/iron_tools": "Isn't It Iron Pick", "story/deflect_arrow": "Not Today, Thank You",
    "story/form_obsidian": "Ice Bucket Challenge", "story/mine_diamond": "Diamonds!",
    "story/enter_the_nether": "We Need to Go Deeper", "story/shiny_gear": "Cover Me with Diamonds",
    "story/enchant_item": "Enchanter", "story/cure_zombie_villager": "Zombie Doctor",
    "story/follow_ender_eye": "Eye Spy", "story/enter_the_end": "The End?",
    "nether/root": "Nether", "nether/return_to_sender": "Return to Sender",
    "nether/find_bastion": "Those Were the Days", "nether/obtain_ancient_debris": "Hidden in the Depths",
    "nether/fast_travel": "Subspace Bubble", "nether/find_fortress": "A Terrible Fortress",
    "nether/obtain_crying_obsidian": "Who is Cutting Onions?", "nether/distract_piglin": "Oh Shiny",
    "nether/ride_strider": "This Boat Has Legs", "nether/uneasy_alliance": "Uneasy Alliance",
    "nether/loot_bastion": "War Pigs", "nether/use_lodestone": "Country Lode, Take Me Home",
    "nether/netherite_armor": "Cover Me in Debris", "nether/get_wither_skull": "Spooky Scary Skeleton",
    "nether/obtain_blaze_rod": "Into Fire", "nether/charge_respawn_anchor": 'Not Quite "Nine" Lives',
    "nether/explore_nether": "Hot Tourist Destinations", "nether/summon_wither": "Withering Heights",
    "nether/brew_potion": "Local Brewery", "nether/create_beacon": "Bring Home the Beacon",
    "nether/all_potions": "A Furious Cocktail", "nether/create_full_beacon": "Beaconator",
    "nether/all_effects": "How Did We Get Here?",
    "end/root": "The End", "end/kill_dragon": "Free the End", "end/dragon_egg": "The Next Generation",
    "end/enter_end_gateway": "Remote Getaway", "end/respawn_dragon": "The End... Again...",
    "end/dragon_breath": "You Need a Mint", "end/find_end_city": "The City at the End of the Game",
    "end/elytra": "Sky's the Limit", "end/levitate": "Great View From Up Here",
    "adventure/root": "Adventure", "adventure/voluntary_exile": "Voluntary Exile",
    "adventure/kill_a_mob": "Monster Hunter", "adventure/trade": "What a Deal!",
    "adventure/honey_block_slide": "Sticky Situation", "adventure/ol_betsy": "Ol' Betsy",
    "adventure/sleep_in_bed": "Sweet Dreams", "adventure/hero_of_the_village": "Hero of the Village",
    "adventure/throw_trident": "A Throwaway Joke", "adventure/shoot_arrow": "Take Aim",
    "adventure/kill_all_mobs": "Monsters Hunted", "adventure/totem_of_undying": "Postmortal",
    "adventure/summon_iron_golem": "Hired Help", "adventure/two_birds_one_arrow": "Two Birds, One Arrow",
    "adventure/whos_the_pillager_now": "Who's the Pillager Now?", "adventure/arbalistic": "Arbalistic",
    "adventure/adventuring_time": "Adventuring Time",
    "adventure/very_very_frightening": "Very Very Frightening",
    "adventure/sniper_duel": "Sniper Duel", "adventure/bullseye": "Bullseye",
    "husbandry/root": "Husbandry", "husbandry/safely_harvest_honey": "Bee Our Guest",
    "husbandry/breed_an_animal": "The Parrots and the Bats", "husbandry/tame_an_animal": "Best Friends Forever",
    "husbandry/fishy_business": "Fishy Business", "husbandry/silk_touch_nest": "Total Beelocation",
    "husbandry/plant_seed": "A Seedy Place", "husbandry/bred_all_animals": "Two by Two",
    "husbandry/complete_catalogue": "A Complete Catalogue", "husbandry/tactical_fishing": "Tactical Fishing",
    "husbandry/balanced_diet": "A Balanced Diet", "husbandry/obtain_netherite_hoe": "Serious Dedication",
}

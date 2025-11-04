# zork/world.py

WORLD = {
    # — Above ground —
    "west_of_house": {
        "name": "West of House",
        "desc": "You are standing in an open field west of a white house, with a boarded front door.",
        "exits": {"east": "south_of_house", "north": "forest", "south": "forest"},
        "items": [],
        "props": {}
    },
    "south_of_house": {
        "name": "South of House",
        "desc": "You are facing the south side of a white house. There is a small window here.",
        "exits": {"west": "west_of_house", "east": "behind_house", "north": "kitchen"},
        "items": [],
        "props": {}
    },
    "behind_house": {
        "name": "Behind House",
        "desc": "You are behind the white house. A path leads into the forest.",
        "exits": {"west": "south_of_house", "north": "forest"},
        "items": [],
        "props": {}
    },
    "forest": {
        "name": "Forest",
        "desc": "This is a dimly lit forest, with large trees all around.",
        "exits": {"south": "south_of_house", "west": "west_of_house"},
        "items": [],
        "props": {}
    },

    # — House —
    "kitchen": {
        "name": "Kitchen",
        "desc": "A kitchen with a table. A dark and narrow chimney leads up. A doorway leads west.",
        "exits": {"west": "living_room", "down": "cellar"},
        "items": ["leaflet"],
        "props": {}
    },
    "living_room": {
        "name": "Living Room",
        "desc": "You are in the living room. There is a trophy case here and a rug on the floor.",
        "exits": {"east": "kitchen", "up": "attic"},
        "items": ["lamp", "sword"],
        "props": {"trap_door": {"open": False}}
    },
    "attic": {
        "name": "Attic",
        "desc": "The attic is dark and cluttered.",
        "exits": {"down": "living_room"},
        "items": ["key"],
        "props": {}
    },

    # — Early underground —
    "cellar": {
        "name": "Cellar",
        "desc": "You are in a dark and damp cellar. Passages lead east and north.",
        "exits": {"up": "kitchen", "east": "troll_room", "north": "e_w_passage"},
        "items": [],
        "props": {}
    },
    "troll_room": {
        "name": "Troll Room",
        "desc": "A nasty troll lurks here. Passages lead west and east.",
        "exits": {"west": "cellar", "east": "e_w_passage"},
        "items": [],
        "props": {}
    },
    "e_w_passage": {
        "name": "East–West Passage",
        "desc": "A narrow passage running east–west.",
        "exits": {"west": "cellar", "east": "round_room", "south": "troll_room"},
        "items": [],
        "props": {}
    },
    "round_room": {
        "name": "Round Room",
        "desc": "You are in a circular stone chamber with several exits.",
        "exits": {"west": "e_w_passage", "east": "loud_room"},
        "items": [],
        "props": {}
    },
    "loud_room": {
        "name": "Loud Room",
        "desc": "The acoustics make every sound painfully loud.",
        "exits": {"west": "round_room"},
        "items": [],
        "props": {}
    },
}

DIRS = {
    "n":"north","s":"south","e":"east","w":"west","u":"up","d":"down",
    "north":"north","south":"south","east":"east","west":"west","up":"up","down":"down",
    "go":"go","move":"go","walk":"go",
    "take":"take","get":"take","pick":"take","grab":"take",
    "drop":"drop","leave":"drop",
    "open":"open","unlock":"unlock","use":"use","read":"read","look":"look","examine":"look",
    "inv":"inventory","i":"inventory","inventory":"inventory",
    "light":"light","lamp":"lamp","quit":"quit",
}

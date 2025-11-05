import os
BASE_DIR   = os.path.dirname(__file__)
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
LOC_DIR    = os.path.join(ASSETS_DIR, "locations")
ITEM_DIR   = os.path.join(ASSETS_DIR, "items")

ROOM_IMAGE = {
    "west_of_house": "west_of_house",
    "south_of_house": "south_of_house",
    "behind_house": "behind_house",
    "forest": "forest",
    "kitchen": "kitchen",
    "living_room": "living_room",
    "attic": "attic",
    "cellar": "cellar",
    "troll_room": "troll_room",
    "e_w_passage": "east_west_passage",
    "round_room": "round_room",
    "loud_room": "loud_room",
}

ITEM_IMAGE = {
    "lamp": "lantern",   # återanvänd din lantern.png
    "leaflet": "note",
    "sword": "sword",
    "key": "key",
    "gem": "gem",
}

# UI-konstanter
CRT_BG   = "#0e1a0e"
CRT_FG   = "#c8ffb0"
CRT_DIM  = "#1a2d1a"
CRT_GRID = "#143014"
LOGW, LOGH = 800, 520
LOC_W, LOC_H = 512, 342
LOC_X, LOC_Y = 100, 50
INV_H = 80
INV_Y = LOGH - INV_H
INV_PAD = 10
ICON_SIZE = 56

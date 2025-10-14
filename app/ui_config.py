#!/usr/bin/env python3
"""
UI config: enum hiển thị và helper legend/item config
"""

from typing import Dict, Tuple
from enum import Enum


class MapElement(Enum):
    WALL = "W"
    CHEST = "C"
    BOMB = "BOMB"
    ITEM_SPEED = "SPEED"
    ITEM_BOMB = "BOMB_COUNT"
    ITEM_FLAME = "EXPLOSION_RANGE"
    EMPTY = ""


class DisplayChar(Enum):
    WALL = "w"
    CHEST = "r"
    BOMB = "B"
    ITEM_SPEED = "g"
    ITEM_BOMB = "c"
    ITEM_FLAME = "l"
    EMPTY = "0"


class DisplayPriority(Enum):
    BOMB = 1
    ITEMS = 2
    CHEST = 3
    BASIC_BLOCKS = 4


DISPLAY_CHARS = {
    MapElement.WALL: DisplayChar.WALL,
    MapElement.CHEST: DisplayChar.CHEST,
    MapElement.BOMB: DisplayChar.BOMB,
    MapElement.ITEM_SPEED: DisplayChar.ITEM_SPEED,
    MapElement.ITEM_BOMB: DisplayChar.ITEM_BOMB,
    MapElement.ITEM_FLAME: DisplayChar.ITEM_FLAME,
    MapElement.EMPTY: DisplayChar.EMPTY,
}


DISPLAY_PRIORITIES = {
    DisplayChar.BOMB: DisplayPriority.BOMB,
    DisplayChar.ITEM_SPEED: DisplayPriority.ITEMS,
    DisplayChar.ITEM_BOMB: DisplayPriority.ITEMS,
    DisplayChar.ITEM_FLAME: DisplayPriority.ITEMS,
    DisplayChar.CHEST: DisplayPriority.CHEST,
    DisplayChar.WALL: DisplayPriority.BASIC_BLOCKS,
    DisplayChar.EMPTY: DisplayPriority.BASIC_BLOCKS,
}


ITEM_TYPES = {
    "SPEED": {
        "display_char": DisplayChar.ITEM_SPEED,
        "priority": DisplayPriority.ITEMS,
        "description": "Item giày có lợi",
    },
    "BOMB_COUNT": {
        "display_char": DisplayChar.ITEM_BOMB,
        "priority": DisplayPriority.ITEMS,
        "description": "Item bom có lợi",
    },
    "EXPLOSION_RANGE": {
        "display_char": DisplayChar.ITEM_FLAME,
        "priority": DisplayPriority.ITEMS,
        "description": "Item lửa có lợi",
    },
}


MAP_LEGEND = {
    DisplayChar.WALL: "tường",
    DisplayChar.CHEST: "rương",
    DisplayChar.BOMB: "bom nguy hiểm",
    DisplayChar.ITEM_SPEED: "giày có lợi",
    DisplayChar.ITEM_BOMB: "item bom có lợi",
    DisplayChar.ITEM_FLAME: "lửa có lợi",
    DisplayChar.EMPTY: "trống",
}


def get_display_char(element: MapElement) -> str:
    return DISPLAY_CHARS.get(element, DisplayChar.EMPTY).value


def get_display_priority(char: str) -> int:
    return DISPLAY_PRIORITIES.get(DisplayChar(char), DisplayPriority.BASIC_BLOCKS).value


def get_legend_text() -> str:
    parts = []
    for char, description in MAP_LEGEND.items():
        parts.append(f"{char.value}={description}")
    return ", ".join(parts)


def get_item_config(item_type: str) -> Dict:
    return ITEM_TYPES.get(
        item_type,
        {
            "display_char": DisplayChar.EMPTY,
            "priority": DisplayPriority.BASIC_BLOCKS,
            "description": "item khác",
        },
    )



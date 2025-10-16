#!/usr/bin/env python3
"""
Cấu hình game và hằng số
"""

import os

# ---------- Biến môi trường / Runtime ----------
SOCKET_SERVER = os.getenv("SOCKET_SERVER", "http://localhost:3000")
TOKEN = os.getenv("TOKEN", "DEV_TOKEN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
TICK_HZ = float(os.getenv("TICK_HZ", "96"))  # Nhịp vòng lặp AI
MAX_CMDS_PER_SEC = float(os.getenv("MAX_CMDS_PER_SEC", "58"))  # Giới hạn lệnh move/s
BOT_NAME = os.getenv("BOT_NAME", "Docker")

# ---------- Config Log ----------
LOG_MOVEMENT = os.getenv("LOG_MOVEMENT", "true").lower() == "true"
LOG_ITEMS = os.getenv("LOG_ITEMS", "false").lower() == "true"
LOG_BOMBS = os.getenv("LOG_BOMBS", "false").lower() == "true"
LOG_CHESTS = os.getenv("LOG_CHESTS", "false").lower() == "true"
LOG_MAP = os.getenv("LOG_MAP", "true").lower() == "true"
LOG_AI = os.getenv("LOG_AI", "true").lower() == "true"
LOG_SOCKET = os.getenv("LOG_SOCKET", "false").lower() == "true"
LOG_GAME_EVENTS = os.getenv("LOG_GAME_EVENTS", "true").lower() == "true"
LOG_ITEM_COLLECTION = os.getenv("LOG_ITEM_COLLECTION", "false").lower() == "true"
LOG_BOMB_EVENTS = os.getenv("LOG_BOMB_EVENTS", "true").lower() == "true"
LOG_ARRIVAL_CHECK = os.getenv("LOG_ARRIVAL_CHECK", "true").lower() == "true"

# ---------- Hằng số game ----------
# Kích thước map (theo spec: 640x640 px)
MAP_WIDTH = 640
MAP_HEIGHT = 640

# Kích thước entity (theo spec)
BOT_SIZE = 35                    # Bot: 35x35 px
BOMB_SIZE = 40                   # Bom: 40x40 px
CHEST_SIZE = 40                  # Rương: 40x40 px
ITEM_SIZE = 40                   # Item: 40x40 px
WALL_SIZE = 40                   # Tường: 40x40 px

# Kích thước ô lưới (theo spec: 40x40 px)
CELL_SIZE = 40

# Cơ chế game (theo spec)
DEFAULT_EXPLOSION_RANGE = 2      # Tầm nổ mặc định = 2 ô
BOMB_LIFETIME = 5.0             # Bom nổ sau 5s
MAX_BOT_SPEED = 3               # Tốc độ tối đa sau SPEED items (3px/bước)
MIN_BOT_SPEED = 1               # Tốc độ mặc định (1px/bước)
MOVE_PIXELS_PER_STEP = 1        # Mỗi lần di chuyển = 1px
CELL_SIZE_PIXELS = 40           # Mỗi ô = 40px

# Hằng số chiến lược sinh tồn
SAFETY_MARGIN_MS = 150          # Margin an toàn 150ms
COLLISION_PADDING = 17.5        # Phồng vật cản 17.5px mỗi phía
LANE_CENTER_OFFSET = 20         # Tâm ô = 20 + 40*k

# ---------- Tham số điều chỉnh chuyển động (tunables) ----------
# Ngưỡng coi như đã tới đích theo trục di chuyển (tránh rung biên)
ARRIVAL_TOLERANCE_PX = float(os.getenv("ARRIVAL_TOLERANCE_PX", "3.0"))
# Thời gian khóa hướng ngược lại sau khi tới đích (chống đảo chiều)
REVERSE_LOCK_SECONDS = float(os.getenv("REVERSE_LOCK_SECONDS", "0.2"))
# Biên căn thẳng hàng trước khi rẽ theo trục vuông góc; mặc định = 15.1px
PREALIGN_MARGIN_PX = float(os.getenv("PREALIGN_MARGIN_PX", "15.1"))

# Loại item và thông tin
ITEM_TYPES = {
    "SPEED": 0,           # Ưu tiên 0 (cao nhất) - Giày speed
    "EXPLOSION_RANGE": 1, # Ưu tiên 1 - Liệt hỏa
    "BOMB_COUNT": 2,      # Ưu tiên 2 - Đa bom
}

# Thông tin vật phẩm
ITEM_INFO = {
    "SPEED": {
        "name": "Giày Speed",
        "description": "Tăng tốc độ di chuyển (+1), tốc độ tối đa là 3",
        "effect": "speed",
        "max_count": 5,
        "priority": 100
    },
    "EXPLOSION_RANGE": {
        "name": "Liệt Hỏa", 
        "description": "Cho phép bom nổ dài hơn theo 4 hướng (mỗi hướng +1)",
        "effect": "explosion_range",
        "max_count": 5,
        "priority": 90
    },
    "BOMB_COUNT": {
        "name": "Đa Bom",
        "description": "Tăng số lượng bom tối đa (+1 bom)",
        "effect": "bomb_count", 
        "max_count": 5,
        "priority": 80
    }
}

# Loại ô map
CELL_TYPES = {
    "WALL": "W",
    "CHEST": "C", 
    "FREE": None,
}

# Hướng di chuyển
DIRECTIONS = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0)
}
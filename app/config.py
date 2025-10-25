#!/usr/bin/env python3
import os

# ---------- Biến môi trường / Runtime ----------
SOCKET_SERVER = os.getenv("SOCKET_SERVER", "http://localhost:3000")
TOKEN = os.getenv("TOKEN", "DEV_TOKEN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
TICK_HZ = float(os.getenv("TICK_HZ", "64"))  # Nhịp vòng lặp AI (tối ưu: 64Hz ≈ 15.6ms/tick, khớp với 58 cmd/s ≈ 17.2ms/cmd)
MAX_CMDS_PER_SEC = float(os.getenv("MAX_CMDS_PER_SEC", "58"))  # Giới hạn lệnh move/s
BOT_NAME = os.getenv("BOT_NAME", "Docker")

# ---------- Config Log ----------
LOG_MOVEMENT = False
LOG_MAP = True
LOG_SOCKET = False
LOG_GAME_EVENTS = True
LOG_ITEM_COLLECTION = False
LOG_BOMB_EVENTS = False
LOG_ARRIVAL_CHECK = False

# ---------- Hằng số game ----------
# Kích thước map (theo spec: 640x640 px)
MAP_WIDTH = 640
MAP_HEIGHT = 640

# Kích thước entity (theo spec)
BOT_SIZE = 35                    # Bot: 35x35 px

# Kích thước ô lưới (theo spec: 40x40 px)
CELL_SIZE = 40
CELL_SIZE_PIXELS = 40           # Mỗi ô = 40px

# ---------- Tham số điều chỉnh chuyển động (tunables) ----------
# Thời gian khóa hướng ngược lại sau khi tới đích (chống đảo chiều)
REVERSE_LOCK_SECONDS = float(os.getenv("REVERSE_LOCK_SECONDS", "0.2"))

# Hướng di chuyển
DIRECTIONS = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0)
}
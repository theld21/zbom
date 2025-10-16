#!/usr/bin/env python3
"""
Quản lý trạng thái game
"""

from typing import Dict, Any, List, Optional, Tuple, Iterable, Set
from collections import deque
import time
import logging
from dataclasses import dataclass, field
import numpy as np

from .config import CELL_SIZE, MAP_WIDTH, MAP_HEIGHT, MAX_CMDS_PER_SEC, BOT_SIZE

logger = logging.getLogger(__name__)

# ---------- Trạng thái game toàn cục ----------
game_state: Dict[str, Any] = {
    "connected": False,
    "my_uid": None,
    "game_started": False,
    "map": [],
    "bombers": [],
    "bombs": [],
    "items": [],
    "chests": [],
    "last_bomb_explosions": [],
    "active_bombs": [],  # Danh sách bom đang hoạt động
}

# Giới hạn tốc độ lệnh
last_cmd_times: deque = deque(maxlen=100)

def can_send_command() -> bool:
    """Giới hạn tốc độ theo MAX_CMDS_PER_SEC"""
    now = time.monotonic()
    # Xóa các lệnh cũ hơn 1s
    while last_cmd_times and now - last_cmd_times[0] > 1.0:
        last_cmd_times.popleft()
    
    can_send = len(last_cmd_times) < MAX_CMDS_PER_SEC
    if can_send:
        last_cmd_times.append(now)
    
    return can_send

def get_grid_size() -> Tuple[int, int]:
    """Lấy kích thước lưới (width, height)"""
    mp = game_state.get("map") or []
    return (len(mp[0]) if mp else 0, len(mp))

def pos_to_cell(x: float, y: float) -> Tuple[float, float]:
    """
    Chuyển vị trí pixel (TOP-LEFT của bot) thành tọa độ ô lưới.
    
    === QUAN TRỌNG: TẤT CẢ TỌA ĐỘ TỪ SERVER ĐỀU LÀ TOP-LEFT (góc trên trái) ===
    
    Map: 640x640px, chia thành 16x16 cells, mỗi cell 40x40px
    - Cell 0: pixel từ 0-39 (bot cho là đã tới ô này phải có vị trí 0 đến 5, khi này trả về 0), nếu nằm từ 6 đến 39 thì trả về 0.5
    - Cell 1: pixel từ 40-79 (bot cho là đã tới ô này phải có vị trí 40 đến 45, khi này trả về 1), nếu nằm từ 46 đến 79 thì trả về 1.5
    - Cell 2: pixel từ 80-119 (bot cho là đã tới ô này phải có vị trí 80 đến 85, khi này trả về 2), nếu nằm từ 86 đến 119 thì trả về 2.5
    - ...
    - Cell 15: pixel từ 600-639 (bot cho là đã tới ô này phải có vị trí 600 đến 605, khi này trả về 15), nếu nằm từ 606 đến 639 thì trả về 15.5
    
    Bot: 35x35px
    - Server trả về (x, y) = top-left của bot, check như logic bên trên đã note
    
    """
    from .config import CELL_SIZE
    
    # Logic mới: Trả về float để biểu diễn vị trí chính xác trong cell
    # 
    # VD: Cell 1 (40-79px)
    # - x=40-45 → trả về 1.0 (đã tới chính xác)
    # - x=46-79 → trả về 1.5 (đang ở giữa cell)
    # 
    # VD: Cell 2 (80-119px)  
    # - x=80-85 → trả về 2.0 (đã tới chính xác)
    # - x=86-119 → trả về 2.5 (đang ở giữa cell)
    
    # Tính cell base
    cell_x = x // CELL_SIZE
    cell_y = y // CELL_SIZE
    
    # Tính offset trong cell (0-39px)
    offset_x = x % CELL_SIZE
    offset_y = y % CELL_SIZE
    
    # Logic: Nếu offset <= 5px → đã tới chính xác (số nguyên)
    # Nếu offset > 5px → đang ở giữa cell (số lẻ .5)
    if offset_x <= 5:
        cx = cell_x
    else:
        cx = cell_x + 0.5
        
    if offset_y <= 5:
        cy = cell_y  
    else:
        cy = cell_y + 0.5
    
    # Clamp vào range hợp lệ (0-15.5)
    cx = max(0, min(15.5, cx))
    cy = max(0, min(15.5, cy))
    
    return (cx, cy)

def pos_to_cell_entity(x: float, y: float) -> Tuple[int, int]:
    """
    Chuyển pixel thành cell cho entity 40x40px (BOM, ITEM, CHEST).
    
    Entity 40x40px = đúng bằng CELL_SIZE → Dùng floor(x/40) thuần túy
    Không cần offset vì entity chiếm ĐÚNG 1 cell!
    """
    from .config import CELL_SIZE
    
    cx = int(x // CELL_SIZE)
    cy = int(y // CELL_SIZE)
    
    # Clamp vào range hợp lệ (0-15)
    cx = max(0, min(15, cx))
    cy = max(0, min(15, cy))
    
    return (cx, cy)

def pos_to_cell_bot(x: float, y: float) -> Tuple[int, int]:
    """Phân loại tile của bot dựa trên góc trên trái (top-left): floor(x/40), floor(y/40)."""
    return pos_to_cell(x, y)

def pos_to_cell_int(x: float, y: float) -> Tuple[int, int]:
    """Chuyển pixel thành cell integer (cho pathfinding, map display)"""
    cell_x, cell_y = pos_to_cell(x, y)
    return (int(cell_x), int(cell_y))

def is_at_exact_cell(x: float, y: float) -> bool:
    """Kiểm tra bot có đang ở chính xác cell không (số nguyên)"""
    cell_x, cell_y = pos_to_cell(x, y)
    return (
        isinstance(cell_x, int) or cell_x.is_integer() and
        isinstance(cell_y, int) or cell_y.is_integer()
    )

def cell_to_pos(cx: int, cy: int) -> Tuple[int, int]:
    """Chuyển ô lưới thành vị trí pixel (tâm ô)"""
    return (cx * CELL_SIZE + CELL_SIZE // 2, cy * CELL_SIZE + CELL_SIZE // 2)

def cell_top_left_pos(cx: int, cy: int) -> Tuple[int, int]:
    """Trả về tọa độ pixel của góc trên trái của ô (neo top-left)."""
    return (cx * CELL_SIZE, cy * CELL_SIZE)

def in_bounds(cx: int, cy: int) -> bool:
    """Kiểm tra tọa độ ô có trong map không (1-14)"""
    return 1 <= cx <= 14 and 1 <= cy <= 14

def in_pixel_bounds(x: float, y: float) -> bool:
    """Kiểm tra vị trí pixel có trong map không"""
    return 0 <= x < MAP_WIDTH and 0 <= y < MAP_HEIGHT

def is_blocked_cell(cell: Optional[str]) -> bool:
    """Kiểm tra ô có chặn di chuyển không (tường và rương)"""
    return cell in ("W", "r")  # W=tường, r=rương

def is_passable(cx: int, cy: int) -> bool:
    """Kiểm tra ô có thể đi qua không"""
    mp = game_state.get("map") or []
    if not in_bounds(cx, cy):
        return False
    
    # Kiểm tra kích thước map
    if not mp or len(mp) <= cy or len(mp[cy]) <= cx:
        # Không log warning nếu map đang được reset (sau khi hồi sinh)
        if len(mp) == 0:
            logger.debug(f"🗺️ MAP RESET: Map đang được reset, tạm coi ô ({cx}, {cy}) là không thể đi")
        else:
            logger.warning(f"⚠️ MAP SIZE ERROR: mp={len(mp)}x{len(mp[0]) if mp else 'empty'}, trying to access ({cx}, {cy})")
        return False
        
    cell = mp[cy][cx]
    return not is_blocked_cell(cell)

def get_neighbors(cx: int, cy: int) -> List[Tuple[int, int]]:
    """Lấy các ô lân cận có thể đi qua"""
    neighbors = [(cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)]
    return [(x, y) for (x, y) in neighbors if in_bounds(x, y) and is_passable(x, y)]

def get_bomber_by_uid(uid: str) -> Optional[Dict[str, Any]]:
    """Lấy dữ liệu bomber theo UID"""
    for bomber in game_state.get("bombers", []):
        if bomber.get("uid") == uid:
            return bomber
    return None

def get_my_bomber() -> Optional[Dict[str, Any]]:
    """Lấy dữ liệu bot hiện tại"""
    uid = game_state.get("my_uid")
    if not uid:
        return None
    return get_bomber_by_uid(uid)

def get_my_cell() -> Optional[Tuple[int, int]]:
    """Lấy vị trí ô của bot hiện tại"""
    me = get_my_bomber()
    if not me:
        return None
    return pos_to_cell_bot(me.get("x", 0), me.get("y", 0))

def get_bomber_explosion_range(uid: str) -> int:
    """Lấy tầm nổ của bomber"""
    bomber = get_bomber_by_uid(uid)
    if bomber and isinstance(bomber.get("explosionRange"), (int, float)):
        return int(bomber["explosionRange"])
    return 2  # Tầm nổ mặc định

def get_bomber_speed(uid: str) -> int:
    """Lấy tốc độ của bot (1, 2, hoặc 3) - số pixel mỗi bước"""
    bomber = get_bomber_by_uid(uid)
    if bomber and isinstance(bomber.get("speed"), (int, float)):
        # Theo format từ server: speed = 1, 2, 3
        return min(3, max(1, int(bomber["speed"])))
    return 1

def get_bomber_speed_count(uid: str) -> int:
    """Lấy số lượng item SPEED đã nhặt"""
    bomber = get_bomber_by_uid(uid)
    if bomber and isinstance(bomber.get("speedCount"), (int, float)):
        return int(bomber["speedCount"])
    return 0

def get_bomber_bomb_count(uid: str) -> int:
    """Lấy số bom của bomber"""
    bomber = get_bomber_by_uid(uid)
    if bomber and isinstance(bomber.get("bombCount"), (int, float)):
        return int(bomber["bombCount"])
    return 1

def get_explosion_history() -> list:
    """Lấy lịch sử nổ bom để học phạm vi nổ thực tế"""
    return game_state.get("explosion_history", [])

def get_item_tile_map() -> dict:
    return game_state.get("item_tile_map", {})

def get_chest_tile_map() -> dict:
    return game_state.get("chest_tile_map", {})

def get_bomb_tile_map() -> dict:
    return game_state.get("bomb_tile_map", {})

def create_tile_map(items: list, key_func, value_func) -> dict:
    """
    Tạo bản đồ tile từ danh sách items một cách tối ưu
    
    Args:
        items: Danh sách items
        key_func: Hàm tạo key từ item (thường là tọa độ tile)
        value_func: Hàm tạo value từ item
    
    Returns:
        dict: Bản đồ tile
    """
    tile_map = {}
    
    for item in items:
        if item:  # Kiểm tra item không None
            key = key_func(item)
            value = value_func(item)
            tile_map[key] = value
    
    return tile_map

def build_item_tile_map(items: list) -> dict:
    """Tạo bản đồ tile cho items dựa trên CELL_SIZE"""
    return create_tile_map(
        items,
        lambda item: (int(item.get("x", 0) // CELL_SIZE), int(item.get("y", 0) // CELL_SIZE)),
        lambda item: item.get("type", "")
    )

def build_chest_tile_map(chests: list) -> dict:
    """Tạo bản đồ tile cho chests dựa trên CELL_SIZE"""
    return create_tile_map(
        chests,
        lambda chest: (int(chest.get("x", 0) // CELL_SIZE), int(chest.get("y", 0) // CELL_SIZE)),
        lambda chest: True
    )

# Bỏ toàn bộ hiển thị bản đồ để giảm log runtime

def get_tile_item(tile_x: int, tile_y: int) -> str:
    item_map = get_item_tile_map()
    return item_map.get((tile_x, tile_y), "")

def has_chest_at_tile(tile_x: int, tile_y: int) -> bool:
    """Kiểm tra có rương tại tile (x, y) không"""
    chest_map = get_chest_tile_map()
    return chest_map.get((tile_x, tile_y), False)

def has_wall_at_tile(tile_x: int, tile_y: int) -> bool:
    """Kiểm tra có tường tại tile (x, y) không"""
    try:
        map_data = game_state.get("map", [])
        if isinstance(map_data, dict):
            tiles = map_data.get("tiles", [])
        else:
            tiles = map_data if isinstance(map_data, list) else []
        
        # Kiểm tra bounds - SỬA: tiles[tile_y][tile_x]
        if tile_y < 0 or tile_y >= len(tiles) or tile_x < 0 or tile_x >= len(tiles[tile_y]):
            return True  # Ngoài bounds = tường
        
        # Kiểm tra tile có phải tường không ('W' hoặc 1 = tường)
        # SỬA: tiles[tile_y][tile_x] thay vì tiles[tile_x][tile_y]
        try:
            tile_value = tiles[tile_y][tile_x]
            return tile_value == 'W' or tile_value == 1  # Hỗ trợ cả string 'W' và số 1
        except (IndexError, TypeError):
            return True  # Lỗi truy cập = coi như tường
    except Exception as e:
        logger.error(f"❌ Lỗi has_wall_at_tile: {e}")
        return True  # Lỗi = coi như tường

# Bỏ cơ chế học phạm vi nổ từ log để đơn giản hóa

# ==============================
#  Fast bitmask-based GameState
# ==============================

# Bitmask cho 1 tile (1 byte)
WALL_MASK   = 1 << 0
CHEST_MASK  = 1 << 1
HAZARD_MASK = 1 << 2
ITEM_MASK   = 1 << 3
BOT_MASK    = 1 << 4

Pos = Tuple[int, int]

@dataclass(frozen=True, slots=True)
class StaticMap:
    width: int
    height: int
    walls: frozenset[Pos]
    chests: frozenset[Pos]
    base_mask: np.ndarray  # np.uint8, shape (H, W)

    @staticmethod
    def build_from_grid(grid: List[List[str]]) -> "StaticMap":
        h = len(grid)
        w = len(grid[0]) if h > 0 else 0
        base = np.zeros((h, w), dtype=np.uint8)
        walls: Set[Pos] = set()
        chests: Set[Pos] = set()
        for y, row in enumerate(grid):
            for x, cell in enumerate(row):
                if cell == "W":
                    base[y, x] |= WALL_MASK
                    walls.add((x, y))
                elif cell == "C":
                    base[y, x] |= CHEST_MASK
                    chests.add((x, y))
        return StaticMap(w, h, frozenset(walls), frozenset(chests), base)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

@dataclass(slots=True)
class Bomb:
    id: int
    owner_uid: str
    pos: Pos
    created_tick: int
    explode_tick: int
    flame: int

@dataclass(slots=True)
class DynamicState:
    bombs: Dict[int, Bomb] = field(default_factory=dict)
    items: Dict[Pos, str] = field(default_factory=dict)
    hazards_set: Set[Pos] = field(default_factory=set)
    hazard_until: np.ndarray = field(default_factory=lambda: np.zeros((16, 16), dtype=np.int16))

    def ensure_size(self, w: int, h: int) -> None:
        if self.hazard_until.shape != (h, w):
            self.hazard_until = np.zeros((h, w), dtype=np.int16)

    def mark_hazard_area(self, tiles: Iterable[Pos], until_tick: int) -> None:
        for x, y in tiles:
            self.hazards_set.add((x, y))
            self.hazard_until[y, x] = max(int(self.hazard_until[y, x]), until_tick)

    def decay_hazards(self, now_tick: int) -> None:
        expired = self.hazard_until < now_tick
        if np.any(expired):
            ys, xs = np.where(expired)
            for y, x in zip(ys, xs):
                self.hazards_set.discard((x, y))
                self.hazard_until[y, x] = 0

@dataclass(slots=True)
class AgentState:
    uid: str
    pos: Pos
    speed: int
    alive: bool = True
    last_action: str = ""

@dataclass(slots=True)
class FastGameState:
    static: Optional[StaticMap] = None
    dynamic: DynamicState = field(default_factory=DynamicState)
    agents: Dict[str, AgentState] = field(default_factory=dict)
    tick: int = 0
    _cached_mask_tick: int = -1
    _cached_tile_mask: Optional[np.ndarray] = None
    _cached_walkable_key: Tuple[int, bool, bool] = (-1, True, False)
    _cached_walkable_mask: Optional[np.ndarray] = None
    _path_cache_tick: int = -1
    _path_cache: Dict[Tuple[Pos, Pos, bool, bool, str], Optional[List[Pos]]] = field(default_factory=dict)

    def tile_mask(self) -> np.ndarray:
        if not self.static:
            return np.zeros((0, 0), dtype=np.uint8)
        if self._cached_tile_mask is not None and self._cached_mask_tick == self.tick:
            return self._cached_tile_mask
        mask = self.static.base_mask.copy()
        # hazards
        mask |= (self.dynamic.hazard_until > self.tick).astype(np.uint8) * HAZARD_MASK
        # items
        for (x, y), _t in self.dynamic.items.items():
            mask[y, x] |= ITEM_MASK
        # bots
        for ag in self.agents.values():
            if ag.alive and self.static.in_bounds(ag.pos[0], ag.pos[1]):
                x, y = ag.pos
                mask[y, x] |= BOT_MASK
        self._cached_tile_mask = mask
        self._cached_mask_tick = self.tick
        return mask

    def walkable_mask(self, avoid_hazard: bool = True, avoid_bots: bool = False, avoid_bombs: bool = True) -> np.ndarray:
        key = (self.tick, bool(avoid_hazard), bool(avoid_bots), bool(avoid_bombs))
        if self._cached_walkable_mask is not None and self._cached_walkable_key == key:
            return self._cached_walkable_mask
        mask = self.tile_mask()
        if mask.size == 0:
            return mask
        blocked = (mask & WALL_MASK) | (mask & CHEST_MASK)
        if avoid_hazard:
            blocked |= (mask & HAZARD_MASK)
        if avoid_bots:
            blocked |= (mask & BOT_MASK)
        
        # === AVOID BOMB BLAST ZONES ===
        if avoid_bombs:
            try:
                from .models.bomb_tracker import get_bomb_tracker
                bomb_tracker = get_bomb_tracker()
                blast_zones = bomb_tracker.get_all_blast_zones()
                
                # Mark blast zones as blocked
                for cell_x, cell_y in blast_zones:
                    # Convert 1-indexed to array indices
                    if self.static and self.static.in_bounds(cell_x, cell_y):
                        blocked[cell_y, cell_x] = True
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Bomb tracker error in walkable_mask: {e}")
        
        walkable = (blocked == 0)
        
        self._cached_walkable_mask = walkable
        self._cached_walkable_key = key
        return walkable

    def get_tile(self, x: int, y: int) -> str:
        if not self.static or not self.static.in_bounds(x, y):
            return '#'
        v = self.tile_mask()[y, x]
        if v & WALL_MASK:
            return 'W'
        if v & CHEST_MASK:
            return 'C'
        if v & HAZARD_MASK:
            return 'X'
        if v & ITEM_MASK:
            return 'I'
        return '0'


# Fast state toàn cục (song song với game_state cũ để tương thích ngược)
fast_state = FastGameState()

def fast_init_from_user(data: Dict[str, Any]) -> None:
    """Khởi tạo FastGameState từ event user (map, bombers, items, chests)."""
    grid = data.get("map") or []
    if grid:
        fast_state.static = StaticMap.build_from_grid(grid)
        fast_state.dynamic.ensure_size(fast_state.static.width, fast_state.static.height)
    else:
        fast_state.static = None

    # Agents
    fast_state.agents.clear()
    for b in data.get("bombers", []) or []:
        cx, cy = pos_to_cell_bot(b.get("x", 0), b.get("y", 0))
        fast_state.agents[b.get("uid", "?")] = AgentState(
            uid=b.get("uid", "?"), pos=(cx, cy), speed=int(b.get("speed", 1)), alive=bool(b.get("isAlive", True))
        )

    # Items
    fast_state.dynamic.items.clear()
    for it in data.get("items", []) or []:
        cx, cy = pos_to_cell(it.get("x", 0), it.get("y", 0))
        fast_state.dynamic.items[(cx, cy)] = it.get("type", "")

    # Bombs (không biết created_tick/explode_tick chính xác => ước lượng)
    fast_state.dynamic.bombs.clear()
    now_tick = int(time.time())
    for bm in data.get("bombs", []) or []:
        cx, cy = pos_to_cell(bm.get("x", 0), bm.get("y", 0))
        life_sec = float(bm.get("lifeTime", 5.0))
        created_at = bm.get("createdAt", time.time())
        remain_sec = max(0.0, life_sec - max(0.0, time.time() - created_at))
        explode_tick = now_tick + int(remain_sec)
        fast_state.dynamic.bombs[int(bm.get("id", 0))] = Bomb(
            id=int(bm.get("id", 0)), owner_uid=str(bm.get("uid", "")), pos=(cx, cy),
            created_tick=now_tick, explode_tick=explode_tick, flame=int(bm.get("flame", 2))
        )

    # Hazards reset
    if fast_state.static:
        fast_state.dynamic.ensure_size(fast_state.static.width, fast_state.static.height)
        fast_state.dynamic.hazard_until.fill(0)
        fast_state.dynamic.hazards_set.clear()
    fast_state.tick = now_tick
    # Dự báo vùng nổ từ bom hiện có
    update_predicted_hazards()

def fast_handle_new_bomb(data: Dict[str, Any]) -> None:
    """Cập nhật FastGameState khi có bom mới."""
    if not fast_state.static:
        return
    bomb_id = int(data.get("id", 0))
    cx, cy = pos_to_cell(data.get("x", 0), data.get("y", 0))
    owner = str(data.get("uid", ""))
    now_tick = fast_state.tick + 1
    life_sec = float(data.get("lifeTime", 5.0))
    explode_tick = now_tick + int(life_sec)
    fast_state.dynamic.bombs[bomb_id] = Bomb(
        id=bomb_id, owner_uid=owner, pos=(cx, cy), created_tick=now_tick, explode_tick=explode_tick, flame=int(data.get("flame", 2))
    )
    # cập nhật agent chủ nếu có
    if owner in fast_state.agents:
        ag = fast_state.agents[owner]
        fast_state.agents[owner] = AgentState(uid=ag.uid, pos=ag.pos, speed=ag.speed, alive=ag.alive, last_action=ag.last_action)
    fast_state.tick = now_tick
    fast_state._cached_mask_tick = -1
    update_predicted_hazards()

def fast_handle_bomb_explode(data: Dict[str, Any], ttl_ticks: int = 3) -> None:
    """Đánh dấu vùng nổ vào hazards với TTL ngắn, xóa bom khỏi dynamic."""
    if not fast_state.static:
        return
    now_tick = fast_state.tick + 1
    explosion_area = data.get("explosionArea") or []
    tiles: List[Pos] = []
    for p in explosion_area:
        cx, cy = pos_to_cell(p.get("x", 0), p.get("y", 0))
        if fast_state.static.in_bounds(cx, cy):
            tiles.append((cx, cy))
    fast_state.dynamic.mark_hazard_area(tiles, now_tick + max(1, ttl_ticks))

    # Xóa bom nổ
    bomb_id = int(data.get("id", -1))
    if bomb_id in fast_state.dynamic.bombs:
        del fast_state.dynamic.bombs[bomb_id]

    # Dọn hazards hết hạn
    fast_state.dynamic.decay_hazards(now_tick)
    fast_state.tick = now_tick
    fast_state._cached_mask_tick = -1
    # Cập nhật dự báo cho các bom còn lại
    update_predicted_hazards()

def fast_handle_map_update(data: Dict[str, Any]) -> None:
    """Cập nhật items/chests vào FastGameState."""
    if not fast_state.static:
        return
    now_tick = fast_state.tick + 1
    
    # Items
    if "items" in data:
        fast_state.dynamic.items.clear()
        for it in data.get("items") or []:
            cx, cy = pos_to_cell(it.get("x", 0), it.get("y", 0))
            if fast_state.static.in_bounds(cx, cy):
                fast_state.dynamic.items[(cx, cy)] = it.get("type", "")
    
    # Chests: rebuild static if layout thực sự thay đổi
    if "chests" in data:
        grid = game_state.get("map") or []
        if grid:
            chest_tiles = set()
            for c in data.get("chests") or []:
                cx, cy = pos_to_cell(c.get("x", 0), c.get("y", 0))
                chest_tiles.add((cx, cy))
            
            for y in range(len(grid)):
                for x in range(len(grid[0])):
                    if (x, y) in chest_tiles:
                        if grid[y][x] != 'W':
                            grid[y][x] = 'C'
                    else:
                        if grid[y][x] == 'C':
                            grid[y][x] = '0'
            fast_state.static = StaticMap.build_from_grid(grid)
            fast_state.dynamic.ensure_size(fast_state.static.width, fast_state.static.height)
    
    fast_state.dynamic.decay_hazards(now_tick)
    fast_state.tick = now_tick
    fast_state._cached_mask_tick = -1
    update_predicted_hazards()

def get_fast_state() -> FastGameState:
    """Truy xuất FastGameState toàn cục để AI có thể dùng."""
    return fast_state

def reset_fast_state() -> None:
    """Reset FastGameState về trạng thái ban đầu"""
    global fast_state
    fast_state.static = None
    fast_state.dynamic = DynamicState()
    fast_state.agents.clear()
    fast_state.tick = 0
    fast_state._cached_mask_tick = -1
    fast_state._cached_tile_mask = None
    fast_state._cached_walkable_key = (-1, True, False)
    fast_state._cached_walkable_mask = None
    fast_state._path_cache_tick = -1
    fast_state._path_cache.clear()
    logger.info("🔄 FAST STATE RESET: Đã reset FastGameState")

# -----------------------------
# Dự báo vùng nổ từ bom (line-of-fire)
# -----------------------------
def _compute_explosion_tiles(center: Pos, flame: int) -> List[Pos]:
    fs = get_fast_state()
    if not fs.static:
        return []
    tiles: List[Pos] = [center]
    # Dùng base_mask để kiểm tra vật cản
    base = fs.static.base_mask
    cx, cy = center
    for dx, dy in NEIGHBORS:
        x, y = cx, cy
        for _ in range(flame):
            x += dx
            y += dy
            if not fs.static.in_bounds(x, y):
                break
            tiles.append((x, y))
            # Dừng nếu gặp tường hoặc rương
            v = base[y, x]
            if (v & WALL_MASK) or (v & CHEST_MASK):
                break
    return tiles

def update_predicted_hazards() -> None:
    fs = get_fast_state()
    if not fs.static:
        return
    # Không xoá hazards hiện tại; chỉ tăng tối đa đến tick nổ dự kiến của bom
    for bomb in fs.dynamic.bombs.values():
        tiles = _compute_explosion_tiles(bomb.pos, max(0, int(bomb.flame)))
        for x, y in tiles:
            fs.dynamic.hazard_until[y, x] = max(int(fs.dynamic.hazard_until[y, x]), int(bomb.explode_tick))
            if fs.dynamic.hazard_until[y, x] > fs.tick:
                fs.dynamic.hazards_set.add((x, y))
    # Invalidate cache
    fs._cached_mask_tick = -1

# -----------------------------
# BFS trên FastGameState (16x16)
# -----------------------------
NEIGHBORS: Tuple[Tuple[int, int], ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))

def bfs_shortest_path(start: Pos, goal: Pos, avoid_hazard: bool = True, avoid_bots: bool = False, avoid_bombs: bool = True) -> Optional[List[Pos]]:
    """
    Tìm đường ngắn nhất từ start -> goal theo mặt nạ walkable.
    Trả về danh sách các ô (bao gồm start và goal) hoặc None nếu không có đường.
    
    Args:
        avoid_bombs: Có tránh blast zones của bombs không (mặc định True)
    """
    fs = get_fast_state()
    if not fs.static:
        return None
    if not (fs.static.in_bounds(start[0], start[1]) and fs.static.in_bounds(goal[0], goal[1])):
        return None
    walkable = fs.walkable_mask(avoid_hazard=avoid_hazard, avoid_bots=avoid_bots, avoid_bombs=avoid_bombs)
    if not walkable[start[1], start[0]] or not walkable[goal[1], goal[0]]:
        return None
    # Cache theo tick
    cache_key = (start, goal, bool(avoid_hazard), bool(avoid_bots), bool(avoid_bombs), "bfs")
    if fs._path_cache_tick != fs.tick:
        fs._path_cache_tick = fs.tick
        fs._path_cache = {}
    if cache_key in fs._path_cache:
        return fs._path_cache[cache_key]

    H, W = fs.static.height, fs.static.width
    visited = np.zeros((H, W), dtype=np.bool_)
    parent: Dict[Pos, Pos] = {}
    q: deque[Pos] = deque([start])
    visited[start[1], start[0]] = True
    while q:
        x, y = q.popleft()
        if (x, y) == goal:
            path = [(x, y)]
            while (x, y) != start:
                x, y = parent[(x, y)]
                path.append((x, y))
            path.reverse()
            
            # Kiểm tra path có hợp lệ không
            invalid_path = False
            for i, (px, py) in enumerate(path):
                if 0 <= px < W and 0 <= py < H:
                    is_walkable = walkable[py, px]
                    if not is_walkable:
                        logger.warning(f"⚠️ PATH INVALID: ({px},{py}) không thể đi được!")
                        invalid_path = True
            
            if invalid_path:
                logger.warning(f"⚠️ BFS PATH INVALID: Tìm được path nhưng có ô không thể đi được!")
                fs._path_cache[cache_key] = None
                return None
            
            fs._path_cache[cache_key] = path
            return path
        for dx, dy in NEIGHBORS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and not visited[ny, nx] and walkable[ny, nx]:
                visited[ny, nx] = True
                parent[(nx, ny)] = (x, y)
                q.append((nx, ny))
    fs._path_cache[cache_key] = None
    return None

# -----------------------------
# A* (Manhattan heuristic)
# -----------------------------
def astar_shortest_path(start: Pos, goal: Pos, avoid_hazard: bool = True, avoid_bots: bool = False, avoid_bombs: bool = True) -> Optional[List[Pos]]:
    """
    A* pathfinding với bomb blast zone avoidance
    
    Args:
        avoid_bombs: Có tránh blast zones của bombs không (mặc định True)
    """
    fs = get_fast_state()
    if not fs.static:
        return None
    if not (fs.static.in_bounds(start[0], start[1]) and fs.static.in_bounds(goal[0], goal[1])):
        return None
    walkable = fs.walkable_mask(avoid_hazard=avoid_hazard, avoid_bots=avoid_bots, avoid_bombs=avoid_bombs)
    if not walkable[start[1], start[0]] or not walkable[goal[1], goal[0]]:
        return None

    # Cache theo tick
    cache_key = (start, goal, bool(avoid_hazard), bool(avoid_bots), bool(avoid_bombs), "astar")
    if fs._path_cache_tick != fs.tick:
        fs._path_cache_tick = fs.tick
        fs._path_cache = {}
    if cache_key in fs._path_cache:
        return fs._path_cache[cache_key]

    import heapq
    H, W = fs.static.height, fs.static.width
    def h(p: Pos) -> int:
        # Manhattan + tie-breaker nhẹ để ưa chuộng đường thẳng theo trục lớn hơn
        dx = abs(p[0] - goal[0])
        dy = abs(p[1] - goal[1])
        return dx + dy + (0 if dx >= dy else 1)

    g_score = {start: 0}
    parent: Dict[Pos, Pos] = {}
    open_set: list[Tuple[int, int, Pos]] = []
    counter = 0
    heapq.heappush(open_set, (h(start), counter, start))
    in_open = {start}

    while open_set:
        _f, _c, current = heapq.heappop(open_set)
        in_open.discard(current)
        if current == goal:
            path = [current]
            while current != start:
                current = parent[current]
                path.append(current)
            path.reverse()
            
            # Kiểm tra path có hợp lệ không
            invalid_path = False
            for i, (px, py) in enumerate(path):
                if 0 <= px < W and 0 <= py < H:
                    is_walkable = walkable[py, px]
                    if not is_walkable:
                        logger.warning(f"⚠️ A* PATH INVALID: ({px},{py}) không thể đi được!")
                        invalid_path = True
            
            if invalid_path:
                logger.warning(f"⚠️ A* PATH INVALID: Tìm được path nhưng có ô không thể đi được!")
                fs._path_cache[cache_key] = None
                return None
            
            fs._path_cache[cache_key] = path
            return path
        x, y = current
        for dx, dy in NEIGHBORS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and walkable[ny, nx]:
                neighbor = (nx, ny)
                tentative_g = g_score[current] + 1
                if tentative_g < g_score.get(neighbor, 1_000_000_000):
                    parent[neighbor] = current
                    g_score[neighbor] = tentative_g
                    fscore = tentative_g + h(neighbor)
                    if neighbor not in in_open:
                        counter += 1
                        heapq.heappush(open_set, (fscore, counter, neighbor))
                        in_open.add(neighbor)
    fs._path_cache[cache_key] = None
    return None
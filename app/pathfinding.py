"""
Pathfinding - Tất cả logic tính đường đi
Gộp: Escape planning, Bombing positions, Navigation
"""

import logging
from typing import Tuple, Optional, List, Dict

logger = logging.getLogger(__name__)

# ============ ESCAPE PLANNING ============

def calculate_escape_time(path_length: int, bot_speed: int) -> float:
    """Tính thời gian cần để di chuyển (ms)"""
    from .config import CELL_SIZE
    
    pixels_needed = path_length * CELL_SIZE
    steps_needed = pixels_needed / bot_speed
    time_needed = steps_needed * 10  # 10ms per step
    
    return time_needed * 1.5  # Safety margin 50%

def calculate_blast_zone(bomb_position: Tuple[int, int], explosion_range: int) -> set:
    """Tính vùng nổ của bom"""
    from .game_state import game_state
    from .config import DIRECTIONS
    
    blast_zone = set()
    blast_zone.add(bomb_position)
    
    map_data = game_state.get("map", [])
    
    for direction, (dx, dy) in DIRECTIONS.items():
        for distance in range(1, explosion_range + 1):
            nx = bomb_position[0] + dx * distance
            ny = bomb_position[1] + dy * distance
            
            if not (0 <= nx <= 15 and 0 <= ny <= 15):
                break
            
            blast_zone.add((nx, ny))
            
            # Dừng nếu gặp tường hoặc rương
            try:
                if ny < len(map_data) and nx < len(map_data[ny]):
                    cell_value = map_data[ny][nx]
                    if cell_value in ['W', 1, 'x', 'r']:
                        break
            except:
                break
    
    return blast_zone

def find_nearest_safe_cells(
    bot_position: Tuple[int, int],
    blast_zone: set,
    max_distance: int = 8
) -> List[Tuple[int, int]]:
    """Tìm các ô an toàn gần nhất ngoài blast zone"""
    safe_cells = []
    
    for distance in range(1, max_distance + 1):
        for dx in range(-distance, distance + 1):
            for dy in range(-distance, distance + 1):
                if abs(dx) + abs(dy) != distance:
                    continue
                
                cell = (bot_position[0] + dx, bot_position[1] + dy)
                
                if (cell not in blast_zone and
                    0 <= cell[0] <= 15 and 0 <= cell[1] <= 15 and
                    is_cell_passable(cell)):
                    safe_cells.append(cell)
        
        if safe_cells:
            return safe_cells
    
    return safe_cells

def find_escape_path_from_bomb(
    bomb_position: Tuple[int, int],
    bot_position: Tuple[int, int],
    explosion_range: int,
    bomb_lifetime: float = 5000.0
) -> Optional[Tuple[List[Tuple[int, int]], float]]:
    """Tìm đường thoát từ vị trí bom - CHO PHÉP đi qua hazard nếu đủ thời gian"""
    from .game_state import astar_shortest_path, game_state, get_bomber_speed
    
    blast_zone = calculate_blast_zone(bomb_position, explosion_range)
    safe_cells = find_nearest_safe_cells(bomb_position, blast_zone, max_distance=8)
    
    if not safe_cells:
        return None
    
    my_uid = game_state.get("my_uid")
    bot_speed = get_bomber_speed(my_uid)
    
    best_path = None
    best_time = float('inf')
    
    for safe_cell in safe_cells[:5]:
        # THỬ 2 CÁCH: Tránh hazard và cho phép đi qua hazard
        paths_to_try = []
        
        # Cách 1: Tránh hazard (an toàn nhất)
        path_safe = astar_shortest_path(bomb_position, safe_cell, avoid_hazard=True, avoid_bots=False)
        if path_safe and len(path_safe) > 1:
            paths_to_try.append(("safe", path_safe))
        
        # Cách 2: Cho phép đi qua hazard (nhanh hơn)
        path_risky = astar_shortest_path(bomb_position, safe_cell, avoid_hazard=False, avoid_bots=False)
        if path_risky and len(path_risky) > 1:
            paths_to_try.append(("risky", path_risky))
        
        # Đánh giá từng path
        for path_type, path in paths_to_try:
            escape_time = calculate_escape_time(len(path) - 1, bot_speed)
            
            # Kiểm tra timing
            if escape_time < bomb_lifetime * 0.8:
                # Kiểm tra path có đi qua hazard không và có đủ thời gian không
                if path_type == "risky":
                    # Tính thời gian đến từng ô trong path
                    if _can_safely_traverse_hazard_path(path, bot_speed, bomb_lifetime):
                        if escape_time < best_time:
                            best_time = escape_time
                            best_path = path
                else:
                    # Safe path - luôn OK
                    if escape_time < best_time:
                        best_time = escape_time
                        best_path = path
    
    if best_path:
        return (best_path, best_time)
    return None

def _can_safely_traverse_hazard_path(path: List[Tuple[int, int]], bot_speed: float, bomb_lifetime: float) -> bool:
    """Kiểm tra có thể đi qua hazard path an toàn không"""
    import time
    from .game_state import game_state
    
    current_time = time.time() * 1000
    total_time = 0
    
    for i, cell in enumerate(path):
        # Tính thời gian đến ô này
        if i == 0:
            continue  # Ô đầu tiên (vị trí hiện tại)
        
        # Thời gian di chuyển từ ô trước đến ô này
        move_time = 1000 / bot_speed  # ms per cell
        total_time += move_time
        
        # Kiểm tra ô này có nguy hiểm không
        if is_in_danger(cell, current_time + total_time):
            # Tính thời gian bom nổ tại ô này (sử dụng tick thay vì ms)
            from .game_state import get_fast_state
            fs = get_fast_state()
            cx, cy = int(cell[0]), int(cell[1])
            if fs.static.in_bounds(cx, cy):
                explosion_tick = fs.dynamic.hazard_until[cy, cx]
                arrival_tick = int((current_time + total_time) / 100)  # Convert ms to tick
                if arrival_tick >= explosion_tick:
                    return False
    
    # logger.info(f"✅ CÓ THỂ đi qua hazard path: tổng {total_time:.0f}ms < bom nổ {bomb_lifetime:.0f}ms")  # Giảm log spam
    return True

def is_safe_to_place_bomb(
    bomb_position: Tuple[int, int],
    bot_position: Tuple[int, int],
    explosion_range: int,
    bomb_lifetime: float = 5000.0
) -> bool:
    """Kiểm tra CÓ AN TOÀN để đặt bom không"""
    result = find_escape_path_from_bomb(
        bomb_position, bot_position, explosion_range, bomb_lifetime
    )
    return result is not None

# ============ BOMBING POSITIONS ============

def find_best_bombing_position(
    current_position: Tuple[int, int],
    max_search_radius: int = 16,
    blacklist: Optional[Dict[Tuple[int, int], float]] = None,
    current_time: float = 0.0
) -> Optional[Tuple[int, int]]:
    """Tìm vị trí đặt bom TỐT NHẤT"""
    from .game_state import game_state, get_bomber_explosion_range
    
    my_uid = game_state.get("my_uid")
    if not my_uid:
        return None
    
    explosion_range = get_bomber_explosion_range(my_uid)
    
    # Tìm chests
    chests = find_chests_in_range(current_position, max_search_radius)
    
    if not chests:
        return None
    
    # Đánh giá từng vị trí
    candidates = []
    
    for chest in chests:
        bomb_positions = get_bomb_positions_for_target(chest, explosion_range)
        
        for bomb_pos in bomb_positions:
            # Check blacklist
            if blacklist and bomb_pos in blacklist:
                if current_time - blacklist[bomb_pos] < 5000:
                    continue
            
            # Check passable
            if not is_cell_passable(bomb_pos):
                continue
            
            # Check path to bomb
            if bomb_pos != current_position:
                from .game_state import astar_shortest_path
                path_to_bomb = astar_shortest_path(current_position, bomb_pos, avoid_hazard=True, avoid_bots=False)
                if not path_to_bomb or len(path_to_bomb) < 2:
                    continue
            
            # Check escape
            if not is_safe_to_place_bomb(bomb_pos, current_position, explosion_range):
                continue
            
            # Tính điểm
            score = calculate_bombing_score(bomb_pos, chest, current_position, explosion_range)
            candidates.append((bomb_pos, score, chest))
    
    if not candidates:
        return None
    
    # Chọn tốt nhất
    candidates.sort(key=lambda x: x[1], reverse=True)
    best_pos, best_score, target_chest = candidates[0]

    return best_pos

def get_bomb_positions_for_target(target: Tuple[int, int], explosion_range: int) -> List[Tuple[int, int]]:
    """Tìm các vị trí có thể đặt bom để nổ target"""
    from .game_state import game_state
    from .config import DIRECTIONS
    
    positions = []
    map_data = game_state.get("map", [])
    
    for direction, (dx, dy) in DIRECTIONS.items():
        for distance in range(0, explosion_range + 1):
            bomb_pos = (target[0] - dx * distance, target[1] - dy * distance)
            
            if not (0 <= bomb_pos[0] <= 15 and 0 <= bomb_pos[1] <= 15):
                break
            
            # Check không có tường giữa bomb và target
            path_clear = True
            for check_dist in range(1, distance + 1):
                check_pos = (target[0] - dx * check_dist, target[1] - dy * check_dist)
                try:
                    check_y, check_x = int(check_pos[1]), int(check_pos[0])
                    if (check_y < len(map_data) and check_x < len(map_data[check_y])):
                        cell_value = map_data[check_y][check_x]
                        if cell_value in ['W', 1]:
                            path_clear = False
                            break
                except:
                    path_clear = False
                    break
            
            if path_clear:
                positions.append(bomb_pos)
    
    return positions

def calculate_bombing_score(
    bomb_position: Tuple[int, int],
    target: Tuple[int, int],
    bot_position: Tuple[int, int],
    explosion_range: int
) -> float:
    """Tính điểm cho vị trí đặt bom"""
    score = 100.0
    
    # Khoảng cách đến target
    distance_to_target = abs(bomb_position[0] - target[0]) + abs(bomb_position[1] - target[1])
    score -= distance_to_target * 5
    
    # Khoảng cách đến bot
    distance_to_bot = abs(bomb_position[0] - bot_position[0]) + abs(bomb_position[1] - bot_position[1])
    score -= distance_to_bot * 10
    
    # Bonus nếu là vị trí hiện tại
    if bomb_position == bot_position:
        score += 50
    
    # Số lượng targets trong tầm nổ
    num_chests = len(count_targets_in_blast(bomb_position, explosion_range))
    score += num_chests * 30
    
    # Check bot khác gần đó
    from .game_state import game_state, pos_to_cell_bot
    my_uid = game_state.get("my_uid")
    for bomber in game_state.get("bombers", []):
        if bomber.get("uid") == my_uid or not bomber.get("isAlive", True):
            continue
        
        bomber_cell = pos_to_cell_bot(bomber.get("x", 0), bomber.get("y", 0))
        distance_to_enemy = abs(bomber_cell[0] - bomb_position[0]) + abs(bomber_cell[1] - bomb_position[1])
        
        if distance_to_enemy <= 3:
            score -= 30
    
    return score

def count_targets_in_blast(bomb_position: Tuple[int, int], explosion_range: int) -> List[Tuple[int, int]]:
    """Đếm số targets trong vùng nổ"""
    from .game_state import game_state, pos_to_cell
    from .config import DIRECTIONS
    
    targets = []
    map_data = game_state.get("map", [])
    chests = game_state.get("chests", [])
    
    for direction, (dx, dy) in DIRECTIONS.items():
        for distance in range(1, explosion_range + 1):
            check_pos = (bomb_position[0] + dx * distance, bomb_position[1] + dy * distance)
            
            if not (0 <= check_pos[0] <= 15 and 0 <= check_pos[1] <= 15):
                break
            
            # Check chest
            for chest in chests:
                chest_cell = pos_to_cell(chest.get("x", 0), chest.get("y", 0))
                if chest_cell == check_pos:
                    targets.append(check_pos)
            
            # Dừng nếu gặp tường
            try:
                check_y, check_x = int(check_pos[1]), int(check_pos[0])
                if (check_y < len(map_data) and check_x < len(map_data[check_y])):
                    cell_value = map_data[check_y][check_x]
                    if cell_value in ['W', 1]:
                        break
            except:
                break
    
    return targets

# ============ NAVIGATION ============

def is_cell_passable(cell: Tuple[int, int], avoid_bombs: bool = False) -> bool:
    """Kiểm tra ô có thể đi qua không"""
    try:
        from .game_state import get_fast_state
        
        fs = get_fast_state()
        if not fs.static:
            return False
        
        # QUAN TRỌNG: Convert float to int để dùng làm array index!
        cx, cy = int(cell[0]), int(cell[1])
        if not fs.static.in_bounds(cx, cy):
            return False
        
        if fs.static.base_mask[cy, cx] & 1:
            return False
        
        if avoid_bombs:
            from .models.bomb_tracker import get_bomb_tracker
            tracker = get_bomb_tracker()
            if tracker.has_bomb_at(cell):
                return False
        
        return True
    except Exception:
        return False

def is_in_danger(cell: Tuple[int, int], current_time: float) -> bool:
    """Kiểm tra ô có nguy hiểm không"""
    from .game_state import get_fast_state
    
    fs = get_fast_state()
    if not fs.static:
        return False
    
    now_tick = fs.tick
    # QUAN TRỌNG: Convert float to int để dùng làm array index!
    # cell có thể là (13.5, 1) từ pos_to_cell()
    cx, cy = int(cell[0]), int(cell[1])
    if not fs.static.in_bounds(cx, cy):
        return True
    return fs.dynamic.hazard_until[cy, cx] > now_tick

def has_dangerous_bombs_nearby(cell: Tuple[int, int], current_time: float, radius: int = 3) -> bool:
    """Kiểm tra có bom nguy hiểm gần không"""
    from .game_state import game_state, pos_to_cell
    
    try:
        bombs = game_state.get("bombs", [])
        for bomb in bombs:
            bomb_cell = pos_to_cell(bomb.get("x", 0), bomb.get("y", 0))
            distance = abs(bomb_cell[0] - cell[0]) + abs(bomb_cell[1] - cell[1])
            
            if distance <= radius:
                life_time = bomb.get("lifeTime", 5.0)
                created_at = bomb.get("createdAt", current_time / 1000)
                elapsed = (current_time / 1000) - created_at
                remaining = life_time - elapsed
                
                if remaining <= 3.0:
                    return True
    except Exception as e:
        pass
    return False

def find_safe_cells(current_cell: Tuple[int, int], current_time: float, radius: int = 6) -> List[Tuple[int, int]]:
    """Tìm các ô an toàn gần"""
    safe_cells = []
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            check_cell = (current_cell[0] + dx, current_cell[1] + dy)
            if (is_cell_passable(check_cell) and 
                not is_in_danger(check_cell, current_time)):
                safe_cells.append(check_cell)
    return safe_cells

def can_reach_goal(current_cell: Tuple[int, int], goal_cell: Tuple[int, int]) -> bool:
    """Kiểm tra có thể đến goal không"""
    from .game_state import bfs_shortest_path
    
    try:
        path = bfs_shortest_path(current_cell, goal_cell, avoid_hazard=True, avoid_bots=False)
        return path is not None and len(path) >= 2
    except Exception:
        return False

# ============ BOMBING HELPERS ============

def has_chest_in_bomb_range(cell: Tuple[int, int]) -> bool:
    """Kiểm tra có rương trong tầm nổ không"""
    from .game_state import game_state, has_chest_at_tile, has_wall_at_tile, in_bounds, get_bomber_explosion_range
    from .config import DIRECTIONS
    
    try:
        my_uid = game_state.get("my_uid")
        if not my_uid:
            return False
            
        explosion_range = get_bomber_explosion_range(my_uid)
        
        for direction, (dx, dy) in DIRECTIONS.items():
            for distance in range(1, explosion_range + 1):
                check_cell = (cell[0] + dx * distance, cell[1] + dy * distance)
                
                if not in_bounds(check_cell[0], check_cell[1]):
                    break
                
                if has_wall_at_tile(check_cell[0], check_cell[1]):
                    break
                
                if has_chest_at_tile(check_cell[0], check_cell[1]):
                    return True
        
        return False
    except Exception as e:
        return False

def has_escape_after_bomb(cell: Tuple[int, int]) -> bool:
    """Kiểm tra có lối thoát sau khi đặt bom không"""
    from .game_state import game_state, get_bomber_explosion_range
    from .config import DIRECTIONS
    
    try:
        my_uid = game_state.get("my_uid")
        explosion_range = get_bomber_explosion_range(my_uid)
        
        blast_cells = set()
        blast_cells.add(cell)
        
        for dx, dy in DIRECTIONS.values():
            for k in range(1, explosion_range + 1):
                nx, ny = cell[0] + dx * k, cell[1] + dy * k
                blast_cells.add((nx, ny))
                
                mp = game_state.get("map", [])
                if (0 <= nx < len(mp[0]) and 0 <= ny < len(mp) and mp[ny][nx] == "W"):
                    break
        
        # Tìm ô an toàn gần
        safe_cells = []
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                check_cell = (cell[0] + dx, cell[1] + dy)
                if (check_cell not in blast_cells and is_cell_passable(check_cell)):
                    safe_cells.append(check_cell)
        
        return len(safe_cells) > 0
    except Exception as e:
        return False

def find_chests_in_range(current_cell: Tuple[int, int], max_range: int) -> List[Tuple[int, int]]:
    """Tìm rương trong tầm"""
    from .game_state import game_state, pos_to_cell
    
    chests = []
    try:
        chest_data = game_state.get("chests", [])
        
        for chest in chest_data:
            chest_cell = pos_to_cell(chest.get("x", 0), chest.get("y", 0))
            if max_range >= 16:
                chests.append(chest_cell)
            else:
                distance = abs(chest_cell[0] - current_cell[0]) + abs(chest_cell[1] - current_cell[1])
                if distance <= max_range:
                    chests.append(chest_cell)
    except Exception as e:
        pass
    return chests

def should_place_bomb_now(
    current_position: Tuple[int, int],
    target_position: Tuple[int, int],
    can_place_bomb: bool
) -> bool:
    """Quyết định có nên đặt bom NGAY không"""
    if not can_place_bomb:
        return False
    
    if current_position != target_position:
        return False
    
    from .game_state import game_state, get_bomber_explosion_range
    
    my_uid = game_state.get("my_uid")
    explosion_range = get_bomber_explosion_range(my_uid)
    
    if not has_chest_in_bomb_range(current_position):
        return False
    
    if not is_safe_to_place_bomb(current_position, current_position, explosion_range):
        return False
    
    return True


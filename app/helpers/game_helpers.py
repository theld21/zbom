"""
Game helpers - Gộp các helper nhỏ: Danger, Bombing, Navigation
"""

import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class DangerDetector:
    """Helper class để phát hiện nguy hiểm"""
    
    @staticmethod
    def is_in_danger(cell: Tuple[int, int], current_time: float) -> bool:
        """Kiểm tra ô có nguy hiểm không"""
        from ..game_state import get_fast_state
        
        fs = get_fast_state()
        if not fs.static:
            return False
        
        now_tick = fs.tick
        cx, cy = cell
        if not fs.static.in_bounds(cx, cy):
            return True
        return fs.dynamic.hazard_until[cy, cx] > now_tick
    
    @staticmethod
    def has_dangerous_bombs_nearby(cell: Tuple[int, int], current_time: float, radius: int = 3) -> bool:
        """Kiểm tra có bom nguy hiểm gần đó không"""
        from ..game_state import game_state, pos_to_cell
        
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
                        logger.info(f"⚠️ BOM NGUY HIỂM: tại {bomb_cell}, còn {remaining:.1f}s")
                        return True
        except Exception as e:
            logger.error(f"Lỗi kiểm tra bom nguy hiểm: {e}")
        return False


class BombingHelper:
    """Helper class cho bombing logic"""
    
    @staticmethod
    def has_chest_in_bomb_range(cell: Tuple[int, int]) -> bool:
        """Kiểm tra có rương trong tầm nổ không"""
        from ..game_state import game_state, has_chest_at_tile, has_wall_at_tile, in_bounds, get_bomber_explosion_range
        from ..config import DIRECTIONS
        
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
                        logger.info(f"💎 TÌM THẤY RƯƠNG TRONG TẦM NỔ: {check_cell} (hướng {direction}, khoảng cách {distance})")
                        return True
            
            return False
        except Exception as e:
            logger.error(f"❌ Lỗi kiểm tra tầm nổ: {e}")
            return False
    
    @staticmethod
    def has_escape_after_bomb(cell: Tuple[int, int]) -> bool:
        """Kiểm tra có lối thoát sau khi đặt bom không"""
        from ..game_state import game_state, get_bomber_explosion_range
        from ..config import DIRECTIONS
        
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
                    if (check_cell not in blast_cells and 
                        NavigationHelper.is_cell_passable(check_cell)):
                        safe_cells.append(check_cell)
            
            return len(safe_cells) > 0
        except Exception as e:
            logger.error(f"❌ Lỗi kiểm tra lối thoát: {e}")
            return False
    
    @staticmethod
    def find_chests_in_range(current_cell: Tuple[int, int], max_range: int) -> List[Tuple[int, int]]:
        """Tìm rương trong tầm"""
        from ..game_state import game_state, pos_to_cell
        
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
            logger.error(f"❌ Lỗi tìm rương: {e}")
        return chests


class NavigationHelper:
    """Helper class cho navigation và pathfinding"""
    
    @staticmethod
    def is_cell_passable(cell: Tuple[int, int], avoid_bombs: bool = False) -> bool:
        """Kiểm tra ô có thể đi qua không"""
        try:
            from ..game_state import get_fast_state
            
            fs = get_fast_state()
            if not fs.static:
                return False
            
            cx, cy = cell
            if not fs.static.in_bounds(cx, cy):
                return False
            
            if fs.static.base_mask[cy, cx] & 1:
                return False
            
            if avoid_bombs:
                from ..models.bomb_tracker import get_bomb_tracker
                tracker = get_bomb_tracker()
                if tracker.has_bomb_at(cell):
                    return False
            
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_neighbors(cell: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Lấy các ô kề cận có thể đi qua"""
        from ..config import DIRECTIONS
        
        neighbors = []
        for dx, dy in DIRECTIONS.values():
            next_cell = (cell[0] + dx, cell[1] + dy)
            if NavigationHelper.is_cell_passable(next_cell):
                neighbors.append(next_cell)
        return neighbors
    
    @staticmethod
    def find_safe_cells(current_cell: Tuple[int, int], current_time: float, radius: int = 6) -> List[Tuple[int, int]]:
        """Tìm các ô an toàn gần"""
        safe_cells = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                check_cell = (current_cell[0] + dx, current_cell[1] + dy)
                if (NavigationHelper.is_cell_passable(check_cell) and 
                    not DangerDetector.is_in_danger(check_cell, current_time)):
                    safe_cells.append(check_cell)
        return safe_cells
    
    @staticmethod
    def can_reach_goal(current_cell: Tuple[int, int], goal_cell: Tuple[int, int]) -> bool:
        """Kiểm tra có thể đến goal không"""
        from ..game_state import bfs_shortest_path
        
        try:
            path = bfs_shortest_path(current_cell, goal_cell, avoid_hazard=True, avoid_bots=False)
            return path is not None and len(path) >= 2
        except Exception:
            return False


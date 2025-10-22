"""
Bombing logic helpers
"""

import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


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
        from .navigation import NavigationHelper
        
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
        """Tìm rương trong tầm (hoặc toàn bộ map nếu max_range >= 16)"""
        from ..game_state import game_state, pos_to_cell
        
        chests = []
        try:
            chest_data = game_state.get("chests", [])
            
            for chest in chest_data:
                chest_cell = pos_to_cell(chest.get("x", 0), chest.get("y", 0))
                # Nếu max_range >= 16, tìm toàn bộ map
                if max_range >= 16:
                    chests.append(chest_cell)
                else:
                    distance = abs(chest_cell[0] - current_cell[0]) + abs(chest_cell[1] - current_cell[1])
                    if distance <= max_range:
                        chests.append(chest_cell)
        except Exception as e:
            logger.error(f"❌ Lỗi tìm rương: {e}")
        return chests

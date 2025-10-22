"""
Danger detection helpers
"""

import logging
from typing import Tuple

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

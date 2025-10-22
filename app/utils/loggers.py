"""
Loggers - Gộp map_logger và movement_logger
"""

import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


def log_map_state(game_state: Dict[str, Any], log_enabled: bool = True, force: bool = False):
    """Log trạng thái bản đồ trước khi phân tích plan"""
    if not log_enabled and not force:
        return
        
    try:
        from ..game_state import get_my_bomber, pos_to_cell
        
        map_data = game_state.get("map", [])
        if isinstance(map_data, dict):
            tiles = map_data.get("tiles", [])
        else:
            tiles = map_data if isinstance(map_data, list) else []
        
        bombs = game_state.get("bombs", [])
        items = game_state.get("items", [])
        chests = game_state.get("chests", [])
        
        me = get_my_bomber()
        bot_cell = None
        if me:
            bot_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
        
        logger.info("=" * 50)
        logger.info("🗺️  MAP STATE")
        logger.info(f"Map size: {len(tiles)}x{len(tiles[0]) if tiles else 0}")
        logger.info(f"Bot: {bot_cell}")
        logger.info(f"Bombs: {len(bombs)}, Items: {len(items)}, Chests: {len(chests)}")
        
        if bombs:
            bomb_cells = [pos_to_cell(b.get("x", 0), b.get("y", 0)) for b in bombs[:3]]
            logger.info(f"Bomb cells: {bomb_cells}")
        
        if chests:
            chest_cells = [pos_to_cell(c.get("x", 0), c.get("y", 0)) for c in chests[:5]]
            logger.info(f"Chest cells: {chest_cells}")
        
        logger.info("=" * 50)
    except Exception as e:
        logger.error(f"❌ Lỗi log map: {e}")


class MovementLogger:
    """Hệ thống log di chuyển đơn giản"""
    
    def __init__(self):
        self.current_direction: Optional[str] = None
        self.last_logged_cell: Optional[Tuple[int, int]] = None
        
    def log_movement(self, direction: str, log_enabled: bool = True):
        """Log di chuyển - chỉ log khi thay đổi hướng"""
        if not log_enabled:
            return
            
        if self.current_direction != direction:
            self.current_direction = direction
            
            from ..game_state import get_my_bomber, pos_to_cell
            
            me = get_my_bomber()
            if me:
                px, py = me.get("x", 0), me.get("y", 0)
                current_cell = pos_to_cell(px, py)
                logger.info(f"🚶 DI CHUYỂN: pixel({px:.1f},{py:.1f}) tile{current_cell} → {direction}")
            else:
                logger.info(f"🚶 DI CHUYỂN: {direction}")
    
    def check_and_log_cell_arrival(self, log_enabled: bool = True):
        """Kiểm tra và log khi bot vào ô mới"""
        if not log_enabled:
            return
            
        from ..game_state import get_my_bomber, pos_to_cell, is_at_exact_cell
        
        me = get_my_bomber()
        if not me:
            return
        
        px, py = me.get("x", 0), me.get("y", 0)
        current_cell = pos_to_cell(px, py)
        
        if is_at_exact_cell(px, py) and current_cell != self.last_logged_cell:
            logger.info(f"📍 VÀO Ô: pixel({px:.1f},{py:.1f}) → tile{current_cell}")
            self.last_logged_cell = current_cell
    
    def reset(self):
        """Reset logger state"""
        self.current_direction = None
        self.last_logged_cell = None
    
    def flush(self):
        """Placeholder for compatibility"""
        pass


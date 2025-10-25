"""Loggers - Movement logging and map logging"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class MovementLogger:
    """Movement logger with cell arrival tracking"""
    
    def __init__(self):
        self.last_cell = None
        self.last_log_time = 0
    
    def check_and_log_cell_arrival(self, log_enabled: bool = True):
        """Check and log when bot arrives at a new cell"""
        if not log_enabled:
            return
        
        try:
            from ..game_state import get_my_bomber, pos_to_cell
            
            me = get_my_bomber()
            if not me:
                return
            
            # Sử dụng pos_to_cell để có tọa độ chính xác (bao gồm .5)
            current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
            
            # Chỉ log khi bot ở chính xác ô (số nguyên), không log khi ở giữa cell (.5)
            is_exact = (current_cell[0] % 1.0 == 0.0 and current_cell[1] % 1.0 == 0.0)
            
            if is_exact and current_cell != self.last_cell:
                # Convert sang int để log đẹp hơn
                cell_int = (int(current_cell[0]), int(current_cell[1]))
                logger.info(f"📍 ĐẾN Ô MỚI: {cell_int}")
                self.last_cell = current_cell
        except Exception as e:
            logger.error(f"Error checking cell arrival: {e}")
    
    def log_movement(self, orient: str, log_enabled: bool = True):
        """Log movement"""
        if not log_enabled:
            return
        logger.info(f"➡️ MOVE: {orient}")
    
    @staticmethod
    def log_move(orient: str, current_pos: tuple, target_pos: tuple):
        """Log movement with positions"""
        logger.info(f"MOVE {orient}: {current_pos} → {target_pos}")

def log_map_state(game_state: Dict[str, Any], log_enabled: bool = True):
    """Log map state"""
    from ..config import LOG_MAP
    if not LOG_MAP or not log_enabled:
        return
    
    try:
        mp = game_state.get("map", [])
        if not mp:
            return
        
        logger.info("=== MAP ===")
        for row in mp:
            logger.info(" ".join(str(cell) if cell else "." for cell in row))
        logger.info("===========")
    except Exception as e:
        logger.error(f"Error logging map: {e}")

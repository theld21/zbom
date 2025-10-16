"""Movement Logger - Ghi log di chuyển của bot"""
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

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
            
            # Import động để tránh circular import
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
            
        # Import động để tránh circular import
        from ..game_state import get_my_bomber, pos_to_cell
        
        me = get_my_bomber()
        if not me:
            return
        
        px, py = me.get("x", 0), me.get("y", 0)
        current_cell = pos_to_cell(px, py)
        
        # Chỉ log khi vào ô MỚI và đã tới chính xác (số nguyên)
        # Số nguyên = đã tới chính xác ô
        # Số lẻ (.5) = đang ở giữa cell, chưa tới
        
        from ..game_state import is_at_exact_cell
        
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


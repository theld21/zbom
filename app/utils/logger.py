"""
Logging utilities cho bot
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..game_state import game_state

logger = logging.getLogger("bot")


class MovementLogger:
    """Logger chuyên dụng cho di chuyển"""
    
    def __init__(self):
        self.current_direction = None
        
    def log_movement(self, direction: str, log_enabled: bool = True):
        """Log di chuyển - chỉ log khi thay đổi hướng"""
        if not log_enabled:
            return
        if self.current_direction != direction:
            self.current_direction = direction
            logger.info(f"🚶 DI CHUYỂN: {direction}")
    
    def flush(self):
        """Flush log buffer"""
        pass


def log_map_state(force: bool = False):
    """Log trạng thái bản đồ"""
    from ..config import LOG_MAP, LOG_GAME_EVENTS
    from ..game_state import game_state, get_my_bomber, pos_to_cell
    
    if not LOG_MAP and not force:
        return
        
    try:
        # Lấy thông tin map
        map_data = game_state.get("map", [])
        if isinstance(map_data, dict):
            tiles = map_data.get("tiles", [])
        else:
            tiles = map_data if isinstance(map_data, list) else []
        
        # DEBUG: Log cấu trúc dữ liệu map
        if LOG_GAME_EVENTS:
            logger.info(f"🗺️ DEBUG MAP: type={type(map_data)}, tiles_type={type(tiles)}")
            if tiles and len(tiles) > 0:
                logger.info(f"🗺️ DEBUG TILES: len={len(tiles)}")
        
        bombs = game_state.get("bombs", [])
        items = game_state.get("items", [])
        chests = game_state.get("chests", [])
        
        # Lấy vị trí bot
        me = get_my_bomber()
        bot_cell = None
        if me:
            bot_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
        
        # Tạo map 14x14 (bỏ hàng/cột biên)
        map_lines = []
        
        for y in range(1, 15):
            line = ""
            for x in range(1, 15):
                # Kiểm tra bot
                if bot_cell and bot_cell == (x, y):
                    line += "X"
                    continue
                
                # Kiểm tra bomb
                has_bomb = False
                for bomb in bombs:
                    bomb_cell = pos_to_cell(bomb.get("x", 0), bomb.get("y", 0))
                    if bomb_cell == (x, y):
                        line += "b"
                        has_bomb = True
                        break
                
                if has_bomb:
                    continue
                
                # Kiểm tra rương
                has_chest = False
                for chest in chests:
                    chest_cell = pos_to_cell(chest.get("x", 0), chest.get("y", 0))
                    if chest_cell == (x, y):
                        line += "r"
                        has_chest = True
                        break
                
                if has_chest:
                    continue
                
                # Kiểm tra item
                has_item = False
                for item in items:
                    item_cell = pos_to_cell(item.get("x", 0), item.get("y", 0))
                    if item_cell == (x, y):
                        item_type = item.get("type", "")
                        if item_type == "SPEED":
                            line += "g"
                        elif item_type == "BOMB_COUNT":
                            line += "c"
                        elif item_type == "EXPLOSION_RANGE":
                            line += "l"
                        else:
                            line += "i"
                        has_item = True
                        break
                
                if has_item:
                    continue
                
                # Kiểm tra tường
                try:
                    if y < len(tiles) and x < len(tiles[y]):
                        tile_value = tiles[y][x]
                        if tile_value == 'W' or tile_value == 1:
                            line += "x"
                        else:
                            line += "-"
                    else:
                        line += "x"
                except Exception:
                    line += "x"
            
            map_lines.append(line)
        
        # Log map
        logger.info("🗺️ BẢN ĐỒ HIỆN TẠI (khu vực bên trong):")
        for i, line in enumerate(map_lines):
            logger.info(f"🗺️ {i+1:2d}|{line}")
        
        # Log chú thích
        logger.info("🗺️ CHÚ THÍCH: x=tường, r=rương, X=bot, b=bomb, g=giày, c=item bom, l=lửa, -=trống")
        
    except Exception as e:
        logger.error(f"🗺️ Lỗi log map: {e}")

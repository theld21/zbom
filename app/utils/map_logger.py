"""Map Logger - Ghi log bản đồ game"""
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

def log_map_state(game_state: Dict[str, Any], log_enabled: bool = True, force: bool = False):
    """Log trạng thái bản đồ trước khi phân tích plan"""
    if not log_enabled and not force:
        return
        
    try:
        # Import động để tránh circular import
        from ..game_state import get_my_bomber, pos_to_cell
        from ..config import LOG_GAME_EVENTS
        
        # Lấy thông tin map
        map_data = game_state.get("map", [])
        if isinstance(map_data, dict):
            tiles = map_data.get("tiles", [])
        else:
            tiles = map_data if isinstance(map_data, list) else []
        
        # DEBUG: Log cấu trúc dữ liệu map (chỉ khi cần debug)
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
        
        for y in range(1, 15):  # Hàng 1-14
            line = ""
            for x in range(1, 15):  # Cột 1-14
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
        
        logger.info("🗺️ CHÚ THÍCH: x=tường, r=rương, X=bot, b=bomb, g=giày, c=item bom, l=lửa, -=trống")
        
    except Exception as e:
        logger.error(f"🗺️ Lỗi log map: {e}")


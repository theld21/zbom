"""
Escape planning với tính toán timing chính xác
"""

import logging
import time
from typing import Tuple, Optional, List

logger = logging.getLogger(__name__)


class EscapePlanner:
    """
    Helper class để lập kế hoạch thoát hiểm với timing chính xác
    Đảm bảo bot luôn có đường thoát TRƯỚC KHI đặt bom
    """
    
    @staticmethod
    def calculate_escape_time(path_length: int, bot_speed: int) -> float:
        """
        Tính thời gian cần thiết để di chuyển theo đường đi (ms)
        
        Args:
            path_length: Số ô cần di chuyển
            bot_speed: Tốc độ bot (1-3 px/step)
        
        Returns:
            Thời gian cần thiết (ms)
        """
        from ...config import CELL_SIZE
        
        # Mỗi ô = 40px, bot speed = px mỗi step
        # Giả sử ~10ms mỗi step (100 ticks/s)
        pixels_needed = path_length * CELL_SIZE
        steps_needed = pixels_needed / bot_speed
        time_needed = steps_needed * 10  # 10ms per step
        
        # Thêm safety margin 50%
        return time_needed * 1.5
    
    @staticmethod
    def find_escape_path_from_bomb(
        bomb_position: Tuple[int, int],
        bot_position: Tuple[int, int],
        explosion_range: int,
        bomb_lifetime: float = 5000.0
    ) -> Optional[Tuple[List[Tuple[int, int]], float]]:
        """
        Tìm đường thoát từ vị trí bom
        
        Args:
            bomb_position: Vị trí bom sẽ đặt
            bot_position: Vị trí hiện tại của bot
            explosion_range: Tầm nổ của bom
            bomb_lifetime: Thời gian bom nổ (ms)
        
        Returns:
            (path, time_needed) hoặc None nếu không có đường thoát
        """
        from ...game_state import astar_shortest_path, game_state, get_bomber_speed
        from ...config import DIRECTIONS
        
        # Tính blast zone
        blast_zone = EscapePlanner._calculate_blast_zone(bomb_position, explosion_range)
        
        # Tìm các safe cells gần nhất (ngoài blast zone)
        # QUAN TRỌNG: Tính escape từ vị trí đặt bom, không phải vị trí hiện tại
        safe_cells = EscapePlanner._find_nearest_safe_cells(
            bomb_position, blast_zone, max_distance=8
        )
        
        if not safe_cells:
            logger.warning(f"⚠️ KHÔNG TÌM THẤY Ô AN TOÀN ngoài blast zone của {bomb_position}")
            return None
        
        # Thử tìm đường đến từng safe cell
        my_uid = game_state.get("my_uid")
        bot_speed = get_bomber_speed(my_uid)
        
        best_path = None
        best_time = float('inf')
        
        # logger.info(f"🛡️ TÌM ĐƯỜNG THOÁT: từ {bomb_position} đến {safe_cells[:5]}")
        
        for safe_cell in safe_cells[:5]:  # Chỉ thử 5 ô gần nhất
            # Tìm đường đi từ vị trí đặt bom
            path = astar_shortest_path(bomb_position, safe_cell, avoid_hazard=True, avoid_bots=False)
            
            if path and len(path) > 1:
                # Tính thời gian cần thiết
                escape_time = EscapePlanner.calculate_escape_time(len(path) - 1, bot_speed)
                # logger.info(f"🛡️ THỬ ĐƯỜNG: {bomb_position} → {safe_cell} ({len(path)-1} ô, {escape_time:.0f}ms)")
                
                # Kiểm tra có đủ thời gian không (cần thêm 20% safety margin)
                if escape_time < bomb_lifetime * 0.8:  # Chỉ dùng 80% thời gian
                    if escape_time < best_time:
                        best_time = escape_time
                        best_path = path
                        # logger.debug(
                        #     f"✅ TÌM THẤY ĐƯỜNG THOÁT: {len(path)-1} ô, "
                        #     f"thời gian={escape_time:.0f}ms, "
                        #     f"bom nổ sau={bomb_lifetime:.0f}ms"
                        # )
        
        if best_path:
            # logger.info(f"✅ TÌM THẤY ĐƯỜNG THOÁT TỐT NHẤT: {best_path[0]} → {best_path[-1]} ({best_time:.0f}ms)")
            return (best_path, best_time)
        
        # logger.warning(f"⚠️ KHÔNG CÓ ĐƯỜNG THOÁT ĐỦ NHANH từ {bomb_position}")
        return None
    
    @staticmethod
    def _calculate_blast_zone(
        bomb_position: Tuple[int, int],
        explosion_range: int
    ) -> set:
        """Tính vùng nổ của bom"""
        from ...game_state import game_state
        from ...config import DIRECTIONS
        
        blast_zone = set()
        blast_zone.add(bomb_position)
        
        # Tính vùng nổ theo 4 hướng
        map_data = game_state.get("map", [])
        
        # logger.info(f"💥 TÍNH BLAST ZONE: bom tại {bomb_position}, tầm nổ={explosion_range}")
        
        for direction, (dx, dy) in DIRECTIONS.items():
            for distance in range(1, explosion_range + 1):
                nx = bomb_position[0] + dx * distance
                ny = bomb_position[1] + dy * distance
                
                # Kiểm tra bounds
                if not (0 <= nx <= 15 and 0 <= ny <= 15):
                    break
                
                blast_zone.add((nx, ny))
                
                # === SPEC BOM NỔ ===
                # - Nổ qua ô trống
                # - Dừng TRƯỚC tường (không nổ tường)
                # - Dừng TẠI rương (nổ rương nhưng không nổ ô sau rương)
                try:
                    if ny < len(map_data) and nx < len(map_data[ny]):
                        cell_value = map_data[ny][nx]
                        # Dừng nếu gặp tường (W hoặc 1/x)
                        if cell_value == 'W' or cell_value == 1 or cell_value == 'x':
                            break
                        # Dừng sau khi nổ rương (r)
                        if cell_value == 'r':
                            # Đã add vào blast_zone ở trên, giờ dừng lại
                            break
                except:
                    break
        
        # logger.info(f"💥 BLAST ZONE: {sorted(blast_zone)}")
        return blast_zone
    
    @staticmethod
    def _find_nearest_safe_cells(
        bot_position: Tuple[int, int],
        blast_zone: set,
        max_distance: int = 8
    ) -> List[Tuple[int, int]]:
        """Tìm các ô an toàn gần nhất ngoài blast zone"""
        from .navigation import NavigationHelper
        
        safe_cells = []
        
        # Tìm theo vòng tròn mở rộng
        for distance in range(1, max_distance + 1):
            for dx in range(-distance, distance + 1):
                for dy in range(-distance, distance + 1):
                    if abs(dx) + abs(dy) != distance:  # Chỉ lấy vòng tròn
                        continue
                    
                    cell = (bot_position[0] + dx, bot_position[1] + dy)
                    
                    # Kiểm tra cell ngoài blast zone và có thể đi qua
                    if (cell not in blast_zone and
                        0 <= cell[0] <= 15 and 0 <= cell[1] <= 15 and
                        NavigationHelper.is_cell_passable(cell)):
                        safe_cells.append(cell)
            
            # Nếu đã tìm được safe cells, return luôn
            if safe_cells:
                return safe_cells
        
        return safe_cells
    
    @staticmethod
    def is_safe_to_place_bomb(
        bomb_position: Tuple[int, int],
        bot_position: Tuple[int, int],
        explosion_range: int,
        bomb_lifetime: float = 5000.0
    ) -> bool:
        """
        Kiểm tra CÓ AN TOÀN để đặt bom tại vị trí này không
        
        Returns:
            True nếu có đường thoát đủ nhanh, False otherwise
        """
        result = EscapePlanner.find_escape_path_from_bomb(
            bomb_position, bot_position, explosion_range, bomb_lifetime
        )
        
        if result:
            path, escape_time = result
            # logger.debug(
            #     f"✅ AN TOÀN ĐẶT BOM tại {bomb_position}: "
            #     f"có đường thoát {len(path)-1} ô, "
            #     f"thời gian={escape_time:.0f}ms < {bomb_lifetime:.0f}ms"
            # )
            return True
        
        # logger.warning(
        #     f"⚠️ KHÔNG AN TOÀN ĐẶT BOM tại {bomb_position}: "
        #     f"không có đường thoát đủ nhanh"
        # )
        return False
    
    @staticmethod
    def get_immediate_escape_direction(
        current_position: Tuple[int, int],
        bomb_position: Tuple[int, int],
        explosion_range: int
    ) -> Optional[str]:
        """
        Lấy hướng thoát hiểm NGAY LẬP TỨC sau khi đặt bom
        
        Returns:
            Direction string (UP/DOWN/LEFT/RIGHT) hoặc None
        """
        result = EscapePlanner.find_escape_path_from_bomb(
            bomb_position, current_position, explosion_range
        )
        
        if not result:
            return None
        
        path, _ = result
        
        if len(path) < 2:
            return None
        
        # Lấy bước đầu tiên trong path
        next_cell = path[1]
        dx = next_cell[0] - current_position[0]
        dy = next_cell[1] - current_position[1]
        
        if dx > 0:
            return "RIGHT"
        elif dx < 0:
            return "LEFT"
        elif dy > 0:
            return "DOWN"
        elif dy < 0:
            return "UP"
        
        return None

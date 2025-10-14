"""
Scoring helpers để đánh giá moves
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class ScoringHelper:
    """Helper class để tính điểm cho các moves"""
    
    @staticmethod
    def calculate_move_score(current_cell: Tuple[int, int], next_cell: Tuple[int, int], 
                            current_time: float, visited_cells: set) -> float:
        """Tính điểm cho một nước đi"""
        from .danger import DangerDetector
        from .navigation import NavigationHelper
        from ...game_state import game_state
        
        score = 0.0
        
        # 1. Tránh nguy hiểm
        if not DangerDetector.is_in_danger(next_cell, current_time):
            score += 30.0
        
        # 2. Tránh bot khác
        distance_from_enemies = ScoringHelper._get_distance_from_nearest_enemy(next_cell)
        if distance_from_enemies > 0:
            score += distance_from_enemies * 25.0
        
        # 3. Hướng về item/chest
        nearby_items = ScoringHelper._get_nearby_items(next_cell, radius=3)
        if nearby_items:
            score += len(nearby_items) * 10.0
        
        # 4. Không gian mở
        open_space = ScoringHelper._count_open_spaces(next_cell, radius=2)
        score += open_space * 5.0
        
        # 5. Tránh lặp lại
        if next_cell in visited_cells:
            score -= 20.0
        
        return score
    
    @staticmethod
    def _get_distance_from_nearest_enemy(cell: Tuple[int, int]) -> int:
        """Khoảng cách đến enemy gần nhất"""
        from ...game_state import game_state, pos_to_cell_bot
        
        my_uid = game_state.get("my_uid")
        min_distance = 999
        
        for bomber in game_state.get("bombers", []):
            if bomber.get("uid") == my_uid or not bomber.get("isAlive", True):
                continue
                
            bomber_cell = pos_to_cell_bot(bomber.get("x", 0), bomber.get("y", 0))
            distance = abs(bomber_cell[0] - cell[0]) + abs(bomber_cell[1] - cell[1])
            min_distance = min(min_distance, distance)
        
        return min_distance if min_distance < 999 else 0
    
    @staticmethod
    def _get_nearby_items(cell: Tuple[int, int], radius: int) -> list:
        """Tìm items gần"""
        from ...game_state import game_state
        
        items = []
        try:
            item_tile_map = game_state.get("item_tile_map", {})
            for (x, y), item_type in item_tile_map.items():
                distance = abs(x - cell[0]) + abs(y - cell[1])
                if distance <= radius:
                    items.append((x, y))
            
            chest_tile_map = game_state.get("chest_tile_map", {})
            for (x, y) in chest_tile_map.keys():
                distance = abs(x - cell[0]) + abs(y - cell[1])
                if distance <= radius:
                    items.append((x, y))
        except:
            pass
        return items
    
    @staticmethod
    def _count_open_spaces(cell: Tuple[int, int], radius: int) -> int:
        """Đếm ô trống xung quanh"""
        from .navigation import NavigationHelper
        
        count = 0
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                check_cell = (cell[0] + dx, cell[1] + dy)
                if NavigationHelper.is_cell_passable(check_cell):
                    count += 1
        return count

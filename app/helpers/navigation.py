"""
Navigation helpers
"""

import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


class NavigationHelper:
    """Helper class cho navigation và pathfinding"""
    
    @staticmethod
    def is_cell_passable(cell: Tuple[int, int], avoid_bombs: bool = False) -> bool:
        """
        Kiểm tra ô có thể đi qua không
        
        Args:
            cell: Vị trí (1-indexed)
            avoid_bombs: Có tránh blast zones của bombs không
        """
        from ..game_state import get_fast_state
        
        fs = get_fast_state()
        if not fs.static:
            return False
        cx, cy = cell
        if not fs.static.in_bounds(cx, cy):
            return False
        walkable = fs.walkable_mask(avoid_hazard=False)
        if not walkable[cy, cx]:
            return False
        
        # Check bomb blast zones nếu được yêu cầu
        if avoid_bombs:
            try:
                from ..models.bomb_tracker import get_bomb_tracker
                bomb_tracker = get_bomb_tracker()
                if bomb_tracker.is_cell_dangerous(cell):
                    return False
            except Exception:
                pass
        
        return True
    
    @staticmethod
    def get_neighbors(cell: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Lấy các ô lân cận có thể đi qua"""
        from ..config import DIRECTIONS
        
        neighbors = []
        for dx, dy in DIRECTIONS.values():
            next_cell = (cell[0] + dx, cell[1] + dy)
            if NavigationHelper.is_cell_passable(next_cell):
                neighbors.append(next_cell)
        return neighbors
    
    @staticmethod
    def find_safe_cells(current_cell: Tuple[int, int], current_time: float, radius: int = 6) -> List[Tuple[int, int]]:
        """Tìm các ô an toàn trong bán kính"""
        from .danger import DangerDetector
        
        safe_cells = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                target = (current_cell[0] + dx, current_cell[1] + dy)
                if (0 <= target[0] <= 15 and 0 <= target[1] <= 15 and
                    NavigationHelper.is_cell_passable(target) and
                    not DangerDetector.is_in_danger(target, current_time + 2000)):
                    safe_cells.append(target)
        return safe_cells
    
    @staticmethod
    def can_reach_goal(current_cell: Tuple[int, int], goal_cell: Tuple[int, int]) -> bool:
        """Kiểm tra có thể đến đích không"""
        from ..game_state import bfs_shortest_path
        
        try:
            path = bfs_shortest_path(current_cell, goal_cell)
            return path is not None and len(path) > 1
        except Exception:
            return (abs(goal_cell[0] - current_cell[0]) + abs(goal_cell[1] - current_cell[1])) <= 3

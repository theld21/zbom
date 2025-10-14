"""
Movement planning và execution
"""

import logging
import time
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger("bot")


# Global movement plan
movement_plan = {
    "path": [],
    "current_target_index": 0,
    "orient": None,
    "target_cell": None,
    "remaining_px": 0.0,
    "skip_once": False,
    "long_term_goal": None,
    "path_valid": False,
}


class MovementPlanner:
    """Quản lý kế hoạch di chuyển"""
    
    @staticmethod
    def reset():
        """Reset movement plan"""
        global movement_plan
        movement_plan["path"] = []
        movement_plan["current_target_index"] = 0
        movement_plan["orient"] = None
        movement_plan["target_cell"] = None
        movement_plan["remaining_px"] = 0.0
        movement_plan["skip_once"] = False
        movement_plan["long_term_goal"] = None
        movement_plan["path_valid"] = False
    
    @staticmethod
    def plan_long_term_path(goal_cell: Tuple[int, int]) -> None:
        """Lập kế hoạch đường đi dài hạn"""
        from ..game_state import get_my_bomber, pos_to_cell, astar_shortest_path, is_passable
        
        me = get_my_bomber()
        if not me:
            logger.warning(f"🚫 PLAN FAILED: Không tìm thấy bot")
            return
            
        current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
        logger.info(f"🗺️ LẬP PLAN: từ {current_cell} đến {goal_cell}")
        
        # Sử dụng A* để tìm đường đi
        path = astar_shortest_path(current_cell, goal_cell, avoid_hazard=True, avoid_bots=False)
        
        if path and len(path) > 1:
            movement_plan["path"] = path
            movement_plan["current_target_index"] = 1
            movement_plan["long_term_goal"] = goal_cell
            movement_plan["path_valid"] = True
            logger.info(f"🗺️ PLAN DÀI HẠN: {len(path)} ô từ {current_cell} đến {goal_cell}")
            logger.info(f"🗺️ PATH CHI TIẾT: {path}")
        else:
            # Fallback: kiểm tra mục tiêu có thể đi được không
            if is_passable(goal_cell[0], goal_cell[1]):
                movement_plan["path"] = [current_cell, goal_cell]
                movement_plan["current_target_index"] = 1
                movement_plan["long_term_goal"] = goal_cell
                movement_plan["path_valid"] = True
                logger.info(f"🗺️ PLAN ĐƠN GIẢN: từ {current_cell} đến {goal_cell}")
            else:
                logger.warning(f"🚫 MỤC TIÊU KHÔNG THỂ ĐI: {goal_cell}")
                MovementPlanner.reset()
    
    @staticmethod
    def get_next_direction() -> Optional[str]:
        """Lấy hướng di chuyển tiếp theo"""
        from ..game_state import get_my_bomber, pos_to_cell
        from ..config import DIRECTIONS
        
        if not movement_plan["path"] or movement_plan["current_target_index"] >= len(movement_plan["path"]):
            return None
            
        me = get_my_bomber()
        if not me:
            return None
            
        current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
        target_cell = movement_plan["path"][movement_plan["current_target_index"]]
        
        # Tính hướng di chuyển
        dx = target_cell[0] - current_cell[0]
        dy = target_cell[1] - current_cell[1]
        
        if dx > 0:
            return "RIGHT"
        elif dx < 0:
            return "LEFT"
        elif dy > 0:
            return "DOWN"
        elif dy < 0:
            return "UP"
        else:
            # Đã đến ô mục tiêu
            movement_plan["current_target_index"] += 1
            if movement_plan["current_target_index"] < len(movement_plan["path"]):
                return MovementPlanner.get_next_direction()
            return None
    
    @staticmethod
    def advance_move_plan() -> Optional[str]:
        """Tiến hành di chuyển theo plan"""
        from ..game_state import get_my_bomber, pos_to_cell
        from ..config import CELL_SIZE, ARRIVAL_TOLERANCE_PX
        
        me = get_my_bomber()
        if not me:
            MovementPlanner.reset()
            return None
            
        if not movement_plan["path_valid"] or not movement_plan["path"]:
            return None
            
        current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
        direction = MovementPlanner.get_next_direction()
        
        if not direction:
            logger.info(f"✅ HOÀN THÀNH PATH: đã đến mục tiêu {movement_plan['long_term_goal']}")
            MovementPlanner.reset()
            return None
        
        movement_plan["orient"] = direction
        target_cell = movement_plan["path"][movement_plan["current_target_index"]]
        movement_plan["target_cell"] = target_cell
        
        # Tính toán arrival
        goal_center_x = target_cell[0] * CELL_SIZE + CELL_SIZE // 2
        goal_center_y = target_cell[1] * CELL_SIZE + CELL_SIZE // 2
        curx, cury = me.get("x", 0.0), me.get("y", 0.0)
        
        dx_px = abs(curx - goal_center_x)
        dy_px = abs(cury - goal_center_y)
        distance = dx_px + dy_px
        
        large_tolerance = max(ARRIVAL_TOLERANCE_PX, 15.0)
        arrived = (distance <= large_tolerance)
        
        if direction == "RIGHT":
            remain_px = max(0.0, goal_center_x - curx)
        elif direction == "LEFT":
            remain_px = max(0.0, curx - goal_center_x)
        elif direction == "DOWN":
            remain_px = max(0.0, goal_center_y - cury)
        else:  # UP
            remain_px = max(0.0, cury - goal_center_y)
            
        movement_plan["remaining_px"] = float(remain_px)
        
        if arrived:
            movement_plan["current_target_index"] += 1
            logger.info(f"✅ ĐẾN Ô: {target_cell}")
        
        return direction


def reset_movement_plan():
    """Reset movement plan (helper function)"""
    MovementPlanner.reset()

"""
Bot Controller - Quản lý logic di chuyển của bot
Tách riêng để dễ debug và sửa lỗi movement
"""

import logging
import time
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class BotController:
    """Controller quản lý toàn bộ logic di chuyển của bot"""
    
    def __init__(self):
        # Movement state
        self.last_move_emit_time = 0.0
        self.arrival_block_until = 0.0
        self.last_pos = (0.0, 0.0)
        self.stuck_count = 0
        
    def reset(self):
        """Reset controller state"""
        self.last_move_emit_time = 0.0
        self.arrival_block_until = 0.0
        self.last_pos = (0.0, 0.0)
        self.stuck_count = 0
    
    def can_emit_move_now(self, max_cmds_per_sec: float) -> bool:
        """Kiểm tra có thể gửi lệnh di chuyển không"""
        min_interval = 1.0 / max(1.0, max_cmds_per_sec)
        now = time.monotonic()
        return (now - self.last_move_emit_time) >= min_interval
    
    def update_last_move_time(self):
        """Cập nhật thời gian gửi lệnh cuối"""
        self.last_move_emit_time = time.monotonic()
    
    def is_in_arrival_block(self) -> bool:
        """Kiểm tra có đang trong arrival block không"""
        return time.monotonic() < self.arrival_block_until
    
    def set_arrival_block(self, reverse_lock_seconds: float):
        """Đặt arrival block để tránh đảo chiều"""
        self.arrival_block_until = time.monotonic() + reverse_lock_seconds
    
    async def execute_action(self, action: Dict[str, Any], send_move_func, send_bomb_func, 
                            movement_planner, survival_ai, game_state, 
                            cell_size: int, reverse_lock_seconds: float, log_map: bool) -> bool:
        """
        Thực thi action từ AI
        
        Returns:
            bool: True nếu có progress, False nếu không
        """
        if not action:
            return False
        
        action_type = action.get("type")
        
        if action_type == "move":
            goal_cell = action.get("goal_cell")
            if not goal_cell:
                return False
            
            # Log vị trí bot
            from .game_state import get_my_bomber, pos_to_cell
            me = get_my_bomber()
            if me:
                current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
            
            # Log map nếu cần
            if log_map:
                from .utils.loggers import log_map_state
                log_map_state(game_state, True)
            
            # Plan path
            movement_planner.plan_path(goal_cell)
            
            # QUAN TRỌNG: Kiểm tra xem có tìm được path không!
            if not movement_planner.plan.get("path_valid"):
                # Clear plan trong survival AI để tạo plan mới
                survival_ai.current_plan = None
                return False
            
            # Lưu plan_type và escape_path từ action
            if action.get("plan_type"):
                movement_planner.plan["plan_type"] = action["plan_type"]
            
            # Lưu escape_path nếu có
            if action.get("escape_path"):
                movement_planner.plan["escape_path"] = action["escape_path"]
            
            # Lấy direction tiếp theo
            direction = movement_planner.get_next_direction()
            if direction:
                await send_move_func(direction)
                movement_planner.plan["skip_once"] = True
                self.stuck_count = 0
                return True
        
        elif action_type == "bomb":
            await send_bomb_func()
            
            # Set flag escape
            survival_ai.must_escape_bomb = True
            
            # QUAN TRỌNG: LẬP ESCAPE PLAN NGAY SAU KHI ĐẶT BOM!
            escape_path = action.get("escape_path")
            if escape_path and len(escape_path) >= 2:
                movement_planner.plan_escape_path(escape_path)
            
            self.stuck_count = 0
            return True
        
        else:
            # Fallback: di chuyển theo orient
            direction = action.get("orient")
            if direction:
                # Check reverse lock
                if movement_planner.recent_orient and time.monotonic() < movement_planner.reverse_block_until:
                    reverse = {"UP":"DOWN","DOWN":"UP","LEFT":"RIGHT","RIGHT":"LEFT"}
                    if direction == reverse.get(movement_planner.recent_orient):
                        return False
                
                await send_move_func(direction)
                self.stuck_count = 0
                return True
        
        return False
    
    async def execute_plan_continuation(self, movement_planner, send_move_func, 
                                       cell_size: int, reverse_lock_seconds: float) -> bool:
        """
        Tiếp tục thực hiện plan dài hạn
        
        Returns:
            bool: True nếu có progress
        """
        plan = movement_planner.plan
        
        if not plan["path_valid"] or not plan["path"]:
            return False
        
        if plan.get("skip_once"):
            plan["skip_once"] = False
            return False
        
        # Advance plan
        movement_planner.advance(cell_size, reverse_lock_seconds)
        current_orient = plan["orient"]
        
        if current_orient and current_orient in ["UP", "DOWN", "LEFT", "RIGHT"]:
            await send_move_func(current_orient)
            self.stuck_count = 0
            return True
        
        return False
    
    async def handle_plan_completion(self, movement_planner, survival_ai, send_bomb_func) -> bool:
        """
        Xử lý khi plan hoàn thành
        
        Returns:
            bool: True nếu có action (đặt bom)
        """
        plan = movement_planner.plan
        
        # Kiểm tra just_completed
        if plan.get("just_completed"):
            completed_time = plan["just_completed"]
            if time.time() - completed_time < 1.0:
                # Đặt bom nếu là bomb_chest plan
                if not plan.get("bomb_placed"):
                    plan_type = plan.get("plan_type")
                    
                    if plan_type == "bomb_chest":
                        from .game_state import get_my_bomber, pos_to_cell
                        me = get_my_bomber()
                        if me:
                            current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
                            # Convert to int for comparison
                            current_cell_int = (int(current_cell[0]), int(current_cell[1]))
                            goal_cell = plan.get("long_term_goal")
                            
                            # QUAN TRỌNG: CHỈ đặt bom khi bot THỰC SỰ Ở goal_cell!
                            if goal_cell and current_cell_int != goal_cell:
                                # logger.warning(f"⚠️ Bot chưa đến goal_cell! Hiện tại: {current_cell_int}, Goal: {goal_cell}")
                                return False
                            
                            if not plan.get("logged_bomb_action"):
                                plan["logged_bomb_action"] = True
                            
                            # Đặt bom
                            await send_bomb_func()
                            plan["bomb_placed"] = True
                            
                            # Set escape flag
                            survival_ai.must_escape_bomb = True
                            
                            # QUAN TRỌNG: Lấy escape_path từ movement plan (đã lưu trước đó) và lập ESCAPE PLAN!
                            escape_path = plan.get("escape_path", [])
                            if escape_path and len(escape_path) >= 2:
                                movement_planner.plan_escape_path(escape_path)
                            # XÓA các field đã dùng để tránh đặt bom lại lần nữa
                            plan.pop("escape_path", None)
                            plan.pop("just_completed", None)
                            plan.pop("plan_type", None)
                            plan.pop("logged_bomb_action", None)
                            
                            return True
                    else:
                        if not plan.get("logged_bomb_action"):
                            plan["logged_bomb_action"] = True
                return False
            else:
                # Hết delay
                plan.pop("just_completed", None)
                plan.pop("bomb_placed", None)
                plan.pop("logged_bomb_action", None)
                plan.pop("plan_type", None)
        
        # Đặt bom tại target nếu cần
        if plan.get("need_bomb_at_target"):
            target_cell = plan["need_bomb_at_target"]
            await send_bomb_func()
            
            # Set escape flag
            survival_ai.must_escape_bomb = True
            
            plan.pop("need_bomb_at_target", None)
            plan["bomb_placed"] = True
            return True
        
        return False

# Global controller instance
bot_controller = BotController()

def get_bot_controller() -> BotController:
    """Lấy bot controller instance"""
    return bot_controller


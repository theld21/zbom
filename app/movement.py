"""Movement - Lập kế hoạch và thực hiện di chuyển"""
import logging
import time
from typing import Optional, Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

class MovementPlanner:
    """Quản lý kế hoạch di chuyển dài hạn"""
    
    def __init__(self):
        self.plan = {
            "path": [],                # Danh sách các ô cần đi qua
            "current_target_index": 0, # Chỉ số ô hiện tại
            "orient": None,            # Hướng hiện tại
            "target_cell": None,       # Ô đang nhắm tới
            "remaining_px": 0.0,       # Pixel còn lại
            "skip_once": False,        # Skip 1 lần gửi
            "long_term_goal": None,    # Mục tiêu dài hạn
            "path_valid": False,       # Đường đi hợp lệ
            "just_completed": None,    # Timestamp hoàn thành
        }
        
        # Anti-oscillation
        self.oscillation_detector: List[str] = []
        
        # Anti-reverse
        self.recent_orient: Optional[str] = None
        self.reverse_block_until: float = 0.0
        
    def reset(self):
        """Reset movement plan"""
        self.plan["path"] = []
        self.plan["current_target_index"] = 0
        self.plan["orient"] = None
        self.plan["target_cell"] = None
        self.plan["remaining_px"] = 0.0
        self.plan["skip_once"] = False
        self.plan["long_term_goal"] = None
        self.plan["path_valid"] = False
        self.plan.pop("just_completed", None)
        self.plan.pop("bomb_placed", None)
        self.plan.pop("logged_bomb_action", None)
        self.plan.pop("plan_type", None)
        self.plan.pop("is_escape_plan", None)  # Clear escape plan flag
        self.plan.pop("escape_path", None)  # QUAN TRỌNG: Xóa escape_path cũ!
        self.oscillation_detector = []
        
    def detect_oscillation(self, direction: str) -> bool:
        """Phát hiện oscillation"""
        self.oscillation_detector.append(direction)
        
        if len(self.oscillation_detector) > 10:
            self.oscillation_detector = self.oscillation_detector[-10:]
        
        if len(self.oscillation_detector) < 4:
            return False
        
        # Pattern A-B-A-B
        last_4 = self.oscillation_detector[-4:]
        if (last_4[0] == last_4[2] and last_4[1] == last_4[3] and 
            last_4[0] != last_4[1]):
            return True
        
        return False
    
    def plan_escape_path(self, escape_path: List[Tuple[int, int]]) -> None:
        """
        Lập plan theo escape path đã tính sẵn (sau khi đặt bom)
        
        Args:
            escape_path: Danh sách các ô cần đi qua để thoát hiểm
        """
        from .game_state import get_my_bomber, pos_to_cell_int
        
        me = get_my_bomber()
        if not me:
            return
        
        current_cell = pos_to_cell_int(me.get("x", 0), me.get("y", 0))
        
        # Lọc path: bỏ ô hiện tại nếu đang ở đó
        filtered_path = [cell for cell in escape_path if cell != current_cell]
        
        if not filtered_path:
            return
        
        # Set escape plan
        self.plan["path"] = filtered_path
        self.plan["current_target_index"] = 0
        self.plan["target_cell"] = filtered_path[0] if filtered_path else None
        self.plan["long_term_goal"] = filtered_path[-1] if filtered_path else None
        self.plan["path_valid"] = True
        self.plan["orient"] = None
        self.plan["is_escape_plan"] = True  # QUAN TRỌNG: Đánh dấu đây là escape plan để KHÔNG áp dụng chống đảo chiều!
        self.plan.pop("just_completed", None)
        
        # RESET reverse lock để không block hướng thoát!
        self.reverse_block_until = 0
        self.recent_orient = None

    def plan_path(self, goal_cell: Tuple[int, int]) -> None:
        """Lập kế hoạch đường đi dài hạn"""
        from .game_state import get_my_bomber, pos_to_cell, pos_to_cell_int, astar_shortest_path, bfs_shortest_path, is_passable
        
        me = get_my_bomber()
        if not me:
            return
            
        current_cell = pos_to_cell_int(me.get("x", 0), me.get("y", 0))
        
        # Thử A* trước
        path = astar_shortest_path(current_cell, goal_cell, avoid_hazard=True, avoid_bots=False)
        
        if path and len(path) > 1:
            self.plan["path"] = path
            self.plan["current_target_index"] = 1
            self.plan["long_term_goal"] = goal_cell
            self.plan["path_valid"] = True
        else:
            # Thử BFS
            path_bfs = bfs_shortest_path(current_cell, goal_cell, avoid_hazard=True, avoid_bots=False)
            
            if path_bfs and len(path_bfs) > 1:
                self.plan["path"] = path_bfs
                self.plan["current_target_index"] = 1
                self.plan["long_term_goal"] = goal_cell
                self.plan["path_valid"] = True
            else:
                # Tìm ô thay thế gần nhất
                self.plan["path_valid"] = False
                
                best_cell = None
                min_distance = float('inf')
                for dx in range(-3, 4):
                    for dy in range(-3, 4):
                        if dx == 0 and dy == 0:
                            continue
                        test_cell = (goal_cell[0] + dx, goal_cell[1] + dy)
                        if test_cell != current_cell and is_passable(test_cell[0], test_cell[1]):
                            distance = abs(dx) + abs(dy)
                            if distance < min_distance:
                                min_distance = distance
                                best_cell = test_cell
                
                if best_cell and best_cell != current_cell:
                    # Tạo path đầy đủ từ current_cell đến best_cell (ô thay thế có thể đi được)
                    full_path = astar_shortest_path(current_cell, best_cell, avoid_hazard=True, avoid_bots=False)
                    if not full_path or len(full_path) <= 1:
                        # Thử BFS nếu A* thất bại
                        full_path = bfs_shortest_path(current_cell, best_cell, avoid_hazard=True, avoid_bots=False)
                    
                    if full_path and len(full_path) > 1:
                        self.plan["path"] = full_path
                        self.plan["current_target_index"] = 1
                        self.plan["long_term_goal"] = best_cell  # Mục tiêu là best_cell, không phải goal_cell
                        self.plan["path_valid"] = True
                    else:
                        # QUAN TRỌNG: Nếu KHÔNG TÌM ĐƯỢC path đầy đủ → KHÔNG TẠO PLAN SAI!
                        # Path chỉ 2 điểm [start, goal] sẽ khiến bot đi thẳng qua tường!
                        self.plan["path"] = []
                        self.plan["current_target_index"] = 0
                        self.plan["path_valid"] = False
                else:
                    self.plan["path"] = []
                    self.plan["current_target_index"] = 0
                    self.plan["path_valid"] = False
    
    def get_next_direction(self) -> Optional[str]:
        """Lấy hướng di chuyển tiếp theo"""
        if not self.plan["path"] or self.plan["current_target_index"] >= len(self.plan["path"]):
            return None
            
        from .game_state import get_my_bomber, pos_to_cell
        
        me = get_my_bomber()
        if not me:
            return None
            
        # Sử dụng pos_to_cell để có tọa độ chính xác (bao gồm .5)
        current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
        target_cell = self.plan["path"][self.plan["current_target_index"]]
        
        # QUAN TRỌNG: So sánh với tọa độ THỰC (current_cell), không làm tròn!
        # Vì nếu bot ở 13.5 và target là 13, làm tròn xuống sẽ cho kết quả sai (13 == 13)
        dx = target_cell[0] - current_cell[0]
        dy = target_cell[1] - current_cell[1]
        
        # Kiểm tra nếu đang ở .5 (giữa cell)
        is_at_half_y = abs(current_cell[1] % 1.0 - 0.5) < 0.1  # Đang ở giữa 2 ô dọc
        is_at_half_x = abs(current_cell[0] % 1.0 - 0.5) < 0.1  # Đang ở giữa 2 ô ngang
        
        # QUAN TRỌNG: Nếu bot đang ở .5 cell → ƯU TIÊN đi về ô nguyên TRƯỚC!
        # Vì server không cho phép đổi hướng khi đang ở giữa 2 ô
        if is_at_half_y and abs(dy) > 0.1:
            # Đang ở giữa 2 ô dọc → phải đi dọc để về ô nguyên trước
            direction = "DOWN" if dy > 0 else "UP"
            return direction
        elif is_at_half_x and abs(dx) > 0.1:
            # Đang ở giữa 2 ô ngang → phải đi ngang để về ô nguyên trước
            direction = "RIGHT" if dx > 0 else "LEFT"
            return direction
        # Nếu đã ở ô nguyên → di chuyển bình thường
        elif abs(dx) > 0.1:  # Có khoảng cách theo X
            return "RIGHT" if dx > 0 else "LEFT"
        elif abs(dy) > 0.1:  # Có khoảng cách theo Y
            return "DOWN" if dy > 0 else "UP"
        else:
            # Đã đến ô mục tiêu (dx, dy gần 0)
            self.plan["current_target_index"] += 1
            if self.plan["current_target_index"] < len(self.plan["path"]):
                return self.get_next_direction()
            return None
    
    def advance(self, cell_size: int, reverse_lock_seconds: float) -> None:
        """Thực hiện di chuyển theo plan"""
        from .game_state import get_my_bomber, pos_to_cell, pos_to_cell_int
        
        me = get_my_bomber()
        if not me:
            self.reset()
            return
            
        if not self.plan["path_valid"] or not self.plan["path"]:
            return
            
        # Check arrival TRƯỚC khi get direction
        # Bounds check để tránh IndexError
        if self.plan["current_target_index"] >= len(self.plan["path"]):
            self.reset()
            return
            
        target_cell = self.plan["path"][self.plan["current_target_index"]]
        self.plan["target_cell"] = target_cell
        
        curx, cury = me.get("x", 0.0), me.get("y", 0.0)
        actual_current_cell = pos_to_cell(curx, cury)
        
        # Định nghĩa current_time và direction ở đây để dùng trong cả arrived và else block
        current_time = time.monotonic()
        
        # Lấy direction hiện tại từ plan
        direction = self.plan.get("orient")
        
        # Logic mới: Chỉ coi là "arrived" khi bot ở chính xác cell (số nguyên)
        # Số nguyên = đã tới chính xác ô
        # Số lẻ (.5) = đang ở giữa cell, chưa tới
        
        from .game_state import is_at_exact_cell
        
        # Check if bot has arrived at the exact target cell
        # Sử dụng pos_to_cell để chuyển đổi tọa độ pixel thành cell
        from .game_state import pos_to_cell
        from .config import CELL_SIZE
        current_cell = pos_to_cell(curx, cury)
        
        # Bot đã đến khi:
        # 1. Tọa độ cell là số nguyên (không phải .5)
        # 2. Đúng ô mục tiêu
        # 3. Cách mép trên cùng của target cell từ 0-5px (giống logic pos_to_cell)
        arrived = (
            (current_cell[0] % 1.0 == 0.0 and current_cell[1] % 1.0 == 0.0) and
            (int(current_cell[0]) == target_cell[0] and int(current_cell[1]) == target_cell[1]) and
            (curx % CELL_SIZE <= 5 and cury % CELL_SIZE <= 5)
        )
        
        if arrived:
            self.plan["current_target_index"] += 1
            self.reverse_block_until = current_time + reverse_lock_seconds
            self.recent_orient = direction
            self.plan["orient"] = None
            
            # Lưu ô hiện tại để kiểm tra đảo chiều
            from .game_state import pos_to_cell_int
            self.plan["last_reverse_cell"] = pos_to_cell_int(curx, cury)
            
            # Check nếu đã hết path - CHỈ HOÀN THÀNH KHI ĐẾN Ô CUỐI CÙNG
            if self.plan["current_target_index"] >= len(self.plan["path"]):
                # Nếu hoàn thành ESCAPE PLAN, clear must_escape_bomb flag!
                was_escape_plan = self.plan.get("is_escape_plan", False)
                if was_escape_plan:
                    # Clear escape flag trong survival_ai
                    try:
                        from .survival_ai import survival_ai
                        if survival_ai:
                            survival_ai.must_escape_bomb = False
                    except Exception:
                        pass
                    # QUAN TRỌNG: Hoàn thành ESCAPE → XÓA HẾT plan_type, escape_path
                    # để bot_controller KHÔNG ĐẶT BOM!
                    self.plan["just_completed"] = time.time()
                    self.reset()  # Reset sạch sẽ, không giữ lại gì
                else:
                    # QUAN TRỌNG: Set just_completed TRƯỚC KHI reset để giữ plan_type!
                    self.plan["just_completed"] = time.time()
                    # Lưu các field quan trọng trước khi reset (CHỈ khi KHÔNG phải escape)
                    saved_plan_type = self.plan.get("plan_type")
                    saved_bomb_placed = self.plan.get("bomb_placed")
                    saved_escape_path = self.plan.get("escape_path")
                    self.reset()
                    # Khôi phục các field quan trọng
                    self.plan["just_completed"] = time.time()
                    if saved_plan_type:
                        self.plan["plan_type"] = saved_plan_type
                    if saved_bomb_placed:
                        self.plan["bomb_placed"] = saved_bomb_placed
                    if saved_escape_path:
                        self.plan["escape_path"] = saved_escape_path
                return
            else:
                # Chưa đến ô cuối cùng - tiếp tục đi đến ô tiếp theo
                next_target = self.plan["path"][self.plan["current_target_index"]]
            
            return
        else:
            # Nếu chưa đến đích, tiếp tục di chuyển theo hướng hiện tại
            direction = self.get_next_direction()
            if not direction:
                # CHỈ hoàn thành khi:
                # 1. Hết path (current_target_index >= len(path))
                # 2. VÀ đã đến đúng ô mục tiêu (current_cell == long_term_goal)
                if self.plan["current_target_index"] >= len(self.plan["path"]):
                    # Check xem bot đã thực sự đến ô mục tiêu chưa
                    from .game_state import pos_to_cell, get_my_bomber
                    me = get_my_bomber()
                    if me:
                        # Sử dụng pos_to_cell để có tọa độ chính xác (bao gồm .5)
                        current_pos = pos_to_cell(me.get("x", 0), me.get("y", 0))
                        goal_pos = self.plan.get("long_term_goal")
                        
                        # Chỉ coi là đã đến khi bot ở chính xác số nguyên (không phải .5)
                        is_exact = (current_pos[0] % 1.0 == 0.0 and current_pos[1] % 1.0 == 0.0)
                        current_pos_int = (int(current_pos[0]), int(current_pos[1]))
                        
                        if is_exact and current_pos_int == goal_pos:
                            # Nếu hoàn thành ESCAPE PLAN, clear must_escape_bomb flag!
                            was_escape_plan = self.plan.get("is_escape_plan", False)
                            if was_escape_plan:
                                # Clear escape flag trong survival_ai
                                try:
                                    from .survival_ai import survival_ai
                                    if survival_ai:
                                        survival_ai.must_escape_bomb = False
                                except Exception:
                                    pass
                                # QUAN TRỌNG: Hoàn thành ESCAPE → XÓA HẾT plan_type, escape_path
                                # để bot_controller KHÔNG ĐẶT BOM!
                                self.plan["just_completed"] = time.time()
                                self.reset()  # Reset sạch sẽ, không giữ lại gì
                            else:
                                # QUAN TRỌNG: Set just_completed TRƯỚC KHI reset để giữ plan_type!
                                self.plan["just_completed"] = time.time()
                                # Lưu các field quan trọng trước khi reset (CHỈ khi KHÔNG phải escape)
                                saved_plan_type = self.plan.get("plan_type")
                                saved_bomb_placed = self.plan.get("bomb_placed")
                                saved_escape_path = self.plan.get("escape_path")
                                self.reset()
                                # Khôi phục các field quan trọng
                                self.plan["just_completed"] = time.time()
                                if saved_plan_type:
                                    self.plan["plan_type"] = saved_plan_type
                                if saved_bomb_placed:
                                    self.plan["bomb_placed"] = saved_bomb_placed
                                if saved_escape_path:
                                    self.plan["escape_path"] = saved_escape_path
                            return
                        else:
                            return
                else:
                    return
                
            # Check oscillation
            if self.detect_oscillation(direction):
                self.reset()
                return
            
            # Check reverse - CHỈ chặn khi thực sự đảo chiều, không chặn khi tiếp tục plan
            # QUAN TRỌNG: KHÔNG áp dụng chống đảo chiều cho ESCAPE PLAN!
            is_escape = self.plan.get("is_escape_plan", False)
            if not is_escape and self.recent_orient and current_time < self.reverse_block_until:
                reverse = {"UP":"DOWN","DOWN":"UP","LEFT":"RIGHT","RIGHT":"LEFT"}
                if direction == reverse.get(self.recent_orient):
                    # CHỈ chặn nếu đang ở cùng một ô (thực sự đảo chiều)
                    # Không chặn nếu đang di chuyển theo plan bình thường
                    from .game_state import pos_to_cell_int
                    current_cell = pos_to_cell_int(curx, cury)
                    if current_cell == self.plan.get("last_reverse_cell"):
                        return
        
        # Tính remaining pixels
        goal_center_x = target_cell[0] * cell_size + cell_size // 2
        goal_center_y = target_cell[1] * cell_size + cell_size // 2
        
        if direction == "RIGHT":
            remain_px = max(0.0, goal_center_x - curx)
        elif direction == "LEFT":
            remain_px = max(0.0, curx - goal_center_x)
        elif direction == "DOWN":
            remain_px = max(0.0, goal_center_y - cury)
        else:  # UP
            remain_px = max(0.0, cury - goal_center_y)
            
        self.plan["remaining_px"] = float(remain_px)
        
        self.plan["orient"] = direction

# Singleton instance
_movement_planner: Optional[MovementPlanner] = None

def get_movement_planner() -> MovementPlanner:
    """Lấy singleton instance"""
    global _movement_planner
    if _movement_planner is None:
        _movement_planner = MovementPlanner()
    return _movement_planner


"""Movement Planner - Lập kế hoạch và thực hiện di chuyển"""
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
    
    def plan_path(self, goal_cell: Tuple[int, int]) -> None:
        """Lập kế hoạch đường đi dài hạn"""
        from ..game_state import get_my_bomber, pos_to_cell, pos_to_cell_int, pos_to_cell_int, astar_shortest_path, bfs_shortest_path, is_passable
        
        me = get_my_bomber()
        if not me:
            logger.warning(f"🚫 PLAN FAILED: Không tìm thấy bot")
            return
            
        current_cell = pos_to_cell_int(me.get("x", 0), me.get("y", 0))
        logger.info(f"🗺️ LẬP PLAN: từ {current_cell} đến {goal_cell}")
        
        # Thử A* trước
        path = astar_shortest_path(current_cell, goal_cell, avoid_hazard=True, avoid_bots=False)
        
        if path and len(path) > 1:
            self.plan["path"] = path
            self.plan["current_target_index"] = 1
            self.plan["long_term_goal"] = goal_cell
            self.plan["path_valid"] = True
            logger.info(f"🗺️ PLAN DÀI HẠN: {len(path)} ô từ {current_cell} đến {goal_cell}")
            logger.info(f"🗺️ PATH CHI TIẾT: {path}")
            
            # Hiển thị path từng bước
            for i, cell in enumerate(path):
                if i == 0:
                    logger.info(f"🗺️ BƯỚC {i}: {cell} (vị trí hiện tại)")
                elif i == len(path) - 1:
                    logger.info(f"🗺️ BƯỚC {i}: {cell} (mục tiêu cuối)")
                else:
                    logger.info(f"🗺️ BƯỚC {i}: {cell}")
        else:
            # Thử BFS
            path_bfs = bfs_shortest_path(current_cell, goal_cell, avoid_hazard=True, avoid_bots=False)
            
            if path_bfs and len(path_bfs) > 1:
                self.plan["path"] = path_bfs
                self.plan["current_target_index"] = 1
                self.plan["long_term_goal"] = goal_cell
                self.plan["path_valid"] = True
                logger.info(f"🗺️ PLAN BFS: {len(path_bfs)} ô từ {current_cell} đến {goal_cell}")
                logger.info(f"🗺️ PATH CHI TIẾT: {path_bfs}")
                
                # Hiển thị path từng bước
                for i, cell in enumerate(path_bfs):
                    if i == 0:
                        logger.info(f"🗺️ BƯỚC {i}: {cell} (vị trí hiện tại)")
                    elif i == len(path_bfs) - 1:
                        logger.info(f"🗺️ BƯỚC {i}: {cell} (mục tiêu cuối)")
                    else:
                        logger.info(f"🗺️ BƯỚC {i}: {cell}")
            else:
                # Tìm ô thay thế gần nhất
                logger.warning(f"❌ KHÔNG CÓ ĐƯỜNG ĐẾN: {goal_cell} từ {current_cell}")
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
                    # Tạo path đầy đủ từ current_cell đến goal_cell
                    from ..game_state import astar_shortest_path
                    full_path = astar_shortest_path(current_cell, goal_cell, avoid_hazard=True, avoid_bots=False)
                    if full_path and len(full_path) > 1:
                        self.plan["path"] = full_path
                        self.plan["current_target_index"] = 1
                        self.plan["long_term_goal"] = goal_cell
                        self.plan["path_valid"] = True
                        logger.info(f"🗺️ FALLBACK PATH: {len(full_path)} ô từ {current_cell} → {goal_cell}")
                    else:
                        # Nếu không có path đầy đủ, dùng path ngắn
                        self.plan["path"] = [current_cell, best_cell]
                        self.plan["current_target_index"] = 1
                        self.plan["long_term_goal"] = best_cell
                        self.plan["path_valid"] = True
                        logger.info(f"🗺️ FALLBACK PATH: {current_cell} → {best_cell}")
                else:
                    logger.warning(f"🚫 KHÔNG TÌM THẤY Ô THAY THẾ cho {goal_cell}")
                    self.plan["path"] = []
                    self.plan["current_target_index"] = 0
                    self.plan["path_valid"] = False
    
    def get_next_direction(self) -> Optional[str]:
        """Lấy hướng di chuyển tiếp theo"""
        if not self.plan["path"] or self.plan["current_target_index"] >= len(self.plan["path"]):
            return None
            
        from ..game_state import get_my_bomber, pos_to_cell, pos_to_cell_int
        
        me = get_my_bomber()
        if not me:
            return None
            
        current_cell = pos_to_cell_int(me.get("x", 0), me.get("y", 0))
        target_cell = self.plan["path"][self.plan["current_target_index"]]
        
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
            self.plan["current_target_index"] += 1
            if self.plan["current_target_index"] < len(self.plan["path"]):
                return self.get_next_direction()
            return None
    
    def advance(self, cell_size: int, reverse_lock_seconds: float) -> None:
        """Thực hiện di chuyển theo plan"""
        from ..game_state import get_my_bomber, pos_to_cell, pos_to_cell_int
        
        me = get_my_bomber()
        if not me:
            self.reset()
            return
            
        if not self.plan["path_valid"] or not self.plan["path"]:
            return
            
        # Check arrival TRƯỚC khi get direction
        # Bounds check để tránh IndexError
        if self.plan["current_target_index"] >= len(self.plan["path"]):
            logger.warning(f"🚫 INDEX OUT OF RANGE: current_target_index={self.plan['current_target_index']} >= path_len={len(self.plan['path'])}")
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
        
        from ..game_state import is_at_exact_cell
        
        # Check if bot has arrived at the exact target cell
        # Sử dụng pos_to_cell_int để consistency với get_next_direction
        current_cell_int = pos_to_cell_int(curx, cury)
        arrived = (
            current_cell_int[0] == target_cell[0] and
            current_cell_int[1] == target_cell[1]
        )
        
        from ..config import LOG_ARRIVAL_CHECK
        if LOG_ARRIVAL_CHECK:
            logger.info(f"🔍 ARRIVAL CHECK: bot({curx:.1f},{cury:.1f}) → cell{current_cell_int} vs target{target_cell} = {arrived}")
        
        if arrived:
            logger.info(f"✅ ĐẾN Ô: pixel({curx:.1f},{cury:.1f}) tile{current_cell_int} = target{target_cell}")
            self.plan["current_target_index"] += 1
            self.reverse_block_until = current_time + reverse_lock_seconds
            self.recent_orient = direction
            self.plan["orient"] = None
            
            # Check nếu đã hết path
            if self.plan["current_target_index"] >= len(self.plan["path"]):
                logger.info(f"✅ HOÀN THÀNH: đã đến {self.plan['long_term_goal']}")
                self.reset()
                # Set delay 1s cho AI
                self.plan["just_completed"] = time.time()
                return
            
            # CHỈ đặt bom khi đến ô cuối cùng của path
            if self.plan["current_target_index"] >= len(self.plan["path"]):
                # Đã đến ô cuối cùng - đặt bom
                if not self.plan.get("bomb_placed_at_target"):
                    logger.info(f"💣 ĐẾN ĐÍCH CUỐI CÙNG - CẦN ĐẶT BOM TẠI: {target_cell}")
                    self.plan["bomb_placed_at_target"] = True
                    self.plan["need_bomb_at_target"] = target_cell
            else:
                # Chưa đến ô cuối cùng - tiếp tục đi
                logger.info(f"📍 ĐẾN Ô TRUNG GIAN: {target_cell}, tiếp tục đến ô tiếp theo")
            
            return
        else:
            # Nếu chưa đến đích, tiếp tục di chuyển theo hướng hiện tại
            direction = self.get_next_direction()
            if not direction:
                # CHỈ hoàn thành khi thực sự hết path, không phải khi chưa đến đích
                if self.plan["current_target_index"] >= len(self.plan["path"]):
                    logger.info(f"✅ HOÀN THÀNH: đã đến {self.plan['long_term_goal']}")
                    self.reset()
                    # Set delay 1s cho AI
                    self.plan["just_completed"] = time.time()
                    return
                else:
                    logger.warning(f"🚫 KHÔNG CÓ HƯỚNG DI CHUYỂN: chưa đến đích nhưng không có direction")
                    return
                
            # Check oscillation
            if self.detect_oscillation(direction):
                logger.warning(f"🚫 PHÁT HIỆN OSCILLATION: {self.oscillation_detector[-4:]} - Reset plan!")
                self.reset()
                return
            
            # Check reverse
            if self.recent_orient and current_time < self.reverse_block_until:
                reverse = {"UP":"DOWN","DOWN":"UP","LEFT":"RIGHT","RIGHT":"LEFT"}
                if direction == reverse.get(self.recent_orient):
                    logger.warning(f"🚫 CHỐNG ĐẢO CHIỀU: Bỏ qua hướng {direction}")
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
        if remain_px > 0:
            logger.debug(f"🚶 ĐI: pixel({curx:.1f},{cury:.1f}) tile{actual_current_cell} → target{target_cell}, còn {remain_px:.1f}px")

# Singleton instance
_movement_planner: Optional[MovementPlanner] = None

def get_movement_planner() -> MovementPlanner:
    """Lấy singleton instance"""
    global _movement_planner
    if _movement_planner is None:
        _movement_planner = MovementPlanner()
    return _movement_planner


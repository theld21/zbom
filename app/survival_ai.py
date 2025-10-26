#!/usr/bin/env python3
"""
AI sinh tồn đơn giản - Chiến lược ưu tiên an toàn
"""

import time
import logging
from typing import List, Tuple, Optional, Dict, Any

from .config import DIRECTIONS, CELL_SIZE_PIXELS
from .game_state import (
    game_state, get_my_bomber, get_my_cell, get_bomber_explosion_range, 
    get_bomber_speed, get_bomber_bomb_count,
    get_tile_item, has_chest_at_tile, has_wall_at_tile, in_bounds,
    get_fast_state, bfs_shortest_path, astar_shortest_path, pos_to_cell, pos_to_cell_bot
)

# Import pathfinding module
import app.pathfinding as pathfinding

logger = logging.getLogger(__name__)

class SimpleSurvivalAI:
    """AI sinh tồn thông minh với bộ nhớ và chiến lược"""
    
    def __init__(self):
        self.last_action_time = 0
        self.last_action = None
        self.action_count = 0
        self.last_bomb_time_ms = 0.0
        
        # Bộ nhớ khám phá - tránh quay lại nơi đã đi
        self.visited_cells = set()
        self.exploration_targets = []
        self.last_exploration_time = 0
        self.exploration_radius = 5
        
        # Chiến lược dài hạn
        self.strategic_goals = []
        self.current_goal = None
        self.goal_priority = {
            'survival': 100,
            'items': 80,
            'exploration': 60,
            'bombing': 40
        }
        
        # Tránh oscillation
        self.movement_history = []
        self.oscillation_threshold = 3
        
        # Logic bom liên tục
        self.my_bombs = set()  # Theo dõi bom của mình
        self.bomb_exploded_time = 0.0  # Thời gian bom nổ cuối cùng
        self.continuous_bombing = True  # Bật chế độ đặt bom liên tục
        
        # Blacklist các vị trí đã thử và thất bại
        self.failed_bomb_positions = {}  # {position: timestamp} - vị trí đã thử và thất bại
        self.blacklist_duration = 10000  # 10 giây blacklist
        
        # Plan hiện tại
        self.current_plan = None
        
        # Flag thoát hiểm
        self.must_escape_bomb = False  # BẮT BUỘC thoát sau khi đặt bom
        
        # Theo dõi vị trí để phát hiện hồi sinh
        self._last_position = None
    
    # ========== HELPER METHODS - Tránh trùng lặp ==========
    
    @staticmethod
    def _in_bounds(x: int, y: int) -> bool:
        """Kiểm tra vị trí có trong bounds không"""
        return 0 <= x <= 15 and 0 <= y <= 15
    
    @staticmethod
    def _to_int_cell(cell: Tuple[float, float]) -> Tuple[int, int]:
        """Convert float cell to int cell"""
        return (int(cell[0]), int(cell[1]))
    
    def _get_my_uid(self) -> Optional[str]:
        """Lấy UID của bot (cached helper)"""
        return game_state.get("my_uid")
    
    def _get_all_enemies(self) -> List[Dict]:
        """Lấy danh sách tất cả địch còn sống"""
        my_uid = self._get_my_uid()
        return [b for b in game_state.get("bombers", []) 
                if b.get("uid") != my_uid and b.get("isAlive", True)]
    
    def reset_state(self):
        """Reset AI state về trạng thái ban đầu"""
        self.last_action_time = 0
        self.last_action = None
        self.action_count = 0
        self.last_bomb_time_ms = 0.0
        self.visited_cells.clear()
        self.exploration_targets.clear()
        self.last_exploration_time = 0
        self.strategic_goals.clear()
        self.current_goal = None
        self.movement_history.clear()
        self.my_bombs.clear()
        self.bomb_exploded_time = 0.0
        self.failed_bomb_positions.clear()
        self.current_plan = None
        self.must_escape_bomb = False
        
        # Reset oscillation detector nếu có
        if hasattr(self, '_oscillation_detector'):
            self._oscillation_detector.clear()
        
        # Reset vị trí theo dõi
        self._last_position = None
        
        logger.info(f"🔄 AI RESET: Đã reset toàn bộ trạng thái AI")
        
    def _get_move_time_ms(self, my_uid: str) -> float:
        """Tính thời gian di chuyển 1 bước (ms) dựa trên tốc độ"""
        speed = get_bomber_speed(my_uid)
        # Tốc độ 1 = 1px/bước, tốc độ 2 = 2px/bước, tốc độ 3 = 3px/bước
        # Thời gian di chuyển = 1000ms / tốc độ
        return 1000.0 / speed
        
    def _update_visited_cells(self, cell: Tuple[int, int]):
        """Cập nhật bộ nhớ các ô đã thăm"""
        self.visited_cells.add(cell)
        # Giữ tối đa 50 ô gần nhất
        if len(self.visited_cells) > 50:
            # Xóa các ô cũ nhất
            old_cells = list(self.visited_cells)[:-50]
            for old_cell in old_cells:
                self.visited_cells.discard(old_cell)
    
    def _is_oscillating(self) -> bool:
        """Kiểm tra xem có đang oscillation không"""
        if len(self.movement_history) < self.oscillation_threshold * 2:
            return False
            
        # Kiểm tra pattern A-B-A-B
        recent = self.movement_history[-self.oscillation_threshold * 2:]
        for i in range(0, len(recent) - 1, 2):
            if i + 1 < len(recent) and recent[i] == recent[i + 1]:
                return False
        return True
    
    def _get_exploration_targets(self, current_cell: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Tìm các mục tiêu khám phá chưa được thăm"""
        targets = []
        for dx in range(-self.exploration_radius, self.exploration_radius + 1):
            for dy in range(-self.exploration_radius, self.exploration_radius + 1):
                if dx == 0 and dy == 0:
                    continue
                target = (current_cell[0] + dx, current_cell[1] + dy)
                if (0 <= target[0] <= 15 and 0 <= target[1] <= 15 and 
                    target not in self.visited_cells and 
                    self._is_cell_passable(target)):
                    targets.append(target)
        return targets
    
    def _get_strategic_goal(self, current_cell: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Lập kế hoạch chiến lược thông minh - TRÁNH VÒNG LẶP"""
        # Kiểm tra vị trí hiện tại có hợp lệ không
        if not (0 <= current_cell[0] <= 15 and 0 <= current_cell[1] <= 15):
            logger.warning(f"🚫 VỊ TRÍ KHÔNG HỢP LỆ: {current_cell} - Tìm vị trí an toàn gần nhất")
            # Tìm vị trí an toàn gần nhất trong map
            for radius in range(1, 8):
                for dx in range(-radius, radius + 1):
                    for dy in range(-radius, radius + 1):
                        target = (current_cell[0] + dx, current_cell[1] + dy)
                        if (0 <= target[0] <= 15 and 0 <= target[1] <= 15 and 
                            self._is_cell_passable(target)):
                            logger.info(f"🎯 TÌM THẤY VỊ TRÍ AN TOÀN: {target}")
                            return target
            return None
        
        # 1. Ưu tiên sinh tồn - tìm nơi an toàn (ưu tiên ô chưa thăm)
        # Convert float to int for safe areas calculation
        current_cell_int = (int(current_cell[0]), int(current_cell[1]))
        safe_goals = self._find_safe_areas(current_cell_int)
        if safe_goals:
            # Ưu tiên ô chưa thăm VÀ CÓ ĐƯỜNG ĐI
            unexplored_safe = [goal for goal in safe_goals if goal not in self.visited_cells]
            if unexplored_safe:
                # QUAN TRỌNG: Kiểm tra xem có đường đi không!
                from .game_state import bfs_shortest_path
                for goal in unexplored_safe:
                    test_path = bfs_shortest_path(current_cell_int, goal, avoid_hazard=False, avoid_bots=False)
                    if test_path and len(test_path) > 1:
                        logger.info(f"🎯 CHỌN VÙNG AN TOÀN CHƯA THĂM (có đường): {goal}")
                        return goal
                # logger.warning(f"⚠️ CÁC VÙNG AN TOÀN CHƯA THĂM KHÔNG CÓ ĐƯỜNG ĐI!")  # Giảm log spam
            # Nếu không có unexplored hoặc không có đường đi, thử explored
            from .game_state import bfs_shortest_path
            for goal in safe_goals:
                test_path = bfs_shortest_path(current_cell_int, goal, avoid_hazard=False, avoid_bots=False)
                if test_path and len(test_path) > 1:
                    logger.info(f"🎯 CHỌN VÙNG AN TOÀN (có đường): {goal}")
                    return goal
            # logger.warning(f"⚠️ TẤT CẢ VÙNG AN TOÀN KHÔNG CÓ ĐƯỜNG ĐI!")  # Giảm log spam
            
        # 2. Tìm vật phẩm quan trọng (phải có đường đi, radius=10 để tìm xa hơn)
        item_goals = self._find_items(current_cell, radius=10, item_types=["S", "R", "B"])
        if item_goals:
            from .game_state import bfs_shortest_path
            for goal in item_goals:
                test_path = bfs_shortest_path(current_cell_int, goal, avoid_hazard=False, avoid_bots=False)
                if test_path and len(test_path) > 1:
                    logger.info(f"🎯 CHỌN ITEM QUAN TRỌNG (có đường): {goal}")
                    return goal
            # logger.warning(f"⚠️ CÁC ITEM KHÔNG CÓ ĐƯỜNG ĐI!")  # Giảm log spam
            
        # 3. Khám phá khu vực mới (ưu tiên ô xa VÀ CÓ ĐƯỜNG ĐI)
        exploration_goals = self._get_exploration_targets(current_cell)
        if exploration_goals:
            # QUAN TRỌNG: Kiểm tra xem có đường đi không! CHO PHÉP đi qua hazard
            from .game_state import bfs_shortest_path
            for goal in exploration_goals:
                test_path = bfs_shortest_path(current_cell_int, goal, avoid_hazard=False, avoid_bots=False)
                if test_path and len(test_path) > 1:
                    logger.info(f"🎯 CHỌN KHÁM PHÁ (có đường): {goal}")
                    return goal
            # logger.warning(f"⚠️ CÁC MỤC TIÊU KHÁM PHÁ KHÔNG CÓ ĐƯỜNG ĐI!")  # Giảm log spam
        
        # 4. Fallback: Tìm ô an toàn bất kỳ (tránh vòng lặp)
        safe_goal = self._find_safe_goal(current_cell, time.time() * 1000)
        if safe_goal:
            logger.info(f"🎯 FALLBACK AN TOÀN: {safe_goal}")
            return safe_goal
            
        # Nếu KHÔNG TÌM ĐƯỢC MỤC TIÊU NÀO → Bot bị TRAPPED
        logger.warning(f"🚧 BOT BỊ TRAPPED tại {current_cell} - ĐỨNG YÊN CHỜ ĐƯỜNG MỞ")
        return None
    
    def _execute_long_term_plan(self, plan: Dict, current_cell: Tuple[int, int], current_time: float, can_place_bomb: bool) -> Optional[Dict[str, Any]]:
        """Thực hiện plan dài hạn"""
        plan_type = plan.get("type")
        plan_goal = plan.get("goal_cell")
        
        if plan_type == "collect_item":
            logger.info(f"💎 PLAN DÀI HẠN - NHẶT VẬT PHẨM: đến {plan_goal}")
            self.last_action_time = current_time
            self._update_last_direction(current_cell, plan_goal)
            return {"type": "move", "goal_cell": plan_goal}
        elif plan_type == "bomb_chest":
            # So sánh int với float: (14, 4) == (14.0, 4.0)
            if (int(plan_goal[0]) == int(current_cell[0]) and 
                int(plan_goal[1]) == int(current_cell[1])):
                if can_place_bomb and self._should_place_bomb_for_chest(current_cell, current_time, can_place_bomb):
                    # Hiển thị plan chi tiết
                    bomb_pos = plan_goal
                    escape_pos = plan.get("escape_cell", "chưa tính")
                    escape_path = plan.get("escape_path", [])
                    
                    logger.info(f"💣 PLAN DÀI HẠN - ĐẶT BOM TẠI VỊ TRÍ HIỆN TẠI")
                    logger.info(f"🎯 PLAN CHI TIẾT: ĐẾN {bomb_pos} → ĐẶT BOM → THOÁT ĐẾN {escape_pos}")
                    if escape_path:
                        logger.info(f"🛡️ ĐƯỜNG THOÁT: {escape_path}")
                    
                    self.last_action_time = current_time
                    self.last_bomb_time_ms = current_time
                    self.must_escape_bomb = True
                    
                    # BLACKLIST vị trí bom VÀ BLAST ZONE!
                    self.failed_bomb_positions[current_cell] = current_time
                    
                    # Tính blast zone và blacklist tất cả các ô nguy hiểm
                    from .game_state import get_bomber_explosion_range, game_state
                    my_uid = game_state.get("my_uid")
                    explosion_range = get_bomber_explosion_range(my_uid) if my_uid else 2
                    blast_zone = pathfinding.calculate_blast_zone(current_cell, explosion_range)
                    
                    for blast_cell in blast_zone:
                        self.failed_bomb_positions[blast_cell] = current_time
                    
                    logger.warning(f"⚡ SET FLAG: must_escape_bomb = True + BLACKLIST {current_cell} + blast zone ({len(blast_zone)} ô)")
                    
                    # QUAN TRỌNG: Trả về bomb action KÈM escape_path để bot_controller thực thi!
                    # KHÔNG XÓA current_plan ở đây! bot_controller cần nó để lấy escape_path!
                    # self.current_plan sẽ được clear sau khi escape plan được lập xong
                    # QUAN TRỌNG: Blacklist vị trí đặt bom để tránh lặp lại!
                    self._add_to_blacklist(current_cell, current_time)
                    return {
                        "type": "bomb",
                        "escape_path": escape_path,  # ← GỬI KÈM ESCAPE PATH!
                        "escape_cell": escape_pos
                    }
                else:
                    logger.warning(f"🚫 KHÔNG THỂ ĐẶT BOM tại {current_cell}: blacklist 5s")
                    # BLACKLIST vị trí này để tránh lặp lại - QUAN TRỌNG: Blacklist cả blast zone!
                    self._add_to_blacklist(current_cell, current_time)
                    self.current_plan = None
                    # Tìm mục tiêu khác ngay
                    fallback = self._get_fallback_action(current_cell, current_time)
                    if fallback:
                        logger.info(f"🔄 CHUYỂN SANG MỤC TIÊU KHÁC")
                        return fallback
                    return None
            else:
                # Hiển thị plan chi tiết khi di chuyển
                bomb_pos = plan_goal
                escape_pos = plan.get("escape_cell", "chưa tính")
                escape_path = plan.get("escape_path", [])
                
                logger.info(f"💣 PLAN DÀI HẠN - ĐẾN VỊ TRÍ ĐẶT BOM: {plan_goal}")
                logger.info(f"🎯 PLAN CHI TIẾT: ĐẾN {bomb_pos} → ĐẶT BOM → THOÁT ĐẾN {escape_pos}")
                if escape_path:
                    logger.info(f"🛡️ ĐƯỜNG THOÁT: {escape_path}")
                
                self.last_action_time = current_time
                self._update_last_direction(current_cell, plan_goal)
                # QUAN TRỌNG: Truyền plan_type để bot_controller biết đặt bom khi đến đích!
                # VÀ LƯU VÀO self.current_plan để bot_controller lấy escape_path sau!
                action = {
                    "type": "move", 
                    "goal_cell": plan_goal, 
                    "plan_type": "bomb_chest",
                    "escape_path": escape_path  # QUAN TRỌNG: Gửi escape_path trong action
                }
                self.current_plan = {
                    "type": "bomb_chest",
                    "goal_cell": plan_goal,
                    "escape_cell": escape_pos,
                    "escape_path": escape_path
                }
                logger.info(f"📤 RETURN ACTION: {action}")
                logger.info(f"💾 LƯU escape_path vào ACTION: {escape_path}")
                return action
        elif plan_type == "explore":
            logger.info(f"🗺️ PLAN DÀI HẠN - KHÁM PHÁ: đến {plan_goal}")
            self.last_action_time = current_time
            self._update_last_direction(current_cell, plan_goal)
            return {"type": "move", "goal_cell": plan_goal}
        return None
    
    def _calculate_escape_plan(self, bomb_position: Tuple[int, int], current_cell: Tuple[int, int]) -> Dict[str, Any]:
        """Tính escape plan cho bomb position"""
        try:
            # Tính escape path từ bomb position
            escape_result = pathfinding.find_escape_path_from_bomb(
                bomb_position=bomb_position,
                bot_position=current_cell,
                explosion_range=2,  # Default explosion range
                bomb_lifetime=5000.0
            )
            
            if escape_result:
                escape_path, escape_time = escape_result
                return {
                    "escape_cell": escape_path[-1] if escape_path else None,
                    "escape_path": escape_path,
                    "escape_time": escape_time
                }
            else:
                return {
                    "escape_cell": None,
                    "escape_path": [],
                    "escape_time": 0
                }
        except Exception as e:
            logger.warning(f"⚠️ LỖI TÍNH ESCAPE PLAN: {e}")
            return {
                "escape_cell": None,
                "escape_path": [],
                "escape_time": 0
            }
    
    def _try_move_to(self, current_cell: Tuple[int, int], goal_cell: Tuple[int, int], current_time: float, label: str) -> Optional[Dict[str, Any]]:
        """Helper: Tạo move action nếu có thể đến goal"""
        if goal_cell and goal_cell != current_cell and self._can_reach_goal(current_cell, goal_cell):
            logger.info(f"{label}: đến {goal_cell}")
            self.last_action_time = current_time
            self._update_last_direction(current_cell, goal_cell)
            return {"type": "move", "goal_cell": goal_cell}
        return None
    
    def _get_fallback_action(self, current_cell: Tuple[int, int], current_time: float) -> Optional[Dict[str, Any]]:
        """Fallback strategies với ưu tiên rõ ràng"""
        if not (0 <= current_cell[0] <= 15 and 0 <= current_cell[1] <= 15):
            return None
        
        # 1. Thử các goals theo thứ tự ưu tiên
        strategies = [
            (self._get_strategic_goal(current_cell), "🎯 CHIẾN LƯỢC"),
            (self._find_safe_goal(current_cell, current_time), "🛡️ AN TOÀN"),
        ]
        
        for goal, label in strategies:
            if goal and goal not in self.movement_history[-3:]:
                action = self._try_move_to(current_cell, goal, current_time, label)
                if action:
                    return action
        
        # 2. Khám phá
        exploration_goals = self._get_exploration_targets(current_cell)
        if exploration_goals:
            best = max(exploration_goals, key=lambda g: abs(g[0] - current_cell[0]) + abs(g[1] - current_cell[1]))
            if best not in self.movement_history[-2:]:
                action = self._try_move_to(current_cell, best, current_time, "🔍 KHÁM PHÁ")
                if action:
                    return action
        
        # 3. Xử lý oscillation / stuck
        if self._is_oscillating():
            self.movement_history = []
        
        # 4. TẮT FALLBACK - BẮT BUỘC phải tìm được safe goal!
        logger.warning(f"🚫 KHÔNG CÓ FALLBACK - Bot phải tìm được safe goal!")
        return None
        
        # 5. TẮT RESET FALLBACK - BẮT BUỘC phải tìm được safe goal!
        logger.warning(f"🚫 KHÔNG CÓ RESET FALLBACK - Bot phải tìm được safe goal!")
        return None
            
        return None
    
    def _can_reach_goal(self, current_cell: Tuple[int, int], goal_cell: Tuple[int, int]) -> bool:
        """Kiểm tra có thể di chuyển đến mục tiêu không"""
        try:
            from .game_state import bfs_shortest_path
            path = bfs_shortest_path(current_cell, goal_cell)
            return path is not None and len(path) > 1
        except Exception:
            return (abs(goal_cell[0] - current_cell[0]) + abs(goal_cell[1] - current_cell[1])) <= 3
        
    def _find_safe_areas(self, current_cell: Tuple[int, int], radius: int = 3) -> List[Tuple[int, int]]:
        """Tìm các khu vực an toàn"""
        safe_areas = []
        current_time = time.time() * 1000
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                target = (current_cell[0] + dx, current_cell[1] + dy)
                if (self._in_bounds(target[0], target[1]) and 
                    self._is_cell_passable(target) and 
                    not self._is_in_danger(target, current_time)):
                    safe_areas.append(target)
        return safe_areas
    
    def _find_items(self, current_cell: Tuple[int, int], radius: int = 5, 
                    item_types: List[str] = None) -> List[Tuple[int, int]]:
        """
        Tìm items (MERGE 3 hàm: _find_important_items, _find_nearby_items, _get_nearby_items)
        
        Args:
            current_cell: Vị trí hiện tại
            radius: Bán kính tìm kiếm
            item_types: Loại items cần tìm (None = tất cả)
        """
        items = []
        try:
            item_tile_map = game_state.get("item_tile_map", {})
            for (x, y), item_type in item_tile_map.items():
                if not self._in_bounds(x, y):
                    continue
                if item_types and item_type not in item_types:
                    continue
                # Tính distance ĐÚNG INDENT!
                    distance = abs(x - current_cell[0]) + abs(y - current_cell[1])
                if distance <= radius:
                        items.append((x, y))
            
            # Thêm chests nếu không chỉ định item_types
            if not item_types:
                chest_tile_map = game_state.get("chest_tile_map", {})
                for (x, y) in chest_tile_map.keys():
                    distance = abs(x - current_cell[0]) + abs(y - current_cell[1])
                    if distance <= radius:
                        items.append((x, y))
        except Exception:
            pass
        return items
        
    def choose_next_action(self) -> Optional[Dict[str, Any]]:
        """Hàm quyết định chính - Ưu tiên sinh tồn với plan dài hạn"""
        logger.info(f"🎯 CHOOSE_NEXT_ACTION CALLED")
        
        # Kiểm tra trạng thái game
        if not game_state.get("game_started", False):
            logger.info(f"❌ RETURN NONE: game chưa start")
            return None
            
        # Kiểm tra map có tồn tại không (tránh lỗi sau khi hồi sinh)
        if not game_state.get("map") or len(game_state.get("map", [])) == 0:
            logger.warning(f"🚫 AI TẠM DỪNG: Map chưa sẵn sàng sau khi hồi sinh")
            return None
            
        me = get_my_bomber()
        if not me:
            logger.info(f"❌ RETURN NONE: không tìm thấy bot")
            return None
            
        # WORKAROUND: Server đôi khi set movable=False và không update lại
        # Chỉ block nếu THỰC SỰ bị stun (protectCooldown > 0 hoặc isAlive=False)
        if not me.get("movable", True):
            # Check xem có phải bị stun thật không
            protect_cooldown = me.get("protectCooldown", 0)
            is_alive = me.get("isAlive", True)
            
            # Chỉ block nếu:
            # - Đang bị protect (vừa hồi sinh)
            # - Hoặc đã chết
            if protect_cooldown > 0 or not is_alive:
                logger.warning(f"❌ BOT BỊ STUN THẬT: protectCooldown={protect_cooldown}, isAlive={is_alive}")
                return None
            else:
                # movable=False nhưng không có lý do rõ ràng -> BỎ QUA và tiếp tục
                logger.info(f"⚠️ IGNORE movable=False (có thể là animation delay)")
                # Tiếp tục xử lý bình thường
            
        current_cell = get_my_cell()
        if not current_cell:
            logger.info(f"❌ RETURN NONE: không lấy được current_cell")
            return None
        
        # Kiểm tra vị trí hiện tại có hợp lệ không
        if not (0 <= current_cell[0] <= 15 and 0 <= current_cell[1] <= 15):
            logger.warning(f"🚫 VỊ TRÍ BOT KHÔNG HỢP LỆ: {current_cell} - Bỏ qua AI")
            return None
        
        logger.info(f"✅ BOT INFO: position={current_cell}, movable={me.get('movable')}")
        
        # Cập nhật bộ nhớ khám phá
        self._update_visited_cells(current_cell)
        
        # Cập nhật theo dõi bom của mình
        self._update_my_bombs()
        
        # Reset plan nếu vị trí thay đổi đột ngột (hồi sinh)
        if hasattr(self, '_last_position'):
            if self._last_position and self._last_position != current_cell:
                distance = abs(current_cell[0] - self._last_position[0]) + abs(current_cell[1] - self._last_position[1])
                if distance > 3:  # Di chuyển xa hơn 3 ô = có thể hồi sinh
                    logger.info(f"🔄 VỊ TRÍ THAY ĐỔI: từ {self._last_position} đến {current_cell}, reset plan")
                    self.current_plan = None
                    self.movement_history.clear()
                    self.visited_cells.clear()
        self._last_position = current_cell
        
        # Lấy thông tin hiện tại
        current_time = time.time() * 1000  # ms
        my_uid = game_state.get("my_uid")
        can_place_bomb = get_bomber_bomb_count(my_uid) > 0
        
        # Tránh spam commands
        move_time = self._get_move_time_ms(my_uid)
        if current_time - self.last_action_time < move_time:
            time_left = move_time - (current_time - self.last_action_time)
            logger.info(f"⏰ THROTTLE: còn {time_left:.0f}ms")
            return None
        
        # 0. ƯU TIÊN TUYỆT ĐỐI - THOÁT SAU KHI ĐẶT BOM
        if self.must_escape_bomb:
            logger.warning(f"🏃 BẮT BUỘC THOÁT: vừa đặt bom, phải chạy ngay!")
            
            # QUAN TRỌNG: Kiểm tra xem movement planner đã có escape plan chưa
            # Nếu có rồi thì KHÔNG tạo action mới, để movement planner xử lý!
            from .movement import get_movement_planner
            movement_planner = get_movement_planner()
            if movement_planner.plan.get("is_escape_plan") and movement_planner.plan.get("path_valid"):
                logger.info(f"✅ ĐÃ CÓ ESCAPE PLAN trong movement planner - để nó xử lý!")
                self.must_escape_bomb = False  # Clear flag
                return None  # Trả về None để bot_controller dùng movement planner
            
            # Nếu chưa có escape plan, tạo action thoát khẩn cấp
            self.must_escape_bomb = False
            escape_move = self._get_escape_move(current_cell, current_time)
            if escape_move:
                self.last_action_time = current_time
                return escape_move
            # Nếu không tìm được đường thoát, cố gắng di chuyển bất kỳ hướng nào
            for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
                dx, dy = DIRECTIONS[direction]
                next_cell = (current_cell[0] + dx, current_cell[1] + dy)
                if self._is_cell_passable(next_cell):
                    logger.warning(f"🏃 THOÁT KHẨN CẤP: {direction}")
                    self.last_action_time = current_time
                    return {"type": "move", "goal_cell": next_cell}
            
            # Nếu không thể thoát, clear plan để tạo plan mới
            logger.warning(f"🚫 KHÔNG THỂ THOÁT: Clear plan và tạo plan mới")
            self.current_plan = None
        
        # 1. KIỂM TRA AN TOÀN TUYỆT ĐỐI - Chạy khỏi bom
        in_danger = self._is_in_danger(current_cell, current_time)
        if in_danger:
            logger.warning(f"🚨 ĐANG Ở VÙNG NGUY HIỂM: {current_cell}")
            safe_goal = self._find_safe_goal(current_cell, current_time)
            if safe_goal:
                logger.warning(f"🚨 THOÁT HIỂM: đến {safe_goal}")
                self.last_action_time = current_time
                return {"type": "move", "goal_cell": safe_goal}
            logger.warning(f"🚨 THOÁT HIỂM: Không tìm thấy nơi an toàn!")
            return None
        else:
            logger.debug(f"✅ KHÔNG NGUY HIỂM: {current_cell} an toàn")
        
        # QUAN TRỌNG: Kiểm tra xem có escape plan đang chạy không
        # Nếu có → KHÔNG TẠO ACTION MỚI, để movement planner xử lý!
        from .movement import get_movement_planner
        movement_planner = get_movement_planner()
        if movement_planner.plan.get("is_escape_plan") and movement_planner.plan.get("path_valid"):
            logger.warning(f"🏃 ĐANG ESCAPE - BỎ QUA TẠO ACTION MỚI!")
            return None  # Để movement planner tiếp tục escape
        
        # 1.5. LẬP PLAN DÀI HẠN - Mục tiêu rõ ràng
        # CHỈ tạo plan mới khi chưa có plan hoặc plan đã hoàn thành
        if not self.current_plan:
            logger.info(f"🎯 TẠO PLAN MỚI: chưa có current_plan")
            long_term_plan = self._create_long_term_plan(current_cell, current_time)
            if long_term_plan:
                self.current_plan = long_term_plan
                logger.info(f"✅ ĐÃ TẠO PLAN: {long_term_plan.get('type')} → {long_term_plan.get('goal_cell')}")
                return self._execute_long_term_plan(long_term_plan, current_cell, current_time, can_place_bomb)
            else:
                logger.warning(f"❌ KHÔNG TẠO ĐƯỢC PLAN: _create_long_term_plan return None")
        else:
            # Đang có plan cũ - tiếp tục thực hiện
            logger.debug(f"🔄 TIẾP TỤC PLAN CŨ: {self.current_plan.get('type')} → {self.current_plan.get('goal_cell')}")
            return self._execute_long_term_plan(self.current_plan, current_cell, current_time, can_place_bomb)
        
        # 1.6. ƯU TIÊN ĐẶT BOM LIÊN TỤC - Sau khi bom nổ
        if self._should_continue_bombing(current_cell, current_time, can_place_bomb):
            logger.info(f"💣 ĐẶT BOM LIÊN TỤC: tiếp tục sau khi bom nổ")
            self.last_action_time = current_time
            self.last_bomb_time_ms = current_time
            self.must_escape_bomb = True  # BẮT BUỘC thoát lần loop tiếp
            logger.warning(f"⚡ SET FLAG: must_escape_bomb = True (bomb liên tục)")
            # QUAN TRỌNG: Blacklist vị trí đặt bom để tránh lặp lại!
            self._add_to_blacklist(current_cell, current_time)
            return {"type": "bomb"}
        
        # 1.6.5. ƯU TIÊN THOÁT KHỎI VÙNG NGUY HIỂM SAU KHI ĐẶT BOM
        if self._should_escape_after_bomb(current_cell, current_time):
            logger.info(f"🏃 THOÁT KHỎI VÙNG NGUY HIỂM: sau khi đặt bom")
            escape_move = self._get_escape_move(current_cell, current_time)
            if escape_move:
                self.last_action_time = current_time
                return escape_move
        
        # 1.7 & 1.8. ƯU TIÊN TRÁNH BOT KHÁC (merge 2 bước)
        has_nearby, min_dist, dangerous = self._get_enemy_info(current_cell, max_radius=3)
        if has_nearby or dangerous:
            if has_nearby:
                logger.info(f"🤖 GẦN BOT KHÁC (distance={min_dist}): ưu tiên di chuyển thông minh")
            if dangerous:
                logger.info(f"🤖 TRÁNH BOT NGUY HIỂM: {len(dangerous)} bot mạnh")
            
            smart_move = self._get_smart_move_near_enemy(current_cell, current_time)
            if smart_move:
                self.last_action_time = current_time
                return smart_move
            else:
                logger.warning(f"⚠️ KHÔNG TÌM ĐƯỢC SMART MOVE: gần bot nhưng không có nước đi")
            
        # 4. BỎ QUA kiểm tra đứng im để bot luôn di chuyển
        # should_idle = self._should_idle(current_cell, current_time)
        # if should_idle:
        #     idle_time = current_time - self.last_action_time
        #     if idle_time > 2000:  # 2 giây
        #         logger.info(f"🚨 ĐÃ ĐỨNG IM QUÁ LÂU: {idle_time:.0f}ms, tìm cách thoát")
        #         for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
        #             dx, dy = DIRECTIONS[direction]
        #             next_cell = (current_cell[0] + dx, current_cell[1] + dy)
        #             if self._is_cell_passable(next_cell):
        #                 logger.info(f"🚨 THOÁT KẸT: di chuyển {direction} đến {next_cell}")
        #                 self._update_last_direction(current_cell, next_cell)
        #                 self.last_action_time = current_time
        #                 return {"type": "move", "goal_cell": next_cell}
        #         logger.info(f"🚨 KHÔNG THỂ THOÁT: tất cả hướng đều bị chặn")
        #     else:
        #         logger.info(f"🚫 QUYẾT ĐỊNH ĐỨNG IM: không có hành động nào (đã đứng im {idle_time:.0f}ms)")
        #     return None
            
        # 5. FALLBACK STRATEGIES
        fallback_action = self._get_fallback_action(current_cell, current_time)
        if fallback_action:
            # Clear plan khi dùng fallback
            self.current_plan = None
            logger.info(f"🔄 FALLBACK ACTION: {fallback_action}")
        else:
            logger.warning(f"🚫 KHÔNG CÓ ACTION: Không có safe move, bomb target, hay fallback!")
        return fallback_action
        
    def _update_last_direction(self, from_cell: Tuple[int, int], to_cell: Tuple[int, int]) -> None:
        """Cập nhật hướng di chuyển cuối cùng để tránh oscillation"""
        # Xử lý float: (14.0, 4.0) -> (14, 4)
        from_cell_int = (int(from_cell[0]), int(from_cell[1]))
        to_cell_int = (int(to_cell[0]), int(to_cell[1]))
        
        dx = to_cell_int[0] - from_cell_int[0]
        dy = to_cell_int[1] - from_cell_int[1]
        
        if dx > 0:
            direction = "RIGHT"
        elif dx < 0:
            direction = "LEFT"
        elif dy > 0:
            direction = "DOWN"
        elif dy < 0:
            direction = "UP"
        else:
            direction = None
            
        if direction:
            self._last_direction = direction
            # Cập nhật movement history để phát hiện oscillation
            self.movement_history.append(direction)
            # Giữ tối đa 10 hướng gần nhất
            if len(self.movement_history) > 10:
                self.movement_history = self.movement_history[-10:]
        
    def _get_enemy_info(self, cell: Tuple[int, int], max_radius: int = 999) -> Tuple[bool, int, List[Dict]]:
        """
        MERGE 3 hàm enemy: _has_enemies_nearby, _get_distance_from_nearest_enemy, _should_avoid_enemies
        
        Returns:
            (has_nearby, min_distance, dangerous_enemies)
        """
        from .game_state import pos_to_cell_bot
        
        enemies = self._get_all_enemies()
        if not enemies:
            return (False, 999, [])
        
        min_distance = 999
        dangerous = []
        has_nearby = False
        
        for bomber in enemies:
            bomber_x, bomber_y = bomber.get("x", 0), bomber.get("y", 0)
            bomber_cell = pos_to_cell_bot(bomber_x, bomber_y)
            distance = abs(bomber_cell[0] - cell[0]) + abs(bomber_cell[1] - cell[1])
            
            min_distance = min(min_distance, distance)
            
            if distance <= max_radius:
                has_nearby = True
            
            # Check dangerous enemy
            explosion_range = bomber.get("explosionRange", 2)
            bomb_count = bomber.get("bombCount", 1)
            if (explosion_range >= 5 and distance <= 6) or (bomb_count >= 3 and distance <= 5):
                dangerous.append(bomber)
        
        return (has_nearby, min_distance, dangerous)
        
    def _get_smart_move_near_enemy(self, current_cell: Tuple[int, int], current_time: float) -> Optional[Dict[str, Any]]:
        """Tìm nước đi thông minh khi gần bot khác - ưu tiên di chuyển tối ưu"""
        # Tìm vị trí tốt nhất để di chuyển (xa bot khác, gần item/chest, an toàn)
        best_move = None
        best_score = -1
        
        # Kiểm tra các hướng di chuyển có thể
        for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
            dx, dy = DIRECTIONS[direction]
            next_cell = (current_cell[0] + dx, current_cell[1] + dy)
            
            # Kiểm tra ô có thể đi được không
            if not self._is_cell_passable(next_cell):
                continue
                
            # Tính điểm cho hướng này
            score = self._calculate_move_score(current_cell, next_cell, current_time)
            
            if score > best_score:
                best_score = score
                best_move = next_cell
        
        if best_move:
            logger.info(f"🤖 DI CHUYỂN THÔNG MINH: từ {current_cell} đến {best_move} (score={best_score})")
            self._update_last_direction(current_cell, best_move)
            return {"type": "move", "goal_cell": best_move}
        
        return None
    
    def _calculate_move_score(self, current_cell: Tuple[int, int], next_cell: Tuple[int, int], current_time: float) -> float:
        """Tính điểm cho nước đi - cao hơn = tốt hơn"""
        score = 0.0
        
        # 1. Tránh bot khác (ưu tiên cao nhất)
        has_nearby, min_dist, _ = self._get_enemy_info(next_cell, max_radius=2)
        if not has_nearby:
            score += 100.0  # Tăng điểm để ưu tiên cao hơn
        
        # 1.5. Ưu tiên di chuyển xa khỏi bot khác
        if min_dist > 0 and min_dist < 999:
            score += min_dist * 25.0  # Tăng điểm để ưu tiên xa bot khác
        
        # 2. Tránh nguy hiểm
        if not self._is_in_danger(next_cell, current_time):
            score += 30.0  # Quan trọng - tránh bom/lửa
        
        # 3. Hướng về item/chest gần đó
        nearby_items = self._find_items(next_cell, radius=3)
        if nearby_items:
            score += len(nearby_items) * 10.0  # Mỗi item/chest gần = +10 điểm
        
        # 4. Hướng về vùng trống (ít tường)
        open_space = self._count_open_spaces(next_cell, radius=2)
        score += open_space * 5.0  # Mỗi ô trống gần = +5 điểm
        
        # 4.5. Ưu tiên hướng có nhiều không gian mở (tránh bị kẹt)
        future_open_space = self._count_open_spaces(next_cell, radius=3)
        score += future_open_space * 3.0  # Mỗi ô trống trong tương lai = +3 điểm
        
        # 5. Tránh di chuyển lặp lại (giảm điểm nếu đã đi qua)
        if next_cell in self.visited_cells:
            score -= 20.0  # Trừ điểm nếu đã đi qua
        
        # 7. Tránh vòng lặp lên xuống (giảm điểm nếu di chuyển theo hướng ngược lại)
        if hasattr(self, '_last_direction') and self._last_direction:
            last_dx, last_dy = DIRECTIONS.get(self._last_direction, (0, 0))
            current_dx, current_dy = next_cell[0] - current_cell[0], next_cell[1] - current_cell[1]
            
            # Nếu di chuyển ngược lại hướng vừa đi
            if (current_dx == -last_dx and current_dy == -last_dy) and (current_dx != 0 or current_dy != 0):
                score -= 30.0  # Trừ điểm mạnh nếu di chuyển ngược lại
                logger.debug(f"🔄 TRÁNH VÒNG LẶP: di chuyển ngược lại hướng {self._last_direction}")
        
        # 6. Ưu tiên di chuyển xa khỏi vị trí hiện tại
        distance_from_current = abs(next_cell[0] - current_cell[0]) + abs(next_cell[1] - current_cell[1])
        if distance_from_current > 0:
            score += 5.0  # Thêm điểm nếu di chuyển thực sự
        
        return score
    
    def _count_open_spaces(self, cell: Tuple[int, int], radius: int = 2) -> int:
        """Đếm số ô trống xung quanh"""
        count = 0
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                check_cell = (cell[0] + dx, cell[1] + dy)
                if self._is_cell_passable(check_cell):
                    count += 1
        return count
    
    def _get_avoid_enemy_move(self, current_cell: Tuple[int, int], current_time: float) -> Optional[Dict[str, Any]]:
        """Tìm nước đi để tránh bot khác (dùng _get_enemy_info)"""
        best_move = None
        best_score = -1
        
        # Tìm hướng di chuyển xa khỏi bot khác nhất
        current_cell_int = (int(current_cell[0]), int(current_cell[1]))
        for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
            dx, dy = DIRECTIONS[direction]
            next_cell = (current_cell_int[0] + dx, current_cell_int[1] + dy)

            if not self._is_cell_passable(next_cell):
                continue
                
            # Tính điểm dựa trên khoảng cách đến bot khác
            _, min_dist, _ = self._get_enemy_info(next_cell)
            score = min_dist * 50.0 if min_dist < 999 else 0
            
            # Tránh nguy hiểm
            if not self._is_in_danger(next_cell, current_time):
                score += 30.0
            
            if score > best_score:
                best_score = score
                best_move = next_cell
        
        if best_move:
            logger.info(f"🤖 TRÁNH BOT KHÁC: từ {current_cell} đến {best_move} (score={best_score})")
            self._update_last_direction(current_cell, best_move)
            return {"type": "move", "goal_cell": best_move}
        
        return None
    
    def _should_escape_after_bomb(self, cell: Tuple[int, int], current_time: float) -> bool:
        """
        Kiểm tra có cần thoát khỏi vùng nguy hiểm sau khi đặt bom không
        CÁCH MỚI: Kiểm tra ngay sau khi đặt bom, không đợi đến khi nguy hiểm
        """
        # QUAN TRỌNG: Kiểm tra NGAY LẬP TỨC sau khi đặt bom (trong vòng 500ms)
        time_since_bomb = current_time - self.last_bomb_time_ms
        if time_since_bomb <= 500:  # 500ms = ngay sau khi đặt bom
            logger.info(f"🏃 CẦN THOÁT NGAY: vừa đặt bom {time_since_bomb:.0f}ms trước")
            return True
        
        # Kiểm tra nếu vừa đặt bom gần đây (trong vòng 4 giây)
        if time_since_bomb > 4000:  # 4 giây
            return False
            
        # Kiểm tra nếu đang ở vùng nguy hiểm
        if self._is_in_danger(cell, current_time):
            logger.info(f"🏃 CẦN THOÁT: đang ở vùng nguy hiểm sau khi đặt bom")
            return True
            
        # Kiểm tra nếu có bom gần đó sắp nổ
        try:
            from .game_state import game_state
            bombs = game_state.get("bombs", [])
            for bomb in bombs:
                bomb_x, bomb_y = bomb.get("x", 0), bomb.get("y", 0)
                bomb_cell = pos_to_cell_bot(bomb_x, bomb_y)
                distance = abs(bomb_cell[0] - cell[0]) + abs(bomb_cell[1] - cell[1])
                
                # Nếu bom gần và sắp nổ (trong vòng 3.5 giây)
                if distance <= 4:
                    life_time = bomb.get("lifeTime", 5000)
                    if life_time <= 3500:  # Còn ít hơn 3.5 giây
                        logger.info(f"🏃 CẦN THOÁT: bom sắp nổ tại {bomb_cell}, còn {life_time}ms")
                        return True
        except Exception:
            pass
            
        return False
    
    def _get_escape_move(self, current_cell: Tuple[int, int], current_time: float) -> Optional[Dict[str, Any]]:
        """Tìm nước đi để thoát khỏi vùng nguy hiểm"""
        try:
            my_uid = game_state.get("my_uid")
            explosion_range = get_bomber_explosion_range(my_uid)
            bombs = game_state.get("bombs", [])
            
            # Tìm bom gần nhất
            if bombs:
                nearest_bomb = min(bombs, key=lambda b: abs(pos_to_cell_bot(b.get("x", 0), b.get("y", 0))[0] - current_cell[0]) + 
                                                         abs(pos_to_cell_bot(b.get("x", 0), b.get("y", 0))[1] - current_cell[1]))
                bomb_cell = pos_to_cell_bot(nearest_bomb.get("x", 0), nearest_bomb.get("y", 0))
                life_time = nearest_bomb.get("lifeTime", 5000)
                
                result = pathfinding.find_escape_path_from_bomb(bomb_cell, current_cell, explosion_range, life_time)
                if result and len(result[0]) >= 2:
                    next_cell = result[0][1]
                    logger.info(f"✅ ESCAPE: {current_cell} → {next_cell}, t={result[1]:.0f}ms < {life_time:.0f}ms")
                    self._update_last_direction(current_cell, next_cell)
                    return {"type": "move", "goal_cell": next_cell}
        except Exception as e:
            logger.error(f"❌ Lỗi escape: {e}")
    
        # Fallback: tìm ô an toàn gần nhất
        best_move = None
        best_score = -1
        for direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
            dx, dy = DIRECTIONS[direction]
            next_cell = (current_cell[0] + dx, current_cell[1] + dy)
            if not self._is_cell_passable(next_cell):
                continue
            score = 100.0 if not self._is_in_danger(next_cell, current_time) else 0.0
            if score > best_score:
                best_score = score
                best_move = next_cell
        
        if best_move:
            logger.info(f"🏃 ESCAPE FALLBACK: {current_cell} → {best_move}")
            self._update_last_direction(current_cell, best_move)
            return {"type": "move", "goal_cell": best_move}
        return None
        
    def _is_in_danger(self, cell: Tuple[int, int], current_time: float) -> bool:
        """Wrapper cho pathfinding.is_in_danger()"""
        return pathfinding.is_in_danger(cell, current_time)
        
    def _is_cell_passable(self, cell: Tuple[int, int]) -> bool:
        """Wrapper cho pathfinding.is_cell_passable()"""
        return pathfinding.is_cell_passable(cell)
        
        
    def _find_safe_goal(self, cell: Tuple[int, int], current_time: float) -> Optional[Tuple[int, int]]:
        """Tìm mục tiêu an toàn thông minh"""
        logger.info(f"🔍 TÌM MỤC TIÊU AN TOÀN: từ {cell}")
        
        # QUAN TRỌNG: Kiểm tra bot có đang trong vùng nguy hiểm không!
        if self._is_in_danger(cell, current_time):
            logger.warning(f"🚨 BOT ĐANG TRONG VÙNG NGUY HIỂM tại {cell} - THOÁT NGAY!")
            # Tìm ô an toàn gần nhất để thoát
            for radius in range(1, 4):  # Chỉ tìm trong 3 bước để thoát nhanh
                candidates = []
                for dx in range(-radius, radius + 1):
                    for dy in range(-radius, radius + 1):
                        if dx == 0 and dy == 0:
                            continue
                        target = (cell[0] + dx, cell[1] + dy)
                        if (0 <= target[0] <= 15 and 0 <= target[1] <= 15 and
                            target != cell):
                            # DEBUG: Chỉ log khi không tìm thấy candidate nào
                            is_passable = self._is_cell_passable(target)
                            is_safe = not self._is_in_danger(target, current_time + 2000)
                        
                            if is_passable and is_safe:
                                distance = abs(dx) + abs(dy)
                                priority = distance
                        
                                # Ưu tiên ô chưa thăm
                                if target not in self.visited_cells:
                                    priority += 5
                                    
                                candidates.append((priority, target))
            
                if candidates:
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    # QUAN TRỌNG: Kiểm tra từng candidate xem có đường đi không! CHO PHÉP đi qua hazard
                    cell_int = (int(cell[0]), int(cell[1]))
                    from .game_state import bfs_shortest_path
                    for priority, target in candidates:
                        test_path = bfs_shortest_path(cell_int, target, avoid_hazard=True, avoid_bots=False)
                        if test_path and len(test_path) >= 1:  # FIX: >= 1 để cho phép ô kề cạnh
                            logger.info(f"🎯 TÌM THẤY ô an toàn trong bán kính {radius}: {target} (có đường đi)")
                            return target
                # Nếu không có candidate nào có đường đi, thử radius lớn hơn
                # logger.warning(f"⚠️ CÁC Ô AN TOÀN trong bán kính {radius} KHÔNG CÓ ĐƯỜNG ĐI")  # Giảm log spam
        
        # QUAN TRỌNG: Kiểm tra có bom sắp nổ không (kiểm tra thực tế)
        try:
            from .game_state import get_fast_state
            fs = get_fast_state()
            if fs and fs.dynamic and fs.dynamic.hazard_until is not None:
                cx, cy = int(cell[0]), int(cell[1])
                if fs.static.in_bounds(cx, cy):
                    current_tick = int(current_time / 100)  # Convert ms to tick
                    explosion_tick = fs.dynamic.hazard_until[cy, cx]
                    if explosion_tick > current_tick:
                        time_until_explosion = (explosion_tick - current_tick) * 100  # Convert tick to ms
                        logger.warning(f"🚨 BOM SẮP NỔ tại {cell} trong {time_until_explosion:.0f}ms - THOÁT NGAY!")
                        
                        # QUAN TRỌNG: XÓA MỌI PLAN và THOÁT NGAY!
                        self.current_plan = None
                        logger.warning(f"🗑️ XÓA MỌI PLAN - THOÁT NGAY!")
                        
                        # Tìm ô an toàn gần nhất để thoát
                        for radius in range(1, 4):  # Chỉ tìm trong 3 bước để thoát nhanh
                            candidates = []
                            for dx in range(-radius, radius + 1):
                                for dy in range(-radius, radius + 1):
                                    if dx == 0 and dy == 0:
                                        continue
                                    target = (cell[0] + dx, cell[1] + dy)
                                    if (0 <= target[0] <= 15 and 0 <= target[1] <= 15 and
                                        target != cell):
                                        is_passable = self._is_cell_passable(target)
                                        is_safe = not self._is_in_danger(target, current_time + 2000)
                                        
                                        if is_passable and is_safe:
                                            distance = abs(dx) + abs(dy)
                                            priority = distance
                                            
                                            if target not in self.visited_cells:
                                                priority += 5
                                                
                                            candidates.append((priority, target))
                            
                            if candidates:
                                candidates.sort(key=lambda x: x[0], reverse=True)
                                cell_int = (int(cell[0]), int(cell[1]))
                                for priority, target in candidates:
                                    test_path = bfs_shortest_path(cell_int, target, avoid_hazard=True, avoid_bots=False)
                                    if test_path and len(test_path) >= 1:
                                        logger.warning(f"🚨 THOÁT NGAY đến {target} (có đường đi)")
                                        return target
        except Exception as e:
            logger.debug(f"Lỗi kiểm tra bom sắp nổ: {e}")
        
        # EMERGENCY: Chọn ô kề cạnh an toàn đầu tiên!
        logger.warning(f"🚨 EMERGENCY: Chọn ô kề cạnh an toàn từ {cell}")
        
        # QUAN TRỌNG: XÓA MỌI PLAN khi vào emergency!
        self.current_plan = None
        logger.warning(f"🗑️ XÓA MỌI PLAN - EMERGENCY!")
        
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                target = (cell[0] + dx, cell[1] + dy)
                if (0 <= target[0] <= 15 and 0 <= target[1] <= 15 and
                    self._is_cell_passable(target) and 
                    not self._is_in_danger(target, current_time + 2000) and
                    not self._is_position_blacklisted(target, current_time)):  # QUAN TRỌNG: Kiểm tra blacklist!
                    
                    # QUAN TRỌNG: Kiểm tra pathfinding trước khi chọn!
                    from .game_state import bfs_shortest_path
                    cell_int = (int(cell[0]), int(cell[1]))
                    test_path = bfs_shortest_path(cell_int, target, avoid_hazard=True, avoid_bots=False)
                    if test_path and len(test_path) >= 1:
                        logger.warning(f"🚨 EMERGENCY: THOÁT NGAY đến {target} (có đường đi)")
                        return target
                    else:
                        logger.debug(f"🚨 EMERGENCY: Bỏ qua {target} - không có đường đi")
                else:
                    # DEBUG: Log tại sao không chọn target này
                    if not self._is_cell_passable(target):
                        logger.debug(f"🚨 EMERGENCY: Bỏ qua {target} - không thể đi được")
                    elif self._is_in_danger(target, current_time + 2000):
                        logger.debug(f"🚨 EMERGENCY: Bỏ qua {target} - nguy hiểm")
                    elif self._is_position_blacklisted(target, current_time):
                        logger.debug(f"🚨 EMERGENCY: Bỏ qua {target} - đã blacklist")
        
        # CUỐI CÙNG: Nếu vẫn không tìm được ô an toàn, chọn ô gần nhất có thể đi được
        logger.warning(f"🚨 CUỐI CÙNG: Chọn ô gần nhất có thể đi được từ {cell}")
        
        # QUAN TRỌNG: XÓA MỌI PLAN khi vào cuối cùng!
        self.current_plan = None
        logger.warning(f"🗑️ XÓA MỌI PLAN - CUỐI CÙNG!")
        
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                target = (cell[0] + dx, cell[1] + dy)
                if (0 <= target[0] <= 15 and 0 <= target[1] <= 15 and
                    self._is_cell_passable(target) and
                    not self._is_position_blacklisted(target, current_time)):
                    
                    # QUAN TRỌNG: Kiểm tra pathfinding trước khi chọn!
                    from .game_state import bfs_shortest_path
                    cell_int = (int(cell[0]), int(cell[1]))
                    test_path = bfs_shortest_path(cell_int, target, avoid_hazard=True, avoid_bots=False)
                    if test_path and len(test_path) >= 1:
                        logger.warning(f"🚨 CUỐI CÙNG: THOÁT NGAY đến {target} (có thể nguy hiểm nhưng có thể đi được)")
                        return target
                    else:
                        logger.debug(f"🚨 CUỐI CÙNG: Bỏ qua {target} - không có đường đi")
                else:
                    # DEBUG: Log tại sao không chọn target này
                    if not self._is_cell_passable(target):
                        logger.debug(f"🚨 CUỐI CÙNG: Bỏ qua {target} - không thể đi được")
                    elif self._is_position_blacklisted(target, current_time):
                        logger.debug(f"🚨 CUỐI CÙNG: Bỏ qua {target} - đã blacklist")
        
        logger.error(f"💀 KHÔNG CÓ Ô AN TOÀN NÀO từ {cell} - Bot sẽ chết!")
        return None
        
        
        
    def _should_place_bomb_for_chest(self, cell: Tuple[int, int], current_time: float, can_place: bool) -> bool:
        """
        Quyết định có nên đặt bom để nổ rương không
        CÁCH MỚI: Sử dụng AdvancedBombingStrategy với timing calculation
        """
        if not can_place:
            return False
        
        # Kiểm tra cooldown
        cooldown = 500 if current_time - self.bomb_exploded_time < 3000 else 2000
        if current_time - self.last_bomb_time_ms < cooldown:
            return False
        
        # Kiểm tra nguy hiểm hiện tại
        if self._is_in_danger(cell, current_time) or self._has_dangerous_bombs_nearby(cell, current_time):
            return False
        
        # SỬ DỤNG PATHFINDING
        try:
            # Kiểm tra có an toàn để đặt bom không
            should_place = pathfinding.should_place_bomb_now(
                cell, cell, can_place
            )
            
            if should_place:
                logger.info(f"✅ AN TOÀN ĐẶT BOM: Đã kiểm tra đường thoát và timing")
                return True
            else:
                logger.warning(f"⚠️ KHÔNG AN TOÀN: Không đủ điều kiện đặt bom tại {cell}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Lỗi advanced bombing: {e}")
            # Fallback về logic cũ
            if (self._has_chest_in_bomb_range(cell) and self._has_escape_after_bomb(cell)):
                logger.info(f"💣 ĐẶT BOM (FALLBACK): có rương và có lối thoát")
                return True
            return False
    
    def _has_chest_in_bomb_range(self, cell: Tuple[int, int]) -> bool:
        """Wrapper cho pathfinding.has_chest_in_bomb_range()"""
        return pathfinding.has_chest_in_bomb_range(cell)
        
    def _has_escape_after_bomb(self, cell: Tuple[int, int]) -> bool:
        """Wrapper cho pathfinding.has_escape_after_bomb()"""
        return pathfinding.has_escape_after_bomb(cell)
    
    def _find_bomb_position_near_chest(self, current_cell: Tuple[int, int], current_time: float) -> Optional[Tuple[int, int]]:
        """Tìm vị trí đặt bom gần rương"""
        try:
            from .game_state import astar_shortest_path
            
            best_position = pathfinding.find_best_bombing_position(
                current_cell, max_search_radius=16,
                blacklist=self.failed_bomb_positions, current_time=current_time
            )
            
            if best_position and not self._is_position_blacklisted(best_position, current_time):
                if best_position != current_cell:
                    path = astar_shortest_path(current_cell, best_position, avoid_hazard=True, avoid_bots=False)
                    if not path or len(path) < 2:
                        return None
                logger.info(f"🎯 Tìm thấy vị trí đặt bom: {best_position}")
                return best_position
        except Exception as e:
            logger.error(f"❌ Lỗi bombing: {e}")
            return None
    
    def _is_position_blacklisted(self, position: Tuple[int, int], current_time: float) -> bool:
        """Kiểm tra vị trí có trong blacklist không"""
        if position in self.failed_bomb_positions:
            failed_time = self.failed_bomb_positions[position]
            if current_time - failed_time < self.blacklist_duration:
                return True
            else:
                # Xóa khỏi blacklist nếu đã hết hạn
                del self.failed_bomb_positions[position]
        return False
    
    def _add_to_blacklist(self, position: Tuple[int, int], current_time: float):
        """Thêm vị trí vào blacklist - QUAN TRỌNG: Blacklist cả BLAST ZONE!"""
        self.failed_bomb_positions[position] = current_time
        
        # QUAN TRỌNG: Blacklist cả BLAST ZONE của bom!
        try:
            from .game_state import get_bomber_explosion_range, game_state
            my_uid = game_state.get("my_uid")
            if my_uid:
                explosion_range = get_bomber_explosion_range(my_uid)
                blast_zones = []
                
                # Tính blast zone theo 4 hướng
                for direction, (dx, dy) in DIRECTIONS.items():
                    for distance in range(1, explosion_range + 1):
                        blast_pos = (position[0] + dx * distance, position[1] + dy * distance)
                        if 0 <= blast_pos[0] <= 15 and 0 <= blast_pos[1] <= 15:
                            blast_zones.append(blast_pos)
                
                # Blacklist tất cả blast zones
                for blast_pos in blast_zones:
                    self.failed_bomb_positions[blast_pos] = current_time
                
                logger.info(f"🚫 BLACKLIST: Thêm {position} + {len(blast_zones)} blast zones vào danh sách cấm ({len(self.failed_bomb_positions)} vị trí)")
            else:
                logger.info(f"🚫 BLACKLIST: Thêm {position} vào danh sách cấm ({len(self.failed_bomb_positions)} vị trí)")
        except Exception as e:
            logger.error(f"❌ Lỗi blacklist blast zone: {e}")
        logger.info(f"🚫 BLACKLIST: Thêm {position} vào danh sách cấm ({len(self.failed_bomb_positions)} vị trí)")

    def _get_bomb_positions_for_chest_with_range(self, chest: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Tìm vị trí đặt bom để nổ rương - SỬ DỤNG TẦM NỔ THỰC TẾ"""
        try:
            from .game_state import game_state, has_wall_at_tile, in_bounds
            
            my_uid = game_state.get("my_uid")
            if not my_uid:
                return []
                
            # Lấy tầm nổ của bom
            explosion_range = get_bomber_explosion_range(my_uid)
            bomb_positions = []
            
            # Tìm vị trí đặt bom trong tầm nổ của rương
            # Duyệt từ rương ra ngoài theo 4 hướng
            for direction, (dx, dy) in DIRECTIONS.items():
                for distance in range(1, explosion_range + 1):
                    # Vị trí đặt bom = rương - hướng * khoảng cách
                    bomb_pos = (chest[0] - dx * distance, chest[1] - dy * distance)
                    
                    # Kiểm tra trong bounds
                    if not in_bounds(bomb_pos[0], bomb_pos[1]):
                        break
                    
                    # Nếu gặp tường, dừng lại (không thể đặt bom qua tường)
                    if has_wall_at_tile(bomb_pos[0], bomb_pos[1]):
                        break
                    
                    # Kiểm tra có thể đặt bom tại vị trí này
                    if self._is_cell_passable(bomb_pos):
                        bomb_positions.append(bomb_pos)
            
            return bomb_positions
            
        except Exception as e:
            logger.error(f"❌ Lỗi tìm vị trí đặt bom: {e}")
            return []
    
    
    def _update_my_bombs(self) -> None:
        """Cập nhật theo dõi bom của mình"""
        try:
            from .game_state import game_state
            my_uid = game_state.get("my_uid")
            if not my_uid:
                return
                
            current_bombs = set()
            bombs = game_state.get("bombs", [])
            
            for bomb in bombs:
                if bomb.get("uid") == my_uid:
                    bomb_cell = pos_to_cell(bomb.get("x", 0), bomb.get("y", 0))
                    current_bombs.add(bomb_cell)
            
            # Kiểm tra bom nào đã nổ (không còn trong danh sách)
            exploded_bombs = self.my_bombs - current_bombs
            if exploded_bombs:
                self.bomb_exploded_time = time.time() * 1000
                logger.info(f"💥 BOM NỔ: {exploded_bombs} - Sẵn sàng đặt bom tiếp")
            
            self.my_bombs = current_bombs
            
        except Exception as e:
            logger.error(f"Lỗi cập nhật bom: {e}")
    
    def _should_continue_bombing(self, current_cell: Tuple[int, int], current_time: float, can_place: bool) -> bool:
        """Kiểm tra có nên tiếp tục đặt bom sau khi bom nổ"""
        if not can_place:
            return False
            
        # Chỉ đặt bom liên tục trong vòng 3 giây sau khi bom nổ
        time_since_explosion = current_time - self.bomb_exploded_time
        if time_since_explosion > 3000:  # 3 giây
            return False
            
        # Không đặt bom nếu đang trong nguy hiểm
        if self._is_in_danger(current_cell, current_time):
            return False
            
        # Kiểm tra có bom nguy hiểm gần đó không
        if self._has_dangerous_bombs_nearby(current_cell, current_time):
            return False
            
        # Kiểm tra có rương kề cạnh không
        adjacent_chest = False
        for dx, dy in DIRECTIONS.values():
            nx, ny = current_cell[0] + dx, current_cell[1] + dy
            if has_chest_at_tile(nx, ny):
                adjacent_chest = True
                break
                
        if not adjacent_chest:
            return False
            
        # Kiểm tra có lối thoát sau khi đặt bom
        if not self._has_escape_after_bomb(current_cell):
            return False
        
        # QUAN TRỌNG: Kiểm tra THỰC TẾ có đường thoát không (double check)
        from .pathfinding import find_escape_path_from_bomb
        from .game_state import get_bomber_explosion_range, game_state
        
        my_uid = game_state.get("my_uid")
        explosion_range = get_bomber_explosion_range(my_uid) if my_uid else 2
        
        escape_result = find_escape_path_from_bomb(current_cell, current_cell, explosion_range, 5000.0)
        if not escape_result:
            logger.warning(f"❌ BỎ QUA BOM LIÊN TỤC tại {current_cell}: KHÔNG CÓ ĐƯỜNG THOÁT THỰC TẾ!")
            return False
            
        logger.info(f"💣 ĐẶT BOM LIÊN TỤC: có rương kề cạnh và an toàn")
        return True
    
    def _find_best_item_to_collect(self, items: List[Tuple[int, int]], current_cell: Tuple[int, int], current_time: float) -> Optional[Tuple[int, int]]:
        """Tìm vật phẩm tốt nhất để nhặt dựa trên ưu tiên và khoảng cách"""
        if not items:
            return None
            
        best_item = None
        best_score = -1
        skipped_no_path = 0
        
        for item_cell in items:
            # Kiểm tra an toàn
            if self._is_in_danger(item_cell, current_time + 2000):
                continue
            
            # QUAN TRỌNG: Kiểm tra có đường đi không! CHO PHÉP đi qua hazard để lấy item
            current_cell_int = (int(current_cell[0]), int(current_cell[1]))
            from .game_state import bfs_shortest_path
            test_path = bfs_shortest_path(current_cell_int, item_cell, avoid_hazard=False, avoid_bots=False)
            if not test_path or len(test_path) <= 1:
                skipped_no_path += 1
                continue  # Không có đường đi → bỏ qua
                
            # Tính khoảng cách
            distance = abs(item_cell[0] - current_cell[0]) + abs(item_cell[1] - current_cell[1])
            
            # Lấy loại vật phẩm
            try:
                from .game_state import get_tile_item
                item_type = get_tile_item(item_cell[0], item_cell[1])
            except Exception:
                continue
                
            # Tính điểm ưu tiên
            priority = self._get_item_priority(item_type)
            score = priority - distance  # Ưu tiên cao, khoảng cách ngắn
            
            if score > best_score:
                best_score = score
                best_item = item_cell
                
        if skipped_no_path > 0:
            logger.warning(f"⚠️ BỎ QUA {skipped_no_path} ITEM vì không có đường đi")
                
        if best_item:
            try:
                from .game_state import get_tile_item
                item_type = get_tile_item(best_item[0], best_item[1])
                logger.info(f"💎 CHỌN VẬT PHẨM: {item_type} tại {best_item} (score={best_score})")
            except Exception:
                pass
        else:
            logger.warning(f"⚠️ KHÔNG TÌM THẤY ITEM CÓ ĐƯỜNG ĐI!")
                
        return best_item
    
    def _get_item_priority(self, item_type: str) -> int:
        """Lấy điểm ưu tiên của vật phẩm"""
        priorities = {
            "S": 100,   # Speed - Giày (tăng tốc độ) - ưu tiên cao nhất
            "R": 90,    # Range - Liệt hỏa (tăng tầm nổ) - ưu tiên cao
            "B": 80,    # Bomb - Đa bom (tăng số bom) - ưu tiên trung bình
        }
        return priorities.get(item_type, 0)
    
    def _create_long_term_plan(self, current_cell: Tuple[int, int], current_time: float) -> Optional[Dict]:
        """Tạo plan dài hạn - SO SÁNH ITEM vs BOMB, chọn cái GẦN HƠN"""
        try:
            current_cell_int = (int(current_cell[0]), int(current_cell[1]))
            
            # 1. TÌM VÀ ĐÁNH GIÁ ITEM
            item_plan = None
            item_distance = 999999
            important_items = self._find_items(current_cell, radius=10, item_types=["S", "R", "B"])
            if important_items:
                logger.info(f"💎 TÌM THẤY {len(important_items)} ITEM trong radius 10: {important_items}")
                best_item = self._find_best_item_to_collect(important_items, current_cell, current_time)
                if best_item and best_item != current_cell:
                    # Tính PATH LENGTH
                    from .game_state import bfs_shortest_path
                    test_path = bfs_shortest_path(current_cell_int, best_item, avoid_hazard=True, avoid_bots=False)
                    if test_path and len(test_path) >= 1:  # FIX: >= 1 thay vì > 1 (cho phép distance=0)
                        item_distance = len(test_path) - 1  # distance=0 khi đã ở đích
                        try:
                            from .game_state import get_tile_item
                            item_type = get_tile_item(best_item[0], best_item[1])
                        except:
                            item_type = "?"
                        logger.info(f"💎 ITEM {item_type} tại {best_item}: PATH LENGTH = {item_distance}")
                        item_plan = {
                        "type": "collect_item",
                        "goal_cell": best_item,
                        "action": "move",
                            "reason": f"Nhặt item {item_type}"
                    }
            
            # 2. TÌM VÀ ĐÁNH GIÁ BOMB POSITION
            bomb_plan = None
            bomb_distance = 999999
            bomb_position = self._find_bomb_position_near_chest(current_cell, current_time)
            
            # CHECK NGUY HIỂM NGAY: Nếu bomb_position đang trong hazard zone → BỎ QUA!
            if bomb_position:
                from .pathfinding import is_in_danger
                if is_in_danger(bomb_position, current_time):
                    logger.warning(f"❌ BỎ QUA BOMB_POSITION {bomb_position}: ĐANG TRONG HAZARD ZONE!")
                    bomb_position = None  # Clear để không xử lý tiếp
            
            if bomb_position:
                # QUAN TRỌNG: Kiểm tra nếu ĐÃ Ở vị trí đặt bom
                if current_cell_int == bomb_position:
                    bomb_distance = 0
                    logger.info(f"💣 BOMB tại {bomb_position}: ĐÃ Ở ĐÂY (distance=0)")
                    # Tính escape path
                    escape_info = self._calculate_escape_plan(bomb_position, current_cell)
                    escape_path = escape_info.get("escape_path", [])
                    # QUAN TRỌNG: Kiểm tra escape_path hợp lệ (phải có ít nhất 2 ô để thoát)
                    if escape_path and len(escape_path) >= 2:
                        bomb_plan = {
                    "type": "bomb_chest", 
                    "goal_cell": bomb_position,
                            "action": "bomb",
                    "reason": "Đặt bom nổ rương",
                    "escape_cell": escape_info.get("escape_cell"),
                            "escape_path": escape_path,
                    "escape_time": escape_info.get("escape_time", 0)
                }
                    else:
                        logger.warning(f"❌ BỎ QUA BOMB tại {bomb_position}: KHÔNG CÓ ĐƯỜNG THOÁT! (escape_path={escape_path})")
                else:
                    # Tính PATH LENGTH
                    from .game_state import bfs_shortest_path
                    test_path = bfs_shortest_path(current_cell_int, bomb_position, avoid_hazard=True, avoid_bots=False)
                    if test_path and len(test_path) >= 1:
                        bomb_distance = len(test_path) - 1
                        logger.info(f"💣 BOMB tại {bomb_position}: PATH LENGTH = {bomb_distance}")
                        # Tính escape path
                        escape_info = self._calculate_escape_plan(bomb_position, current_cell)
                        escape_path = escape_info.get("escape_path", [])
                        # QUAN TRỌNG: Kiểm tra escape_path hợp lệ (phải có ít nhất 2 ô để thoát)
                        if escape_path and len(escape_path) >= 2:
                            bomb_plan = {
                                "type": "bomb_chest", 
                                "goal_cell": bomb_position,
                                "action": "move",
                                "reason": "Đặt bom nổ rương",
                                "escape_cell": escape_info.get("escape_cell"),
                                "escape_path": escape_path,
                                "escape_time": escape_info.get("escape_time", 0)
                            }
                        else:
                            logger.warning(f"❌ BỎ QUA BOMB tại {bomb_position}: KHÔNG CÓ ĐƯỜNG THOÁT! (escape_path={escape_path})")
            
            # 3. SO SÁNH VÀ CHỌN CÁI GẦN HƠN - ƯU TIÊN ITEM NẾU < 5 BƯỚC
            if item_plan and bomb_plan:
                if item_distance < 5:  # Item gần (< 5 bước) → ƯU TIÊN ITEM
                    logger.info(f"🏆 SO SÁNH: 💎 ITEM (distance={item_distance}) < 5 → ƯU TIÊN ITEM!")
                    return item_plan
                elif item_distance <= bomb_distance:  # Item gần hơn hoặc bằng bomb
                    logger.info(f"🏆 SO SÁNH: 💎 ITEM (distance={item_distance}) vs 💣 BOMB (distance={bomb_distance}) → CHỌN ITEM")
                    return item_plan
                else:  # Bomb gần hơn
                    logger.info(f"🏆 SO SÁNH: 💎 ITEM (distance={item_distance}) vs 💣 BOMB (distance={bomb_distance}) → CHỌN BOMB")
                    return bomb_plan
            elif item_plan:
                logger.info(f"✅ CHỈ CÓ ITEM (distance={item_distance})")
                return item_plan
            elif bomb_plan:
                logger.info(f"✅ CHỈ CÓ BOMB (distance={bomb_distance})")
                return bomb_plan
            
            # 4. CHIẾN LƯỢC DÀI HẠN (nếu không có item hoặc bomb)
            logger.info(f"⚠️ KHÔNG CÓ ITEM/BOMB - chuyển sang EXPLORE")
            strategic_goal = self._get_strategic_goal(current_cell)
            if strategic_goal and strategic_goal != current_cell:
                return {
                    "type": "explore",
                    "goal_cell": strategic_goal, 
                    "action": "move",
                    "reason": "Khám phá khu vực mới"
                }
                
            # KHÔNG TÌM ĐƯỢC MỤC TIÊU NÀO
            logger.warning(f"🚧 KHÔNG TÌM ĐƯỢC MỤC TIÊU từ {current_cell} - Bot có thể bị trapped")
            return None
            
        except Exception as e:
            logger.error(f"❌ Lỗi tạo plan dài hạn: {e}")
            return None
    
    def _has_dangerous_bombs_nearby(self, cell: Tuple[int, int], current_time: float) -> bool:
        """Wrapper cho pathfinding.has_dangerous_bombs_nearby()"""
        return pathfinding.has_dangerous_bombs_nearby(cell, current_time, radius=3)

# Instance toàn cục
survival_ai = SimpleSurvivalAI()

def choose_next_action() -> Optional[Dict[str, Any]]:
    """Điểm vào chính cho quyết định AI"""
    return survival_ai.choose_next_action()

def reset_ai_state():
    """Reset AI state toàn cục"""
    try:
        # Reset global AI instance nếu có
        global survival_ai
        if survival_ai:
            survival_ai.reset_state()
        logger.info(f"✅ GLOBAL AI RESET: Hoàn thành")
    except Exception as e:
        logger.error(f"❌ Lỗi reset global AI: {e}")
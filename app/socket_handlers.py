#!/usr/bin/env python3
"""
Xử lý sự kiện Socket.IO
"""

import logging
import time
from typing import Dict, Any

from .game_state import (
    game_state, get_my_bomber, get_my_cell, get_bomber_explosion_range,
    fast_init_from_user, fast_handle_new_bomb, fast_handle_bomb_explode, fast_handle_map_update,
    build_item_tile_map, build_chest_tile_map
)
from .utils.loggers import log_map_state
from .config import BOT_NAME, LOG_SOCKET, LOG_GAME_EVENTS, LOG_ITEM_COLLECTION, LOG_BOMB_EVENTS

logger = logging.getLogger("bot")

# ========== HELPER FUNCTIONS ==========
def _to_tile(x: float, y: float) -> tuple:
    """Convert pixel coordinates to tile coordinates"""
    return (int(x // 40), int(y // 40))

def _update_item_map(items: list) -> None:
    """Update item tile map in game_state"""
    game_state["item_tile_map"] = build_item_tile_map(items)

def _update_chest_map(chests: list) -> None:
    """Update chest tile map in game_state"""
    game_state["chest_tile_map"] = build_chest_tile_map(chests)

def _reset_bomb_tracker() -> None:
    """Reset bomb tracker"""
    try:
        from .models.bomb_tracker import get_bomb_tracker
        get_bomb_tracker().clear()
        logger.info("🎯 BOMB TRACKER RESET")
    except Exception as e:
        logger.error(f"❌ Lỗi reset Bomb Tracker: {e}")

def _reset_ai_state() -> None:
    """Reset AI state"""
    try:
        from .survival_ai import survival_ai
        if survival_ai:
            survival_ai.reset_state()
            logger.info("🔄 AI RESET")
    except Exception as e:
        logger.error(f"❌ Lỗi reset AI: {e}")

# ========== SOCKET HANDLERS ==========
def handle_connect():
    """Xử lý kết nối socket"""
    game_state["connected"] = True
    if LOG_SOCKET:
        logger.info(f"🔌 Đã kết nối. my_uid={game_state['my_uid']}")

def handle_disconnect():
    """Xử lý ngắt kết nối socket - Reset toàn bộ state"""
    game_state["connected"] = False
    if LOG_SOCKET:
        logger.warning("🔌 Đã ngắt kết nối - Reset toàn bộ state")
    
    # Reset toàn bộ khi disconnect để sẵn sàng kết nối lại
    try:
        from .main import reset_global_state
        reset_global_state()
        logger.info("🔄 DISCONNECT RESET: Đã reset toàn bộ state")
    except Exception as e:
        logger.error(f"❌ Lỗi reset khi disconnect: {e}")

def handle_user(data: Dict[str, Any]):
    """Xử lý sự kiện user - ảnh chụp thế giới ban đầu"""
    logger.info("🔄 RESET GAME DATA")
    
    # Reset game_state
    game_state.update({
        "connected": True, "my_uid": None, "game_started": False,
        "map": [], "bombers": [], "bombs": [], "items": [], "chests": [],
        "last_bomb_explosions": [], "active_bombs": [],
        "item_tile_map": {}, "chest_tile_map": {}, "bomb_tile_map": {}, "explosion_history": []
    })
    
    # Cập nhật trạng thái thế giới
    game_state.update({
        "map": data.get("map") or [],
        "bombers": data.get("bombers") or [],
        "bombs": data.get("bombs") or [],
        "items": data.get("items") or [],
        "chests": data.get("chests") or []
    })
    
    # Tìm bot
    uids = [b.get("uid") for b in game_state["bombers"]]
    if game_state["my_uid"] not in uids and uids:
        mine = next((b for b in game_state["bombers"] 
                    if isinstance(b.get("name"), str) and b["name"].lower() == BOT_NAME.lower()), None)
        game_state["my_uid"] = mine.get("uid") if mine else game_state["bombers"][0].get("uid")
        logger.info(f"🤖 BOT: {mine.get('name') if mine else game_state['bombers'][0].get('name')} ({game_state['my_uid']})")
    
    # Game started
    if data.get("isStart", False):
        game_state["game_started"] = True
    
    # Update tile maps
    _update_item_map(game_state.get("items", []))
    _update_chest_map(game_state.get("chests", []))
    game_state["bomb_tile_map"] = {}
    game_state["active_bombs"] = []
    
    # Log
    logger.info(f"🌍 map={len(game_state['map'])}x{len(game_state['map'][0]) if game_state['map'] else 0} | "
               f"bombers={len(game_state['bombers'])} | bombs={len(game_state['bombs'])} | "
               f"items={len(game_state['items'])} | chests={len(game_state['chests'])}")
    
    log_map_state(game_state, log_enabled=True)
    
    # Init fast_state
    try:
        fast_init_from_user(data or {})
    except Exception as e:
        logger.exception(f"FastState init error: {e}")

def handle_start(data: Dict[str, Any]):
    """Xử lý sự kiện bắt đầu game"""
    game_state["game_started"] = True
    if LOG_GAME_EVENTS:
        logger.info(f"📥 START RESPONSE: {data}")
    logger.info(f"🟢 Bot của tôi: {get_my_bomber()}")
    logger.info(f"🟢 Ô của tôi: {get_my_cell()}")

def handle_finish(data: Dict[str, Any]):
    """Xử lý sự kiện kết thúc game"""
    logger.info("🔴 Game KẾT THÚC")
    
    _reset_bomb_tracker()
    
    game_state.update({
        "game_started": False, "map": [], "bombers": [], "bombs": [], "items": [], "chests": [],
        "last_bomb_explosions": [], "active_bombs": [], "explosion_history": [],
        "chest_tile_map": {}, "item_tile_map": {}, "bomb_tile_map": {}, "wall_tile_map": {}
    })
    
    try:
        from .game_state import reset_fast_state
        reset_fast_state()
    except Exception as e:
        logger.error(f"❌ reset FastGameState: {e}")
    
    _reset_ai_state()
    
    try:
        from .main import reset_global_state
        reset_global_state()
    except Exception as e:
        logger.error(f"❌ reset global: {e}")
    
    logger.info("✅ RESET HOÀN THÀNH")

def handle_player_move(data: Dict[str, Any]):
    """Xử lý cập nhật di chuyển player"""
    uid = data.get("uid")
    # Bỏ logging chi tiết và so sánh cũ để giảm noise
    
    # Cập nhật bomber trong state
    updated = False
    for i, bomber in enumerate(game_state["bombers"]):
        if bomber.get("uid") == uid:
            game_state["bombers"][i] = data
            updated = True
            break
    
    if not updated:
        game_state["bombers"].append(data)
    
    # Theo dõi việc đi qua bom cho bot của chúng ta
    if uid == game_state.get("my_uid"):
        for bomb in game_state["bombs"]:
            if bomb.get("uid") == uid and not bomb.get("bomberPassedThrough", False):
                bomb_cell = (int(bomb.get("x", 0) // 40), int(bomb.get("y", 0) // 40))
                current_cell = (int(data.get("x", 0) // 40), int(data.get("y", 0) // 40))
                if bomb_cell != current_cell:
                    bomb["bomberPassedThrough"] = True

def handle_new_bomb(data: Dict[str, Any]):
    """Xử lý đặt bom mới"""
    bomb_id = data.get("id")
    if LOG_BOMB_EVENTS:
        logger.info(f"💣 BOM MỚI: {bomb_id} tại ({data.get('x')},{data.get('y')})")
    
    # Update bombs list
    for i, bomb in enumerate(game_state["bombs"]):
        if bomb.get("id") == bomb_id:
            game_state["bombs"][i] = data
            break
    else:
        game_state["bombs"].append(data)
    game_state["active_bombs"].append(data)
    
    # Update bomb tile map
    tile_x, tile_y = _to_tile(data.get("x", 0), data.get("y", 0))
    game_state.setdefault("bomb_tile_map", {})[(tile_x, tile_y)] = True
    
    # Add to bomb tracker
    try:
        from .models.bomb_tracker import get_bomb_tracker
        from .game_state import get_bomber_explosion_range
        
        bomb_uid = data.get("uid", "")
        explosion_range = get_bomber_explosion_range(bomb_uid) if bomb_uid else 2
        
        get_bomb_tracker().add_bomb(
            bomb_id=bomb_id, position=(tile_x, tile_y), explosion_range=explosion_range,
            created_at=data.get("createdAt", time.time() * 1000),
            lifetime=data.get("lifeTime", 5000.0), owner_uid=bomb_uid
        )
    except Exception as e:
        logger.exception(f"Bomb tracker error: {e}")
    
    log_map_state(game_state, log_enabled=True)
    
    try:
        fast_handle_new_bomb(data or {})
    except Exception as e:
        logger.exception(f"FastState error: {e}")
    
    # Check path intersects bomb blast
    try:
        from .main import movement_plan
        import app.pathfinding as pathfinding
        from .survival_ai import survival_ai
        
        # QUAN TRỌNG: Không reset plan nếu đây là BOM CỦA MÌNH và đang escape!
        is_my_bomb = (data.get("uid") == game_state.get("my_uid"))
        is_escaping = (survival_ai and survival_ai.must_escape_bomb)
        
        if is_my_bomb and is_escaping:
            logger.info(f"✅ BOM CỦA MÌNH - GIỮ ESCAPE PLAN!")
        elif movement_plan.get("path_valid") and movement_plan.get("path"):
            explosion_range = get_bomber_explosion_range(data.get("uid")) if data.get("uid") else 2
            blast_zone = pathfinding.calculate_blast_zone((tile_x + 1, tile_y + 1), explosion_range)
            
            if any(cell in blast_zone for cell in movement_plan.get("path", [])):
                logger.warning(f"⚠️ PATH VƯỚNG BOM! Reset plan")
                movement_plan.update({"path_valid": False, "path": [], "orient": None})
                if survival_ai:
                    survival_ai.current_plan = None
    except Exception as e:
        logger.exception(f"Check path error: {e}")

def handle_bomb_explode(data: Dict[str, Any]):
    """Xử lý bom nổ"""
    bomb_id = data.get("id")
    explosion_area = data.get("explosionArea") or []
    
    logger.info(f"💥 BOM NỔ: id={bomb_id} uid={data.get('uid')} areaPoints={len(explosion_area)}")
    
    # === XÓA KHỎI BOMB TRACKER ===
    try:
        from .models.bomb_tracker import get_bomb_tracker
        bomb_tracker = get_bomb_tracker()
        bomb_tracker.remove_bomb(bomb_id)
        logger.info(f"🎯 BOMB TRACKER: Đã xóa bom {bomb_id}")
    except Exception as e:
        logger.exception(f"Bomb tracker remove error: {e}")
    
    # Phân tích phạm vi nổ thực tế
    if explosion_area:
        explosion_tiles = []
        for point in explosion_area:
            x, y = point.get("x", 0), point.get("y", 0)
            tile_x = int(x // 40)
            tile_y = int(y // 40)
            explosion_tiles.append((tile_x, tile_y))
        
        bomb_x = int(data.get("x", 0) // 40)
        bomb_y = int(data.get("y", 0) // 40)
        flame_ranges = {
            "UP": 0, "DOWN": 0, "LEFT": 0, "RIGHT": 0
        }
        
        for tile_x, tile_y in explosion_tiles:
            if tile_x == bomb_x:  # Cùng cột
                if tile_y < bomb_y:  # Lên trên
                    flame_ranges["UP"] = max(flame_ranges["UP"], bomb_y - tile_y)
                elif tile_y > bomb_y:  # Xuống dưới
                    flame_ranges["DOWN"] = max(flame_ranges["DOWN"], tile_y - bomb_y)
            elif tile_y == bomb_y:  # Cùng hàng
                if tile_x < bomb_x:  # Sang trái
                    flame_ranges["LEFT"] = max(flame_ranges["LEFT"], bomb_x - tile_x)
                elif tile_x > bomb_x:  # Sang phải
                    flame_ranges["RIGHT"] = max(flame_ranges["RIGHT"], tile_x - bomb_x)
        
        logger.info(f"🔥 PHẠM VI NỔ THỰC TẾ: UP={flame_ranges['UP']}, DOWN={flame_ranges['DOWN']}, "
                   f"LEFT={flame_ranges['LEFT']}, RIGHT={flame_ranges['RIGHT']}")
        
        # Lưu dữ liệu học cho AI
        explosion_data = {
            "bomb_id": bomb_id,
            "bomb_tile": (bomb_x, bomb_y),
            "explosion_tiles": explosion_tiles,
            "flame_ranges": flame_ranges,
            "timestamp": time.time()
        }
        
        # Thêm vào lịch sử học
        if "explosion_history" not in game_state:
            game_state["explosion_history"] = []
        game_state["explosion_history"].append(explosion_data)
        
        # Giữ tối đa 50 vụ nổ gần nhất
        if len(game_state["explosion_history"]) > 50:
            game_state["explosion_history"] = game_state["explosion_history"][-50:]
    
    # Tìm và xóa bom đã nổ
    exploded_bomb = None
    for bomb in game_state["bombs"]:
        if bomb.get("id") == bomb_id:
            exploded_bomb = bomb
            break
    
    game_state["bombs"] = [b for b in game_state["bombs"] if b.get("id") != bomb_id]
    
    # Xóa bom khỏi danh sách bom hoạt động
    game_state["active_bombs"] = [b for b in game_state["active_bombs"] if b.get("id") != bomb_id]
    
    # Cập nhật bomb_tile_map - xóa bom đã nổ
    if exploded_bomb:
        bomb_x, bomb_y = exploded_bomb.get("x", 0), exploded_bomb.get("y", 0)
        tile_x = int(bomb_x // 40)
        tile_y = int(bomb_y // 40)
        bomb_tile_map = game_state.get("bomb_tile_map", {})
        if (tile_x, tile_y) in bomb_tile_map:
            del bomb_tile_map[(tile_x, tile_y)]
            game_state["bomb_tile_map"] = bomb_tile_map
            logger.info(f"🗺️ XÓA BOM tile=({tile_x}, {tile_y})")
    
    # Vẽ lại map sau khi bom nổ
    log_map_state(game_state, log_enabled=True)

    # Cập nhật FastState hazards
    try:
        fast_handle_bomb_explode(data or {})
    except Exception as e:
        logger.exception(f"FastState bomb_explode error: {e}")
    
    # Khôi phục số bom cho bomber
    if exploded_bomb:
        bomb_uid = exploded_bomb.get("uid")
        for bomber in game_state["bombers"]:
            if bomber.get("uid") == bomb_uid:
                bomber["bombCount"] = bomber.get("bombCount", 0) + 1
                logger.info(f"💥 BOM NỔ: Khôi phục số bom cho {bomb_uid}")
                break
    
    # Ghi lại vùng nổ
    if explosion_area:
        game_state["last_bomb_explosions"].append(explosion_area)
        if len(game_state["last_bomb_explosions"]) > 32:
            game_state["last_bomb_explosions"] = game_state["last_bomb_explosions"][-32:]

def handle_map_update(data: Dict[str, Any]):
    """Xử lý cập nhật map (rương, items)"""
    if LOG_GAME_EVENTS:
        logger.info(f"📥 MAP_UPDATE: chests={len(data.get('chests', []))} items={len(data.get('items', []))}")
    
    # Cập nhật chests
    if "chests" in data:
        old_chests = game_state.get("chests", [])
        new_chests = data["chests"] or []
        game_state["chests"] = new_chests
        
        # Phân tích thay đổi chests
        old_chest_positions = {(c.get("x", 0), c.get("y", 0)) for c in old_chests}
        new_chest_positions = {(c.get("x", 0), c.get("y", 0)) for c in new_chests}
        
        destroyed_chests = old_chest_positions - new_chest_positions
        if destroyed_chests:
            logger.info(f"📦 RƯƠNG BỊ PHÁ: {len(destroyed_chests)} rương - {list(destroyed_chests)}")
    
    # Cập nhật items với phân tích chi tiết
    if "items" in data:
        old_items = game_state.get("items", [])
        new_items = data["items"] or []
        game_state["items"] = new_items
        
        # Phân tích thay đổi items
        old_item_positions = {(i.get("x", 0), i.get("y", 0), i.get("type", "")) for i in old_items}
        new_item_positions = {(i.get("x", 0), i.get("y", 0), i.get("type", "")) for i in new_items}
        
        new_items_added = new_item_positions - old_item_positions
        items_collected = old_item_positions - new_item_positions
        
        if new_items_added:
            logger.info(f"💎 ITEM MỚI: {len(new_items_added)}")
        if items_collected:
            logger.info(f"🎯 ITEM BỊ NHẶT: {len(items_collected)}")
        
        # Tạo bản đồ tile cho items (tối ưu)
        item_tile_map = build_item_tile_map(new_items)
        game_state["item_tile_map"] = item_tile_map
        logger.info(f"🗺️ ITEMS tiles={len(item_tile_map)}")
    
    # Tạo bản đồ tile cho chests (tối ưu)
    chests = game_state.get("chests", [])
    chest_tile_map = build_chest_tile_map(chests)
    game_state["chest_tile_map"] = chest_tile_map
    logger.info(f"🗺️ CHESTS tiles={len(chest_tile_map)}")
    
    # Vẽ lại map sau khi cập nhật (bắt buộc hiển thị)
    logger.info(f"🗺️ MAP UPDATE: Hiển thị map mới sau khi cập nhật")
    # Tạm thời bỏ force=True để tránh lỗi
    try:
        log_map_state(game_state, log_enabled=True)
    except Exception as e:
        logger.exception(f"❌ LỖI LOG MAP: {e}")

    # Đồng bộ FastState (items/chests)
    try:
        fast_handle_map_update(data or {})
    except Exception as e:
        logger.exception(f"FastState map_update error: {e}")
    
    # MAP_UPDATE: KHÔNG reset plan nếu đang có plan hợp lệ
    # Các event cụ thể (chest_destroyed, bomb_explode) sẽ xử lý reset nếu cần
    try:
        from .survival_ai import survival_ai
        if survival_ai and not survival_ai.current_plan:
            # Chỉ trigger AI tính plan NẾU CHƯA CÓ PLAN
            logger.debug(f"🔄 MAP UPDATE: Chưa có plan, trigger AI tính toán")
            try:
                new_action = survival_ai.choose_next_action()
                if new_action:
                    logger.info(f"🎯 AI PLAN MỚI: {new_action}")
                else:
                    logger.info(f"🤔 AI KHÔNG CÓ HÀNH ĐỘNG")
            except Exception as e:
                logger.exception(f"AI choose_next_action error: {e}")
        elif survival_ai and survival_ai.current_plan:
            # Đã có plan, KHÔNG làm gì (giữ plan hiện tại)
            logger.debug(f"🗺️ MAP UPDATE: Giữ plan hiện tại {survival_ai.current_plan.get('type')}")
    except Exception as e:
        logger.exception(f"AI plan error: {e}")

def handle_item_collected(data: Dict[str, Any]):
    """Xử lý nhặt item"""
    if LOG_ITEM_COLLECTION:
        logger.info(f"📥 ITEM_COLLECTED RESPONSE: {data}")
    
    bomber = data.get("bomber")
    item = data.get("item", {})
    logger.info(f"📥 ITEM_COLLECTED: bomber={bomber.get('name') if bomber else 'None'} - "
               f"item={item.get('type')} tại ({item.get('x')}, {item.get('y')})")
    
    # Cập nhật item_tile_map - xóa item đã được nhặt
    if item:
        item_x, item_y = item.get("x", 0), item.get("y", 0)
        tile_x = int(item_x // 40)
        tile_y = int(item_y // 40)
        
        # Xóa item khỏi bản đồ
        item_tile_map = game_state.get("item_tile_map", {})
        if (tile_x, tile_y) in item_tile_map:
            del item_tile_map[(tile_x, tile_y)]
            game_state["item_tile_map"] = item_tile_map
            logger.info(f"🗺️ XÓA ITEM: {item.get('type')} tại tile ({tile_x}, {tile_y})")
    
    if bomber and bomber.get("uid") == game_state.get("my_uid"):
        # Cập nhật bomber của chúng ta
        for i, b in enumerate(game_state["bombers"]):
            if b.get("uid") == bomber.get("uid"):
                game_state["bombers"][i] = bomber
                break
        logger.info(f"💎 NHẶT ITEM: {item.get('type')} - Tốc độ hiện tại: {bomber.get('speed')} (max 3) - Số item speed: {bomber.get('speedCount')} (mỗi item = 10 điểm)")
    
    # Vẽ lại map sau khi nhặt item
    log_map_state(game_state, log_enabled=True)

def handle_chest_destroyed(data: Dict[str, Any]):
    """Xử lý rương bị phá"""
    logger.info(f"📥 CHEST_DESTROYED RESPONSE: {data}")
    logger.info(f"📦 RƯƠNG BỊ PHÁ: ({data.get('x')}, {data.get('y')}) - item={data.get('item')}")
    
    # Cập nhật item_tile_map - thêm item mới được tạo ra
    item = data.get("item")
    if item:
        item_x, item_y = item.get("x", 0), item.get("y", 0)
        tile_x = int(item_x // 40)
        tile_y = int(item_y // 40)
        item_type = item.get("type", "")
        
        # Thêm item vào bản đồ
        item_tile_map = game_state.get("item_tile_map", {})
        item_tile_map[(tile_x, tile_y)] = item_type
        game_state["item_tile_map"] = item_tile_map
        logger.info(f"🗺️ THÊM ITEM: {item_type} tại tile ({tile_x}, {tile_y})")
    
    # Cập nhật chest_tile_map - xóa rương đã bị phá
    chest_x, chest_y = data.get("x", 0), data.get("y", 0)
    tile_x = int(chest_x // 40)
    tile_y = int(chest_y // 40)
    chest_tile_map = game_state.get("chest_tile_map", {})
    if (tile_x, tile_y) in chest_tile_map:
        del chest_tile_map[(tile_x, tile_y)]
        game_state["chest_tile_map"] = chest_tile_map
        logger.info(f"🗺️ XÓA RƯƠNG: tại tile ({tile_x}, {tile_y})")
    
    # Vẽ lại map sau khi rương bị phá
    # Tạm thời bỏ force=True để tránh lỗi
    log_map_state(game_state, log_enabled=True)
    
    # Tính lại kế hoạch AI sau khi rương bị phá - CHỈ NÊN RESET NÊU RƯƠNG LÀ TARGET
    try:
        from .survival_ai import survival_ai
        if survival_ai and survival_ai.current_plan:
            # Chỉ reset nếu rương bị phá là TARGET hiện tại của bot
            plan_goal = survival_ai.current_plan.get("goal_cell")
            destroyed_cell = (tile_x + 1, tile_y + 1)  # Đã +1 ở trên
            
            if plan_goal == destroyed_cell:
                # Target bị phá → reset plan
                survival_ai.current_plan = None
                logger.info(f"🔄 RESET AI PLAN: Target {destroyed_cell} bị phá")
                
                # Trigger AI tính lại plan
                try:
                    new_action = survival_ai.choose_next_action()
                    if new_action:
                        logger.info(f"🎯 AI PLAN MỚI: {new_action}")
                    else:
                        logger.info(f"🤔 AI KHÔNG CÓ HÀNH ĐỘNG")
                except Exception as e:
                    logger.exception(f"AI choose_next_action error: {e}")
            else:
                # Rương khác bị phá, KHÔNG reset plan đang thực hiện
                logger.debug(f"🗺️ Rương {destroyed_cell} bị phá (không phải target {plan_goal})")
    except Exception as e:
        logger.exception(f"Reset AI plan error: {e}")

def handle_new_enemy(data: Dict[str, Any]):
    """Xử lý bot mới tham gia"""
    logger.info(f"📥 NEW_ENEMY RESPONSE: {data}")
    
    bomber = data.get("bomber")
    if bomber:
        # Thêm bomber mới vào danh sách
        game_state["bombers"].append(bomber)
        logger.info(f"👤 BOT MỚI: {bomber.get('name')} ({bomber.get('uid')}) - "
                   f"pos=({bomber.get('x')}, {bomber.get('y')}) - "
                   f"speed={bomber.get('speed')} - alive={bomber.get('isAlive')}")
        try:
            bx, by = bomber.get("x", 0), bomber.get("y", 0)
            logger.info(f"SPAWN: {bomber.get('name')} ({bomber.get('uid')}) pixel=({bx},{by})")
        except Exception:
            pass

        # Nếu bot của tôi chưa được gán đúng theo BOT_NAME, gán lại ngay khi thấy bot spawn
        try:
            from .config import BOT_NAME
            current_my = get_my_bomber()
            want_this = isinstance(bomber.get("name"), str) and bomber["name"].lower() == BOT_NAME.lower()
            wrong_uid = (current_my is None) or (isinstance(current_my.get("name"), str) and current_my["name"].lower() != BOT_NAME.lower())
            if want_this and wrong_uid:
                game_state["my_uid"] = bomber.get("uid")
                logger.info(f"🤖 GÁN LẠI BOT CỦA TÔI: {bomber.get('name')} ({bomber.get('uid')}) theo BOT_NAME={BOT_NAME}")
        except Exception:
            pass

def handle_user_die_update(data: Dict[str, Any]):
    """Xử lý bot bị hạ gục"""
    killer = data.get("killer")
    killed = data.get("killed")
    bomb = data.get("bomb")
    bombers = data.get("bombers", [])
    
    logger.info(f"📥 USER_DIE_UPDATE: killer={killer.get('name') if killer else 'None'} - "
               f"killed={killed.get('name') if killed else 'None'} - "
               f"bombers={len(bombers)}")
    
    # Cập nhật danh sách bombers
    game_state["bombers"] = bombers
    
    if killed:
        logger.info(f"💀 BOT BỊ HẠ: {killed.get('name')} bởi {killer.get('name') if killer else 'bom'}")

def handle_user_disconnect(data: Dict[str, Any]):
    """Xử lý bot thoát khỏi phòng"""
    uid = data.get("uid")
    bomber = data.get("bomber")
    
    logger.info(f"📥 USER_DISCONNECT: uid={uid} - bomber={bomber.get('name') if bomber else 'None'}")
    
    # Xóa bomber khỏi danh sách
    game_state["bombers"] = [b for b in game_state["bombers"] if b.get("uid") != uid]
    
    if bomber:
        logger.info(f"👋 BOT THOÁT: {bomber.get('name')} ({uid})")
    else:
        logger.info(f"👋 BOT THOÁT: {uid}")

def handle_new_life(data: Dict[str, Any]):
    """Xử lý bot hồi sinh (chỉ có ở môi trường luyện tập)"""
    logger.info(f"📥 NEW_LIFE RESPONSE: {data.get('killed', {}).get('name')}")
    
    # Kiểm tra xem có phải bot của mình không
    killed_data = data.get("killed", {})
    killed_uid = killed_data.get("uid")
    my_uid = game_state.get("my_uid")
    
    is_my_bot = (killed_uid == my_uid)
    
    if is_my_bot:
        # CHỈ reset khi là bot của mình
        logger.info(f"🔄 NEW_LIFE: Bot của mình ({killed_uid}) hồi sinh - Reset state")
        
        # === RESET BOMB TRACKER ===
        try:
            from .models.bomb_tracker import get_bomb_tracker
            bomb_tracker = get_bomb_tracker()
            bomb_tracker.clear()
            logger.info("🎯 BOMB TRACKER RESET: Đã xóa toàn bộ bombs")
        except Exception as e:
            logger.error(f"❌ Lỗi reset Bomb Tracker: {e}")
        
        # Reset toàn bộ game state nhưng giữ lại connection state
        connected = game_state.get("connected", False)
        game_started = game_state.get("game_started", False)
        
        # KHÔNG reset map ngay lập tức - chờ server gửi lại
        game_state.update({
            "bombers": [],
            "bombs": [],
            "items": [],
            "chests": [],
            "chest_tile_map": {},
            "item_tile_map": {},
            "bomb_tile_map": {},
            "wall_tile_map": {},
            "active_bombs": [],
            "last_bomb_explosions": [],
            "explosion_history": [],
            "connected": connected,
            "game_started": game_started,
            "my_uid": my_uid
        })
        
        # Reset AI state và movement plan
        try:
            from .survival_ai import survival_ai
            if survival_ai:
                survival_ai.reset_state()
                logger.info(f"🔄 RESET AI STATE: Đã reset toàn bộ AI state")
            
            # Reset movement plan trong movement_planner.py
            from .movement import get_movement_planner
            movement_planner = get_movement_planner()
            movement_planner.reset()
            logger.info(f"🔄 RESET MOVEMENT PLAN: Đã reset movement plan sau khi hồi sinh")
        except Exception as e:
            logger.exception(f"Reset AI state error: {e}")
    else:
        logger.info(f"🔄 NEW_LIFE: Bot khác ({killed_uid}) hồi sinh - KHÔNG reset state")
    
    bomber = data.get("bomber")
    if bomber:
        logger.info(f"📥 NEW_LIFE: bomber={bomber.get('name')} ({bomber.get('uid')}) - "
                   f"pos=({bomber.get('x')}, {bomber.get('y')}) - "
                   f"alive={bomber.get('isAlive')}")
        
        # Thêm bomber vào danh sách mới
        game_state["bombers"].append(bomber)
        logger.info(f"🔄 BOT HỒI SINH: {bomber.get('name')} ({bomber.get('uid')})")
        
        if bomber.get("uid") == game_state.get("my_uid"):
            logger.info(f"✅ BOT CỦA MÌNH đã hồi sinh và được thêm vào game_state")
        
        try:
            bx, by = bomber.get("x", 0), bomber.get("y", 0)
            logger.info(f"SPAWN: {bomber.get('name')} ({bomber.get('uid')}) pixel=({bx},{by})")
        except Exception:
            pass
    
    # NEW_LIFE xử lý xong
    if is_my_bot:
        logger.info(f"🔄 NEW_LIFE: Đã reset toàn bộ state, chờ server gửi map mới")
    else:
        logger.info(f"✅ NEW_LIFE: Đã update bomber data, game tiếp tục")
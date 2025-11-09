#!/usr/bin/env python3
"""
Bot Bomberman - Zinza Hackathon 2025
Bot AI đơn giản với chiến lược sinh tồn
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

# Import các module cần thiết
from aiolimiter import AsyncLimiter
from fastapi import FastAPI
import socketio

# Import config và modules
from .config import (
    SOCKET_SERVER, TOKEN, TICK_HZ, MAX_CMDS_PER_SEC, CELL_SIZE, LOG_LEVEL, BOT_NAME,
    REVERSE_LOCK_SECONDS, DIRECTIONS, LOG_MOVEMENT, LOG_MAP
)
from .game_state import game_state, get_my_bomber, pos_to_cell
from .survival_ai import choose_next_action
from .socket_handlers import (
    handle_connect, handle_disconnect, handle_user, handle_start, 
    handle_finish, handle_player_move, handle_new_bomb, 
    handle_bomb_explode, handle_map_update, handle_item_collected,
    handle_chest_destroyed, handle_new_enemy, handle_user_die_update,
    handle_user_disconnect, handle_new_life
)

# Import utils
from .utils.loggers import MovementLogger, log_map_state
from .movement import get_movement_planner
from .bot_controller import get_bot_controller

# Giới hạn tốc độ gửi lệnh
cmd_limiter = AsyncLimiter(max_rate=MAX_CMDS_PER_SEC, time_period=1)
logger = logging.getLogger("bot")

# Khởi tạo các utilities
movement_logger = MovementLogger()
movement_planner = get_movement_planner()

# Compatibility: movement_plan trỏ đến planner.plan
movement_plan = movement_planner.plan

# Khởi tạo Socket.IO client
sio = socketio.AsyncClient(
    reconnection=True, 
    reconnection_attempts=0, 
    logger=False, 
    engineio_logger=False
)

# Đã chuyển sang BotController

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý vòng đời FastAPI"""
    # Cấu hình mức log theo LOG_LEVEL
    try:
        level = getattr(logging, LOG_LEVEL, logging.INFO)
        logging.basicConfig(level=level)
        logger.setLevel(level)
    except Exception:
        pass
    try:
        await startup()
    except Exception as e:
        pass
    yield

app = FastAPI(lifespan=lifespan)

# ---------- API Endpoints ----------
@app.get("/healthz")
async def health_check():
    """Kiểm tra trạng thái bot"""
    return {
        "status": "ok", 
        "connected": game_state["connected"], 
        "started": game_state["game_started"]
    }

@app.get("/state")
async def get_state():
    """Lấy trạng thái game hiện tại"""
    me = get_my_bomber()
    return {
        "connected": game_state["connected"],
        "started": game_state["game_started"],
        "my_uid": game_state["my_uid"],
        "me": me,
        "bombs": len(game_state.get("bombs", [])),
        "items": len(game_state.get("items", [])),
        "chests": len(game_state.get("chests", [])),
    }

# ---------- Socket Event Handlers ----------
@sio.event
async def connect():
    """Xử lý kết nối socket"""
    handle_connect()
    
    # Gửi yêu cầu tham gia ngay sau khi kết nối
    try:
        await sio.emit("join", {})
    except Exception as e:
        logger.error(f"Lỗi gửi join: {e}")

@sio.event
async def connect_error(data):
    """Xử lý lỗi kết nối"""
    logger.error(f"Lỗi kết nối: {data}")

@sio.event
async def disconnect():
    """Xử lý ngắt kết nối"""
    handle_disconnect()

@sio.on("user")
async def on_user(data=None):
    """Xử lý sự kiện user"""
    handle_user(data or {})

@sio.on("start")
async def on_start(data=None):
    """Xử lý sự kiện bắt đầu game"""
    logger.info(f"🎮 GAME BẮT ĐẦU")
    handle_start(data or {})

@sio.on("finish")
async def on_finish(data=None):
    """Xử lý sự kiện kết thúc game"""
    logger.info(f"🏁 GAME KẾT THÚC")
    handle_finish(data or {})

@sio.on("player_move")
async def on_player_move(data=None):
    """Xử lý sự kiện di chuyển player"""
    handle_player_move(data or {})

@sio.on("new_bomb")
async def on_new_bomb(data=None):
    """Xử lý sự kiện bom mới"""
    handle_new_bomb(data or {})

@sio.on("bomb_explode")
async def on_bomb_explode(data=None):
    """Xử lý sự kiện bom nổ"""
    handle_bomb_explode(data or {})

@sio.on("map_update")
async def on_map_update(data=None):
    """Xử lý sự kiện cập nhật map"""
    handle_map_update(data or {})

@sio.on("item_collected")
async def on_item_collected(data=None):
    """Xử lý sự kiện nhặt item"""
    handle_item_collected(data or {})

@sio.on("chest_destroyed")
async def on_chest_destroyed(data=None):
    """Xử lý sự kiện rương bị phá"""
    handle_chest_destroyed(data or {})

@sio.on("new_enemy")
async def on_new_enemy(data=None):
    """Xử lý sự kiện bot mới tham gia"""
    handle_new_enemy(data or {})

@sio.on("user_die_update")
async def on_user_die_update(data=None):
    """Xử lý sự kiện bot bị hạ gục"""
    handle_user_die_update(data or {})

@sio.on("user_disconnect")
async def on_user_disconnect(data=None):
    """Xử lý sự kiện bot thoát khỏi phòng"""
    handle_user_disconnect(data or {})

@sio.on("new_life")
async def on_new_life(data=None):
    """Xử lý sự kiện bot hồi sinh"""
    handle_new_life(data or {})

# ---------- Bot Actions ----------
async def send_move(orient: str):
    """Gửi lệnh di chuyển với giới hạn tốc độ"""
    if orient not in DIRECTIONS:
        return
    
    if not game_state.get("game_started", False):
        if os.getenv("ENVIRONMENT", "prod") != "dev":
            return
    
    try:
        async with cmd_limiter:
            await sio.emit("move", {"orient": orient})
        movement_logger.log_movement(orient, LOG_MOVEMENT)
    except Exception as e:
        logger.error(f"❌ Lỗi di chuyển: {e}")

async def send_bomb():
    """Gửi lệnh đặt bom"""
    # Kiểm tra game đã bắt đầu chưa
    if not game_state.get("game_started", False):
        # Trong môi trường dev, cho phép đặt bom mà không cần start event
        if os.getenv("ENVIRONMENT", "prod") == "dev":
            pass
        else:
            return
    
    try:
        async with cmd_limiter:
            await sio.emit("place_bomb", {})
        
        # Cập nhật số bom local
        my_uid = game_state.get("my_uid")
        if my_uid:
            for bomber in game_state["bombers"]:
                if bomber.get("uid") == my_uid:
                    bomber["bombCount"] = max(0, bomber.get("bombCount", 1) - 1)
                    break
    except Exception as e:
        logger.error(f"Lỗi đặt bom: {e}")

# ---------- Bot Logic ----------
def reset_global_state() -> None:
    """Reset toàn bộ global state khi game kết thúc"""
    controller = get_bot_controller()
    controller.reset()
    movement_planner.reset()
    movement_logger.reset()

async def _send_move(orient: str):
    """Helper để gửi move với rate limiting"""
    controller = get_bot_controller()
    if controller.can_emit_move_now(MAX_CMDS_PER_SEC):
        await send_move(orient)
        controller.update_last_move_time()
        movement_planner.recent_orient = orient

async def _try_find_bot():
    """Helper để tìm lại bot"""
    available = [b.get('name') for b in game_state.get('bombers', [])]
    
    if available:
        game_state["my_uid"] = None
        mine = next((b for b in game_state.get("bombers", [])
                    if isinstance(b.get("name"), str) and 
                    b["name"].lower() == BOT_NAME.lower()), None)
        if mine:
            game_state["my_uid"] = mine.get("uid")
        else:
            uids = [b.get("uid") for b in game_state.get("bombers", [])]
            if uids:
                game_state["my_uid"] = game_state["bombers"][0].get("uid")

async def bot_loop():
    """Vòng lặp quyết định - ĐƠN GIẢN HÓA"""
    from .survival_ai import choose_next_action, survival_ai
    
    controller = get_bot_controller()
    logger.info(f"🤖 Bắt đầu bot loop (TICK_HZ={TICK_HZ})")
    await asyncio.sleep(0.2)
    
    period = 1.0 / max(TICK_HZ, 1.0)
    
    while True:
        if not game_state.get("game_started", False):
            await asyncio.sleep(0.5)
            continue
        
        try:
            # 1. Kiểm tra bot
            me = get_my_bomber()
            if not me:
                await _try_find_bot()
                await asyncio.sleep(period)
                continue
            
            # 2. Kiểm tra map
            if not game_state.get("map") or len(game_state.get("map", [])) == 0:
                logger.debug("🗺️ CHỜ MAP")
                await asyncio.sleep(period)
                continue
            
            # 3. Kiểm tra vị trí hợp lệ
            current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
            if not (0 <= current_cell[0] <= 15 and 0 <= current_cell[1] <= 15):
                logger.warning(f"🚫 VỊ TRÍ KHÔNG HỢP LỆ: {current_cell}")
                await asyncio.sleep(period)
                continue
            
            # 4. Check arrival block
            if controller.is_in_arrival_block():
                await asyncio.sleep(period)
                continue
            
            # 5. Log cell arrival
            movement_logger.check_and_log_cell_arrival(LOG_MOVEMENT)
            
            # 6. Xử lý plan completion
            did_action = await controller.handle_plan_completion(
                movement_planner, survival_ai, send_bomb
            )
            if did_action:
                await asyncio.sleep(period)
                continue
            
            # 7. Tiếp tục plan hiện tại
            if movement_plan["path_valid"] and movement_plan["path"]:
                did_progress = await controller.execute_plan_continuation(
                    movement_planner, _send_move, CELL_SIZE, REVERSE_LOCK_SECONDS
                )
                if did_progress:
                    await asyncio.sleep(period)
                    continue
                
                # Clear plan nếu hoàn thành
                if not movement_plan["path_valid"] or not movement_plan["path"]:
                    if not movement_plan.get("bomb_placed"):
                        survival_ai.current_plan = None
            
            # 8. Hỏi AI action mới
            action = choose_next_action()
            if action:
                did_progress = await controller.execute_action(
                    action, _send_move, send_bomb, movement_planner, 
                    survival_ai, game_state, CELL_SIZE, REVERSE_LOCK_SECONDS, LOG_MAP
                )
                if did_progress:
                    await asyncio.sleep(period)
                    continue
            else:
                # Không có action → KHÔNG sleep, lặp lại ngay để hỏi AI liên tục
                # cho đến khi có action mới (sau khi hoàn thành plan)
                await asyncio.sleep(0.05)  # Sleep rất ngắn để tránh spam CPU
                continue
            
            # 9. Không có fallback random - Bot sẽ đợi survival_ai tạo plan mới
            # (Xóa fallback random để tránh bot đi lung tung khi plan bị reset)
                
        except Exception as e:
            logger.exception(f"❌ Lỗi bot loop: {e}")
            
            await asyncio.sleep(period)

# ---------- Startup ----------
async def startup():
    """Khởi tạo kết nối bot và bắt đầu vòng lặp quyết định"""
    # Bắt đầu kết nối trong background
    asyncio.create_task(connect_and_start_bot())

async def connect_and_start_bot():
    """Tác vụ background để xử lý kết nối và vòng lặp bot"""
    # Chờ một chút để event loop sẵn sàng
    await asyncio.sleep(2)
    
    while True:
        try:
            await sio.connect(SOCKET_SERVER, transports=["websocket"], auth={"token": TOKEN})
            break
        except Exception as e:
            logger.error(f"Kết nối thất bại: {e}; thử lại sau 3s")
            await asyncio.sleep(3)
    
    # Kiểm tra môi trường dev và bật game_started
    if os.getenv("ENVIRONMENT", "prod") == "dev":
        game_state["game_started"] = True
        logger.info("🔧 MÔI TRƯỜNG DEV TỰ CHẠY BOT")
    
    # Bắt đầu vòng lặp bot
    bot_task = asyncio.create_task(bot_loop())

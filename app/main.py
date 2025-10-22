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
from .utils.movement_logger import MovementLogger
from .utils.map_logger import log_map_state
from .utils.movement_planner import get_movement_planner

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

# ---------- Ack logging helpers ----------
def _ack_logger(event_name: str):
    def _cb(res=None):
        try:
            logger.info(f"ACK {event_name}: {res}")
        except Exception:
            pass
    return _cb

# ---------- Move pacing ----------
_last_move_emit_time: float = 0.0
_arrival_block_until: float = 0.0
_last_pos: tuple = (0.0, 0.0)
_stuck_count: int = 0

def _can_emit_move_now() -> bool:
    global _last_move_emit_time
    min_interval = 1.0 / max(1.0, MAX_CMDS_PER_SEC)
    now = time.monotonic()
    return (now - _last_move_emit_time) >= min_interval

async def _maybe_emit_move(orient: str):
    global _last_move_emit_time
    if not _can_emit_move_now():
        return
    await send_move(orient)
    _last_move_emit_time = time.monotonic()
    movement_planner.recent_orient = orient

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
    logger.info("🚀 Khởi động bot...")
    try:
        # Tạm thời tắt AI đa luồng
        # multithread_ai.start()
        await startup()
        logger.info("🚀 Bot đã sẵn sàng")
    except Exception as e:
        logger.error(f"🚀 Lỗi khởi động: {e}")
    yield
    # Dừng AI đa luồng
    # multithread_ai.stop()
    logger.info("🚀 Bot đã dừng")

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
            logger.warning(f"🚫 KHÔNG THỂ DI CHUYỂN: Game chưa bắt đầu - {orient}")
            return
    
    try:
        # cmd_limiter đã đảm bảo rate limiting (58 cmd/s)
        async with cmd_limiter:
            await sio.emit("move", {"orient": orient}, callback=_ack_logger("move"))
        movement_logger.log_movement(orient, LOG_MOVEMENT)
    except Exception as e:
        logger.error(f"❌ Lỗi di chuyển: {e}")

async def send_bomb():
    """Gửi lệnh đặt bom"""
    # Kiểm tra bot có thể di chuyển không
    me = get_my_bomber()
    # if me and not me.get("movable", True):
    #     logger.warning(f"🚫 KHÔNG THỂ ĐẶT BOM: Bot không thể di chuyển")
    #     logger.warning(f"🔍 ME DETAILS: {me}")
    #     return
    
    # Kiểm tra game đã bắt đầu chưa
    if not game_state.get("game_started", False):
        # Trong môi trường dev, cho phép đặt bom mà không cần start event
        if os.getenv("ENVIRONMENT", "prod") == "dev":
            logger.info(f"💣 CHẾ ĐỘ DEV: Cho phép đặt bom mà không cần start event")
        else:
            logger.warning(f"🚫 KHÔNG THỂ ĐẶT BOM: Game chưa bắt đầu - chờ start event")
            return
    
    try:
        # cmd_limiter đã đảm bảo rate limiting (58 cmd/s)
        async with cmd_limiter:
            await sio.emit("place_bomb", {}, callback=_ack_logger("place_bomb"))
        logger.info(f"💣 ĐẶT BOM")
        
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
    global _last_move_emit_time, _arrival_block_until, _last_pos, _stuck_count
    
    _last_move_emit_time = 0.0
    _arrival_block_until = 0.0
    _last_pos = (0.0, 0.0)
    _stuck_count = 0
    
    movement_planner.reset()
    movement_logger.reset()
    
    logger.info("🔄 GLOBAL RESET: Đã reset toàn bộ global state")

async def bot_loop():
    """Vòng lặp quyết định chính của bot"""
    logger.info(f"🤖 Bắt đầu vòng lặp bot với TICK_HZ={TICK_HZ}")
    await asyncio.sleep(0.2)  # Để state ổn định
    
    period = 1.0 / max(TICK_HZ, 1.0)
    
    while True:
        # Kiểm tra game đã bắt đầu chưa
        if not game_state.get("game_started", False):
            await asyncio.sleep(0.5)
            continue
        
        start_time = time.time()
        try:
            # Kiểm tra trạng thái bot
            me = get_my_bomber()
            if not me:
                available_bombers = [b.get('name') for b in game_state.get('bombers', [])]
                logger.warning(f"🤖 Không tìm thấy bot! Có sẵn: {available_bombers}")
                logger.warning(f"🔍 GAME STATE: connected={game_state.get('connected')}, started={game_state.get('game_started')}")
                logger.warning(f"🔍 BOMBERS: {game_state.get('bombers', [])}")
                logger.warning(f"🔍 MY_UID: {game_state.get('my_uid')}")
                
                # Thử tìm lại bot nếu có bombers
                if available_bombers:
                    logger.info("🔄 Thử tìm lại bot...")
                    # Reset my_uid và tìm lại
                    game_state["my_uid"] = None
                    # Ưu tiên chọn theo BOT_NAME
                    mine = next((b for b in game_state.get("bombers", [])
                                 if isinstance(b.get("name"), str) and b["name"].lower() == BOT_NAME.lower()), None)
                    if mine:
                        game_state["my_uid"] = mine.get("uid")
                        logger.info(f"🤖 CHỌN LẠI BOT THEO TÊN: {mine.get('name')} ({game_state['my_uid']})")
                    else:
                        uids = [b.get("uid") for b in game_state.get("bombers", [])]
                        if uids:
                            game_state["my_uid"] = game_state["bombers"][0].get("uid")
                            logger.info(f"🤖 CHỌN LẠI BOT (FALLBACK): {game_state['bombers'][0].get('name')} ({game_state['my_uid']})")
                        else:
                            logger.warning(f"🚫 KHÔNG TÌM THẤY BOT: Có sẵn: {[b.get('name') for b in game_state.get('bombers', [])]}")
                        me = get_my_bomber()  # Thử lấy lại
            
            # Kiểm tra game có hoạt động không
            game_active = game_state["connected"] and (game_state["game_started"] or os.getenv("ENVIRONMENT", "prod") == "dev")
            
            # Kiểm tra map có sẵn sàng không (tránh lỗi sau khi hồi sinh)
            map_ready = game_state.get("map") and len(game_state.get("map", [])) > 0
            
            if not map_ready and game_active:
                logger.info(f"🗺️ CHỜ MAP: Map chưa sẵn sàng sau khi hồi sinh, tạm dừng AI")
            
            if game_active and me and map_ready:
                # Log chi tiết bot info
                logger.debug(f"🤖 BOT INFO: {me}")
                # Kiểm tra vị trí bot có hợp lệ không
                current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
                if not (0 <= current_cell[0] <= 15 and 0 <= current_cell[1] <= 15):
                    logger.warning(f"🚫 BOT Ở VỊ TRÍ KHÔNG HỢP LỆ: {current_cell} - Tạm dừng AI")
                    await asyncio.sleep(period)
                    continue
                
                # Khai báo tất cả biến global cần thiết
                global _arrival_block_until, _last_pos, _stuck_count, _recent_orient, _reverse_block_until
                
                # Nếu vừa tới nơi, tạm không nhận action/fallback để tránh đảo chiều (dwell)
                if time.monotonic() < _arrival_block_until:
                    await asyncio.sleep(period)
                    continue
                
                # BỎ QUA stuck detection để bot luôn có thể di chuyển
                # cur_pos = (me.get("x", 0.0), me.get("y", 0.0))
                # if abs(cur_pos[0] - _last_pos[0]) < 0.1 and abs(cur_pos[1] - _last_pos[1]) < 0.1:
                #     _stuck_count += 1
                #     if _stuck_count >= 20:  
                #         logger.info(f"🚫 STUCK: Bot không di chuyển trong {_stuck_count} tick, tạm dừng movement")
                #         _reset_movement_plan()
                #         _arrival_block_until = time.monotonic() + 0.1
                #         await asyncio.sleep(period)
                #         continue
                # else:
                #     _stuck_count = 0
                # _last_pos = cur_pos
                
                # Check và log khi bot vào ô mới
                movement_logger.check_and_log_cell_arrival(LOG_MOVEMENT)
                
                did_progress = False
                
                # CHECK DELAY - Ưu tiên cao nhất!
                if movement_plan.get("just_completed"):
                    completed_time = movement_plan["just_completed"]
                    if time.time() - completed_time < 1.0:
                        # CHỈ đặt bom khi plan là bomb_chest, không đặt bom khi plan là collect_item
                        if not movement_plan.get("bomb_placed"):
                            # Lấy plan_type đã lưu trong movement_plan (thay vì survival_ai.current_plan có thể bị clear)
                            plan_type = movement_plan.get("plan_type")
                            
                            if plan_type == "bomb_chest":
                                me = get_my_bomber()
                                if me:
                                    current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
                                    # CHỈ log 1 lần duy nhất
                                    if not movement_plan.get("logged_bomb_action"):
                                        logger.info(f"💣 PATH HOÀN THÀNH - ĐẶT BOM TẠI: {current_cell}")
                                        movement_plan["logged_bomb_action"] = True
                                    await send_bomb()
                                    movement_plan["bomb_placed"] = True
                            else:
                                # CHỈ log 1 lần duy nhất
                                if not movement_plan.get("logged_bomb_action"):
                                    logger.info(f"✅ PATH HOÀN THÀNH - KHÔNG ĐẶT BOM: Plan type = {plan_type}")
                                    movement_plan["logged_bomb_action"] = True
                        await asyncio.sleep(period)
                        continue
                    else:
                        movement_plan.pop("just_completed", None)
                        movement_plan.pop("bomb_placed", None)
                        movement_plan.pop("logged_bomb_action", None)
                        movement_plan.pop("plan_type", None)
                
                # Đặt bom ngay khi đến đích (trước khi chạy tiếp)
                if movement_plan.get("need_bomb_at_target"):
                    target_cell = movement_plan["need_bomb_at_target"]
                    logger.info(f"💣 ĐẶT BOM NGAY TẠI: {target_cell}")
                    await send_bomb()
                    
                    # Set flag để survival_ai biết phải thoát ngay
                    from .survival_ai import survival_ai
                    survival_ai.must_escape_bomb = True
                    logger.warning(f"⚡ SET FLAG: must_escape_bomb = True (main.py)")
                    
                    # KHÔNG clear plan ngay lập tức - để bot tiếp tục thực hiện escape path
                    movement_plan.pop("need_bomb_at_target", None)
                    movement_plan["bomb_placed"] = True  # Đánh dấu đã đặt bom
                    logger.info(f"🔄 TIẾP TỤC ESCAPE PATH: Không clear plan, tiếp tục thực hiện escape")
                    did_progress = True
                
                # Tiếp tục plan dài hạn
                if movement_plan["path_valid"] and movement_plan["path"]:
                    if movement_plan.get("skip_once"):
                        movement_plan["skip_once"] = False
                    else:
                        movement_planner.advance(CELL_SIZE, REVERSE_LOCK_SECONDS)
                        current_orient = movement_plan["orient"]
                        if current_orient and current_orient in DIRECTIONS:
                            await _maybe_emit_move(current_orient)
                            _stuck_count = 0
                            did_progress = True
                        
                        # Kiểm tra nếu plan đã hoàn thành
                        if not movement_plan["path_valid"] or not movement_plan["path"]:
                            # CHỈ clear plan khi thực sự hoàn thành (không phải khi vừa đặt bom)
                            if not movement_plan.get("bomb_placed"):
                                # Clear plan trong AI khi hoàn thành
                                from .survival_ai import survival_ai
                                survival_ai.current_plan = None
                                logger.info(f"✅ CLEAR PLAN: Đã hoàn thành plan dài hạn")
                            else:
                                # Đã đặt bom nhưng chưa hoàn thành escape path
                                logger.info(f"🔄 ESCAPE MODE: Đã đặt bom, tiếp tục thực hiện escape path")
                else:
                    # Kiểm tra nếu vừa hoàn thành plan (trong vòng 1 giây)
                    if movement_plan.get("just_completed"):
                        completed_time = movement_plan["just_completed"]
                        if time.time() - completed_time < 1.0:  # 1 giây delay
                            logger.info(f"⏳ DELAY SAU KHI HOÀN THÀNH PLAN: {time.time() - completed_time:.1f}s")
                            did_progress = True
                        else:
                            # Hết delay, xóa flag và hỏi AI
                            movement_plan.pop("just_completed", None)
                    
                    # Không có plan: hỏi AI
                    if not movement_plan.get("just_completed"):
                        # Lấy current_plan TRƯỚC khi choose_next_action (có thể bị clear bên trong)
                        from .survival_ai import survival_ai
                        current_plan_type = survival_ai.current_plan.get("type") if survival_ai.current_plan else None
                        
                        action = choose_next_action()
                        
                        # Lưu plan_type từ current_plan vào action (nếu có)
                        if action and current_plan_type and action.get("type") == "move":
                            action["plan_type"] = current_plan_type
                    
                    if action is None:
                        global _last_ai_idle_time
                        current_time = time.time() * 1000
                        if '_last_ai_idle_time' not in globals():
                            _last_ai_idle_time = current_time
                        
                        idle_duration = current_time - _last_ai_idle_time
                        if idle_duration > 10000:
                            logger.warning(f"🚨 AI ĐỨNG IM QUÁ LÂU: {idle_duration:.0f}ms")
                            did_progress = False
                            _last_ai_idle_time = current_time
                        else:
                            _last_ai_idle_time = current_time
                            
                    if action:
                        if action["type"] == "move":
                            me = get_my_bomber()
                            if me:
                                current_cell = pos_to_cell(me.get("x", 0), me.get("y", 0))
                                logger.info(f"🤖 VỊ TRÍ BOT: ({me.get('x', 0):.1f}, {me.get('y', 0):.1f}) → ô {current_cell}")
                            
                            log_map_state(game_state, LOG_MAP)
                            
                            goal_cell = action.get("goal_cell")
                            if goal_cell:
                                movement_planner.plan_path(goal_cell)
                                # Lưu plan_type từ action vào movement_plan để dùng khi hoàn thành path
                                if action.get("plan_type"):
                                    movement_plan["plan_type"] = action["plan_type"]
                                direction = movement_planner.get_next_direction()
                                if direction:
                                    await _maybe_emit_move(direction)
                            movement_plan["skip_once"] = True
                            _stuck_count = 0
                            did_progress = True
                        elif action["type"] == "bomb":
                            await send_bomb()
                            
                            # Set flag để survival_ai biết phải thoát ngay
                            from .survival_ai import survival_ai
                            survival_ai.must_escape_bomb = True
                            logger.warning(f"⚡ SET FLAG: must_escape_bomb = True (survival_ai)")
                            
                            did_progress = True
                        else:
                            direction = action["orient"]
                            if movement_planner.recent_orient and time.monotonic() < movement_planner.reverse_block_until:
                                reverse = {"UP":"DOWN","DOWN":"UP","LEFT":"RIGHT","RIGHT":"LEFT"}
                                if direction == reverse.get(movement_planner.recent_orient):
                                    direction = None
                            if direction:
                                await _maybe_emit_move(direction)
                            _stuck_count = 0
                            did_progress = True
                    else:
                        if movement_plan["path"]:
                            movement_planner.reset()
                        did_progress = False
                        
                # FALLBACK LUÔN HOẠT ĐỘNG: Đảm bảo bot luôn có hành động
                if not did_progress:
                    try:
                        # LUÔN thử di chuyển bất kỳ hướng nào để tránh bị kẹt
                        for orient in ["UP", "DOWN", "LEFT", "RIGHT"]:
                            await _maybe_emit_move(orient)
                            # Reset stuck counter khi có fallback movement
                            _stuck_count = 0
                            break
                                
                    except Exception as e:
                        logger.error(f"🤖 FALLBACK ERROR: {e}")
            
            # Flush log di chuyển định kỳ
            movement_logger.flush()
            
            await asyncio.sleep(period)
            
        except asyncio.CancelledError:
            logger.info(f"🤖 Vòng lặp bot bị hủy")
            break
        except Exception as e:
            logger.exception(f"Lỗi vòng lặp bot: {e}")
            await asyncio.sleep(0.1)

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

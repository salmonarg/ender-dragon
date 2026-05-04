import asyncio
import websockets
import json
import time
import requests
import api4agent
from typing import Optional
from session_manager import session_manager
from config import BOT_CONFIG, SERVER_CONFIG, CONNECTION_CONFIG
from logger import setup_logger

logger = setup_logger("client_runner")


class ClientRunner:
    def __init__(self, room: Optional[str] = None):
        self.room = room or BOT_CONFIG["room"]
        self.msg_buffer = []
        self.processed_msg_ids = set()
        self.last_reply_time = 0.0
        self.msg_count = 0
        self.memory_check_count = 0

        self.ws_base = SERVER_CONFIG["ws_base"]
        self.heartbeat_interval = CONNECTION_CONFIG["heartbeat_interval"]
        self.buffer_max = CONNECTION_CONFIG["message_buffer_max"]
        self.memory_interval = CONNECTION_CONFIG["memory_interval"]
        self.reply_cooldown = CONNECTION_CONFIG["reply_cooldown"]
        self.base_delay = CONNECTION_CONFIG["initial_retry_delay"]
        self.max_delay = CONNECTION_CONFIG["max_retry_delay"]

    def _is_message_fresh(self, msg: dict) -> bool:
        msg_time_raw = msg.get("timestamp")
        if msg_time_raw is None:
            return False
        msg_time = int(msg_time_raw) // 1000
        return (time.time() - msg_time) <= 60

    def _should_process(self, msg: dict) -> bool:
        msg_id = msg.get("msg_id")
        if not msg_id:
            return False
        if msg_id in self.processed_msg_ids:
            return False
        if not self._is_message_fresh(msg):
            return False
        return True

    def _is_on_cooldown(self) -> bool:
        return (time.time() - self.last_reply_time) < self.reply_cooldown

    def _extract_valid_messages(self, msg_data) -> list:
        if isinstance(msg_data, list):
            return [m for m in msg_data if isinstance(m, dict) and 'text' in m]
        if isinstance(msg_data, dict) and 'text' in msg_data:
            return [msg_data]
        return []

    def _trim_buffer(self):
        if len(self.msg_buffer) > self.buffer_max:
            removed = self.msg_buffer[:-self.buffer_max]
            self.msg_buffer = self.msg_buffer[-self.buffer_max:]
            logger.debug(f'[Buffer] 裁剪{len(removed)}条，当前{len(self.msg_buffer)}条')

    async def _send_message(self, ws, content: str):
        try:
            await ws.send(content)
            logger.info(f"[Bot] 发送: {content}")
        except Exception as e:
            logger.error(f"[Bot] 发送失败: {e}")

    async def _handle_actions(self, ws, actions: list):
        for action in actions:
            if action["action"] == "send":
                await self._send_message(ws, action["msg_content"])
            elif action["action"] == "delete":
                logger.info(f"[Bot] 删除消息: {action['msg_id']} (channel: {action['channel']})")

    async def _process_latest(self, ws, last_msg: dict):
        if last_msg.get("sender_username") == "EnderDragon":
            return
        if not self._should_process(last_msg):
            return
        if self._is_on_cooldown():
            logger.debug(f"[Cooldown] 冷却中，跳过回复")
            self.processed_msg_ids.add(last_msg["msg_id"])
            return

        logger.info(f"[Process] 处理: {last_msg['sender_username']}: {last_msg['text']}")

        # Await the async AI call
        need_reply = await api4agent.dragon_eyes(self.msg_buffer)

        self.processed_msg_ids.add(last_msg["msg_id"])

        if not need_reply:
            return

        # Await the async AI call
        actions = await api4agent.dragon_speaking(self.msg_buffer, channel=self.room)
        if actions:
            await self._handle_actions(ws, actions)
            self.last_reply_time = time.time()

    async def _check_memory_summary(self):
        self.memory_check_count += 1
        if self.memory_check_count >= self.memory_interval:
            self.memory_check_count = 0
            logger.info(f"[Memory] 已处理{self.msg_count}条，正在总结...")
            # Await the async AI call
            await api4agent.memory_conclude(self.msg_buffer)
            logger.info("[Memory] 总结完成")

    async def run(self):
        retry_attempt = 0

        while True:
            cookie = session_manager.get_session(force_refresh=False)
            if cookie is None:
                delay = min(self.base_delay * (2 ** retry_attempt), self.max_delay)
                logger.warning(f"[Connection] 无法获取session，{delay}秒后重试... (attempt {retry_attempt})")
                retry_attempt += 1
                await asyncio.sleep(delay)
                continue

            ws_url = f"{self.ws_base}/{self.room}"
            logger.info(f"[Connection] 连接: {ws_url}")

            try:
                async with websockets.connect(ws_url, additional_headers={"Cookie": cookie}) as ws:
                    logger.info(f"[Connection] 已连接房间: {self.room}")
                    last_ping = time.time()
                    retry_attempt = 0

                    async for raw_msg in ws:
                        try:
                            if time.time() - last_ping > self.heartbeat_interval:
                                await ws.ping()
                                last_ping = time.time()

                            msg_data = json.loads(raw_msg)
                            valid = self._extract_valid_messages(msg_data)
                            if not valid:
                                continue

                            self.msg_count += len(valid)
                            self.msg_buffer.extend(valid)
                            self._trim_buffer()

                            await self._process_latest(ws, self.msg_buffer[-1])
                            await self._check_memory_summary()

                        except json.JSONDecodeError:
                            logger.error(f"[Parse] JSON错误: {raw_msg[:50]}")
                        except Exception as e:
                            logger.error(f"[Process] 处理异常: {e}")

            except Exception as e:
                delay = min(self.base_delay * (2 ** retry_attempt), self.max_delay)
                logger.error(f"[Connection] 连接断开: {e}，{delay}秒后尝试重连... (attempt {retry_attempt})")
                retry_attempt += 1
                await asyncio.sleep(delay)

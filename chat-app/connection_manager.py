from typing import Dict, List
from datetime import datetime
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.user_connections: Dict[int, List[WebSocket]] = {}
        self.server_connections: Dict[int, List[WebSocket]] = {}
        self.connection_info: Dict[WebSocket, Dict] = {}
        print("ConnectionManager initialized")

    async def connect(self, websocket: WebSocket, user_id: int = None):
        await websocket.accept()
        
        # 存储连接信息
        self.connection_info[websocket] = {
            "user_id": user_id,
            "connected_at": datetime.now(),
            "current_server_id": None  # 初始没有选择服务器
        }
        
        # 添加到用户连接映射
        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = []
            self.user_connections[user_id].append(websocket)
            
        print(f"New connection: user_id={user_id}")
        print(f"Total connections: {len(self.connection_info)}")

    def disconnect(self, websocket: WebSocket):
        # 获取连接信息
        conn_info = self.connection_info.get(websocket, {})
        user_id = conn_info.get("user_id")
        server_id = conn_info.get("current_server_id")
        
        # 从用户连接映射中移除
        if user_id and user_id in self.user_connections:
            if websocket in self.user_connections[user_id]:
                self.user_connections[user_id].remove(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        # 从服务器连接映射中移除
        if server_id and server_id in self.server_connections:
            if websocket in self.server_connections[server_id]:
                self.server_connections[server_id].remove(websocket)
            if not self.server_connections[server_id]:
                del self.server_connections[server_id]
        
        # 移除连接信息
        if websocket in self.connection_info:
            del self.connection_info[websocket]
            
        print(f"Connection closed: user_id={user_id}, server_id={server_id}")
        print(f"Total connections: {len(self.connection_info)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            print(f"Error sending personal message: {e}")
            # 如果发送失败，可能连接已断开，尝试断开连接
            self.disconnect(websocket)

    async def broadcast(self, message: str, server_id: int = None, exclude: WebSocket = None):
        """
        广播消息到指定服务器的所有连接，或者所有连接
        
        Args:
            message: 要发送的消息
            server_id: 服务器ID，如果指定则只发送给该服务器的连接
            exclude: 要排除的连接
        """
        targets = []
        
        if server_id is not None:
            # 发送给特定服务器的所有连接
            targets = self.server_connections.get(server_id, [])
        else:
            # 发送给所有连接
            targets = list(self.connection_info.keys())
        
        disconnected = []
        for connection in targets:
            if connection != exclude:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    print(f"Error broadcasting message: {e}")
                    disconnected.append(connection)
        
        # 处理断开的连接
        for connection in disconnected:
            self.disconnect(connection)

    def set_user_server(self, websocket: WebSocket, server_id: int):
        """
        设置用户当前选择的服务器
        
        Args:
            websocket: WebSocket连接
            server_id: 服务器ID
        """
        if websocket not in self.connection_info:
            return
        
        # 获取旧的服务器ID
        old_server_id = self.connection_info[websocket].get("current_server_id")
        
        # 如果已经在相同的服务器中，不需要更改
        if old_server_id == server_id:
            return
        
        # 从旧服务器的连接列表中移除
        if old_server_id and old_server_id in self.server_connections:
            if websocket in self.server_connections[old_server_id]:
                self.server_connections[old_server_id].remove(websocket)
            if not self.server_connections[old_server_id]:
                del self.server_connections[old_server_id]
        
        # 添加到新服务器的连接列表
        if server_id:
            if server_id not in self.server_connections:
                self.server_connections[server_id] = []
            self.server_connections[server_id].append(websocket)
        
        # 更新连接信息
        self.connection_info[websocket]["current_server_id"] = server_id
        
        print(f"User switched server: user_id={self.connection_info[websocket].get('user_id')}, server_id={server_id}")

    def get_user_connections(self, user_id: int) -> List[WebSocket]:
        """获取用户的所有连接"""
        return self.user_connections.get(user_id, [])

    def get_server_connections(self, server_id: int) -> List[WebSocket]:
        """获取服务器的所有连接"""
        return self.server_connections.get(server_id, [])

    def get_connection_info(self, websocket: WebSocket) -> Dict:
        """获取连接信息"""
        return self.connection_info.get(websocket, {}) 
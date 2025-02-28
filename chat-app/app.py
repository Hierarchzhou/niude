from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request, Form, Cookie, Response, HTTPException, status, UploadFile, File, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import update, text
import json
from typing import List, Dict, Optional
import uuid
import datetime
import shutil
import os
import random
import string
from pydantic import BaseModel
import asyncio
import jwt
from jose import JWTError

from database import get_db, Message, User, Server, ServerMember

app = FastAPI(title="简易聊天应用")

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 存储活跃的WebSocket连接
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_connections: Dict[int, List[WebSocket]] = {}  # 用户ID到WebSocket连接的映射
        self.server_connections: Dict[int, List[WebSocket]] = {}  # 服务器ID到WebSocket连接的映射
    
    async def connect(self, websocket: WebSocket, user_id: Optional[int] = None, server_ids: Optional[List[int]] = None):
        try:
            await websocket.accept()
            self.active_connections.append(websocket)
            print(f"WebSocket连接已接受，当前活跃连接数: {len(self.active_connections)}")
            
            # 如果有用户ID，将连接与用户关联
            if user_id:
                if user_id not in self.user_connections:
                    self.user_connections[user_id] = []
                self.user_connections[user_id].append(websocket)
                print(f"用户 {user_id} 的连接数: {len(self.user_connections[user_id])}")
            
            # 如果有服务器ID，将连接与服务器关联
            if server_ids:
                print(f"正在将连接关联到服务器: {server_ids}")
                for server_id in server_ids:
                    if server_id not in self.server_connections:
                        self.server_connections[server_id] = []
                    self.server_connections[server_id].append(websocket)
                    print(f"服务器 {server_id} 的连接数: {len(self.server_connections[server_id])}")
            else:
                print("没有服务器ID提供，连接不会关联到任何服务器")
            
            # 打印当前所有服务器的连接情况
            print(f"当前服务器连接情况: {', '.join([f'服务器{sid}: {len(conns)}个连接' for sid, conns in self.server_connections.items()])}")
            
            return True
        except Exception as e:
            print(f"建立WebSocket连接时出错: {e}")
            return False
    
    def disconnect(self, websocket: WebSocket, user_id: Optional[int] = None):
        try:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                print(f"WebSocket连接已移除，剩余活跃连接数: {len(self.active_connections)}")
            
            # 如果有用户ID，从用户连接列表中移除
            if user_id and user_id in self.user_connections:
                if websocket in self.user_connections[user_id]:
                    self.user_connections[user_id].remove(websocket)
                    print(f"用户 {user_id} 的连接已移除，剩余连接数: {len(self.user_connections[user_id])}")
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]
                    print(f"用户 {user_id} 已没有活跃连接")
            
            # 从所有服务器连接列表中移除
            for server_id in list(self.server_connections.keys()):
                if websocket in self.server_connections[server_id]:
                    self.server_connections[server_id].remove(websocket)
                    print(f"服务器 {server_id} 的连接已移除，剩余连接数: {len(self.server_connections[server_id])}")
                    if not self.server_connections[server_id]:
                        del self.server_connections[server_id]
                        print(f"服务器 {server_id} 已没有活跃连接")
            
            # 打印当前所有服务器的连接情况
            if self.server_connections:
                print(f"当前服务器连接情况: {', '.join([f'服务器{sid}: {len(conns)}个连接' for sid, conns in self.server_connections.items()])}")
            else:
                print("当前没有服务器有活跃连接")
        except Exception as e:
            print(f"断开WebSocket连接时出错: {e}")
    
    async def is_connection_active(self, websocket: WebSocket) -> bool:
        """检查WebSocket连接是否仍然活跃"""
        try:
            # 尝试发送一个ping帧
            pong_waiter = await websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=1.0)
            return True
        except Exception:
            return False
    
    async def clean_inactive_connections(self):
        """清理不活跃的连接"""
        inactive = []
        for connection in self.active_connections:
            if not await self.is_connection_active(connection):
                inactive.append(connection)
        
        for conn in inactive:
            print(f"移除不活跃的连接")
            self.disconnect(conn)
        
        return len(inactive)
    
    async def broadcast(self, message: str, server_id: int = None):
        """
        广播消息到所有连接或特定服务器的连接
        
        Args:
            message: 要发送的消息
            server_id: 服务器ID，如果指定则只发送给该服务器的连接
        """
        # 如果指定了server_id，则调用broadcast_to_server方法
        if server_id is not None:
            await self.broadcast_to_server(message, server_id)
            return
            
        # 先清理不活跃的连接
        await self.clean_inactive_connections()
        
        disconnected = []
        for i, connection in enumerate(self.active_connections):
            try:
                await connection.send_text(message)
                print(f"消息已发送到连接 {i+1}/{len(self.active_connections)}")
            except Exception as e:
                print(f"发送消息到连接 {i+1} 失败: {e}")
                disconnected.append(connection)
        
        # 移除断开的连接
        for conn in disconnected:
            self.disconnect(conn)
            print(f"已移除断开的连接，剩余连接数: {len(self.active_connections)}")
    
    async def broadcast_to_server(self, message: str, server_id: int):
        """向特定服务器的所有连接广播消息"""
        if server_id not in self.server_connections:
            print(f"服务器 {server_id} 没有活跃连接")
            return
        
        # 先清理不活跃的连接
        await self.clean_inactive_connections()
        
        disconnected = []
        connections = self.server_connections[server_id]
        print(f"向服务器 {server_id} 的 {len(connections)} 个连接广播消息")
        for i, connection in enumerate(connections):
            try:
                await connection.send_text(message)
                print(f"消息已发送到服务器 {server_id} 的连接 {i+1}/{len(connections)}")
            except Exception as e:
                print(f"发送消息到服务器 {server_id} 的连接 {i+1} 失败: {e}")
                disconnected.append(connection)
        
        # 移除断开的连接
        for conn in disconnected:
            self.disconnect(conn)
        
        if server_id in self.server_connections and not self.server_connections[server_id]:
            del self.server_connections[server_id]
            print(f"服务器 {server_id} 已没有活跃连接")

    # 添加发送个人消息的方法
    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            print(f"发送个人消息失败: {e}")
            # 如果发送失败，可能连接已断开，尝试断开连接
            self.disconnect(websocket)
    
    # 添加获取连接信息的方法
    def get_connection_info(self, websocket: WebSocket) -> dict:
        """获取连接信息"""
        # 在这个简化版本中，我们只返回用户ID和当前服务器ID
        # 在实际应用中，可能需要存储更多信息
        for user_id, connections in self.user_connections.items():
            if websocket in connections:
                # 查找连接所在的服务器
                current_server_id = None
                for server_id, server_connections in self.server_connections.items():
                    if websocket in server_connections:
                        current_server_id = server_id
                        break
                
                return {
                    "user_id": user_id,
                    "current_server_id": current_server_id
                }
        
        return {}
    
    # 添加设置用户服务器的方法
    def set_user_server(self, websocket: WebSocket, server_id: int):
        """设置用户当前的服务器"""
        # 从所有服务器连接中移除此连接
        for sid in list(self.server_connections.keys()):
            if websocket in self.server_connections[sid]:
                self.server_connections[sid].remove(websocket)
                if not self.server_connections[sid]:
                    del self.server_connections[sid]
        
        # 添加到新服务器
        if server_id not in self.server_connections:
            self.server_connections[server_id] = []
        self.server_connections[server_id].append(websocket)
        print(f"用户已切换到服务器 {server_id}")

manager = ConnectionManager()

# 用户会话存储
user_sessions = {}

# 生成会话ID
def generate_session_id():
    return str(uuid.uuid4())

# 检查用户是否已登录
def get_current_user(session_id: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if session_id and session_id in user_sessions:
        user_id = user_sessions[session_id]
        return db.query(User).filter(User.id == user_id).first()
    return None

# 主页路由
@app.get("/", response_class=HTMLResponse)
async def get_home(user: Optional[User] = Depends(get_current_user)):
    # 如果用户已登录，重定向到聊天页面
    if user:
        return RedirectResponse(url="/chat")
    
    # 否则重定向到登录页面
    return RedirectResponse(url="/login")

# 聊天页面
@app.get("/chat", response_class=HTMLResponse)
async def get_chat(user: Optional[User] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>简易聊天应用</title>
        <meta charset="utf-8">
        <meta http-equiv="refresh" content="0; url=/static/chat.html">
    </head>
    <body>
        <p>正在跳转到聊天页面...</p>
    </body>
    </html>
    """

# 登录页面
@app.get("/login", response_class=HTMLResponse)
async def get_login():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>登录 - 简易聊天应用</title>
        <meta charset="utf-8">
        <meta http-equiv="refresh" content="0; url=/static/login.html">
    </head>
    <body>
        <p>正在跳转到登录页面...</p>
    </body>
    </html>
    """


# 注册页面
@app.get("/register", response_class=HTMLResponse)
async def get_register():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>注册 - 简易聊天应用</title>
        <meta charset="utf-8">
        <meta http-equiv="refresh" content="0; url=/static/register.html">
    </head>
    <body>
        <p>正在跳转到注册页面...</p>
    </body>
    </html>
    """

# 用户注册API
@app.post("/api/register")
async def register(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    # 检查邮箱是否已存在
    existing_email = db.query(User).filter(User.email == email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被注册"
        )
    
    # 创建新用户
    hashed_password = User.hash_password(password)
    new_user = User(
        username=username,
        email=email,
        password_hash=hashed_password
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # 创建会话
    session_id = generate_session_id()
    user_sessions[session_id] = new_user.id
    
    # 设置Cookie并重定向到聊天页面
    response = RedirectResponse(url="/chat", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="session_id", value=session_id)
    
    return response

# 用户登录API
@app.post("/api/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # 查找用户
    user = db.query(User).filter(User.username == username).first()
    
    # 验证用户和密码
    if not user or not user.verify_password(password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    # 更新最后登录时间
    user.last_login = datetime.datetime.utcnow()
    db.commit()
    
    # 创建会话
    session_id = generate_session_id()
    user_sessions[session_id] = user.id
    
    # 设置Cookie并重定向到聊天页面
    response = RedirectResponse(url="/chat", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="session_id", value=session_id)
    
    return response

# 用户登出API
@app.get("/api/logout")
async def logout(response: Response, session_id: Optional[str] = Cookie(None)):
    if session_id and session_id in user_sessions:
        del user_sessions[session_id]
    
    response = RedirectResponse(url="/login")
    response.delete_cookie(key="session_id")
    
    return response

# 获取当前用户信息API
@app.get("/api/users/me")
async def get_user_me(user: Optional[User] = Depends(get_current_user)):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录"
        )
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at,
        "last_login": user.last_login,
        "display_name": user.display_name,
        "bio": user.bio,
        "avatar_url": user.avatar_url
    }

# 获取所有用户API
@app.get("/api/users")
async def get_users(db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user)):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录"
        )
    
    users = db.query(User).all()
    return [{"id": u.id, "username": u.username, "email": u.email} for u in users]

# WebSocket端点
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(None),
    db: Session = Depends(get_db)
):
    # 验证token
    user = None
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            if username:
                user = db.query(User).filter(User.username == username).first()
        except JWTError:
            await websocket.close(code=1008, reason="无效的token")
            return
    
    # 连接到WebSocket
    await manager.connect(websocket, user.id if user else None)
    
    try:
        # 发送欢迎消息
        welcome_msg = {
            "type": "system",
            "content": f"欢迎 {user.username if user else '游客'} 加入聊天！",
            "timestamp": datetime.datetime.now().isoformat()
        }
        await manager.send_personal_message(json.dumps(welcome_msg), websocket)
        
        # 接收和处理消息
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                content = message_data.get("content", "").strip()
                server_id = message_data.get("server_id")
                
                if not content:
                    continue
                
                # 如果消息包含服务器ID，则设置用户当前的服务器
                if server_id:
                    manager.set_user_server(websocket, server_id)
                    
                    # 检查服务器是否存在
                    server = db.query(Server).filter(Server.id == server_id).first()
                    if not server:
                        error_msg = {
                            "type": "error",
                            "content": f"服务器ID {server_id} 不存在",
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        await manager.send_personal_message(json.dumps(error_msg), websocket)
                        continue
                    
                    # 检查用户是否是服务器成员
                    if user and server and user not in server.members:
                        error_msg = {
                            "type": "error",
                            "content": f"您不是服务器 {server.name} 的成员",
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        await manager.send_personal_message(json.dumps(error_msg), websocket)
                        continue
                
                # 创建消息记录
                if server_id and user:
                    db_message = Message(
                        content=content,
                        sender=user.username,
                        user_id=user.id,
                        server_id=server_id
                    )
                    db.add(db_message)
                    db.commit()
                    db.refresh(db_message)
                
                # 构建消息对象
                message_obj = {
                    "type": "chat",
                    "content": content,
                    "sender": user.username if user else "游客",
                    "user_id": user.id if user else None,
                    "server_id": server_id,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "message_id": db_message.id if server_id and user else None
                }
                
                # 广播消息
                if server_id:
                    # 发送到特定服务器
                    await manager.broadcast(json.dumps(message_obj), server_id=server_id)
                else:
                    # 全局消息
                    await manager.broadcast(json.dumps(message_obj))
                
            except json.JSONDecodeError:
                error_msg = {
                    "type": "error",
                    "content": "无效的消息格式",
                    "timestamp": datetime.datetime.now().isoformat()
                }
                await manager.send_personal_message(json.dumps(error_msg), websocket)
            except Exception as e:
                print(f"处理消息错误: {e}")
                error_msg = {
                    "type": "error",
                    "content": "处理消息时出错",
                    "timestamp": datetime.datetime.now().isoformat()
                }
                await manager.send_personal_message(json.dumps(error_msg), websocket)
    
    except WebSocketDisconnect:
        # 断开连接
        manager.disconnect(websocket)
        
        # 广播用户离开的消息
        if user:
            leave_msg = {
                "type": "system",
                "content": f"{user.username} 离开了聊天",
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            # 获取用户当前的服务器ID
            conn_info = manager.get_connection_info(websocket)
            server_id = conn_info.get("current_server_id")
            
            # 广播消息
            if server_id:
                await manager.broadcast(json.dumps(leave_msg), server_id=server_id)
            else:
                await manager.broadcast(json.dumps(leave_msg))

# 添加新的WebSocket端点，处理带有session_id参数的连接
@app.websocket("/ws/chat")
async def chat_websocket_endpoint(
    websocket: WebSocket,
    session_id: str = Query(None),
    db: Session = Depends(get_db)
):
    # 验证session_id
    user = None
    if session_id and session_id in user_sessions:
        user_id = user_sessions[session_id]
        user = db.query(User).filter(User.id == user_id).first()
    
    # 连接到WebSocket
    await manager.connect(websocket, user.id if user else None)
    
    try:
        # 发送欢迎消息
        welcome_msg = {
            "type": "system",
            "content": f"欢迎 {user.username if user else '游客'} 加入聊天！",
            "timestamp": datetime.datetime.now().isoformat()
        }
        await manager.send_personal_message(json.dumps(welcome_msg), websocket)
        
        # 接收和处理消息
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                content = message_data.get("content", "").strip()
                server_id = message_data.get("server_id")
                
                if not content:
                    continue
                
                # 如果消息包含服务器ID，则设置用户当前的服务器
                if server_id:
                    manager.set_user_server(websocket, server_id)
                    
                    # 检查服务器是否存在
                    server = db.query(Server).filter(Server.id == server_id).first()
                    if not server:
                        error_msg = {
                            "type": "error",
                            "content": f"服务器ID {server_id} 不存在",
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        await manager.send_personal_message(json.dumps(error_msg), websocket)
                        continue
                    
                    # 检查用户是否是服务器成员
                    if user and server and user not in server.members:
                        error_msg = {
                            "type": "error",
                            "content": f"您不是服务器 {server.name} 的成员",
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        await manager.send_personal_message(json.dumps(error_msg), websocket)
                        continue
                
                # 创建消息记录
                if server_id and user:
                    db_message = Message(
                        content=content,
                        sender=user.username,
                        user_id=user.id,
                        server_id=server_id
                    )
                    db.add(db_message)
                    db.commit()
                    db.refresh(db_message)
                
                # 构建消息对象
                message_obj = {
                    "type": "chat",
                    "content": content,
                    "sender": user.username if user else "游客",
                    "user_id": user.id if user else None,
                    "server_id": server_id,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "message_id": db_message.id if server_id and user else None
                }
                
                # 广播消息
                if server_id:
                    # 发送到特定服务器
                    await manager.broadcast(json.dumps(message_obj), server_id=server_id)
                else:
                    # 全局消息
                    await manager.broadcast(json.dumps(message_obj))
                
            except json.JSONDecodeError:
                error_msg = {
                    "type": "error",
                    "content": "无效的消息格式",
                    "timestamp": datetime.datetime.now().isoformat()
                }
                await manager.send_personal_message(json.dumps(error_msg), websocket)
            except Exception as e:
                print(f"处理消息错误: {e}")
                error_msg = {
                    "type": "error",
                    "content": "处理消息时出错",
                    "timestamp": datetime.datetime.now().isoformat()
                }
                await manager.send_personal_message(json.dumps(error_msg), websocket)
    
    except WebSocketDisconnect:
        # 断开连接
        manager.disconnect(websocket)
        
        # 广播用户离开的消息
        if user:
            leave_msg = {
                "type": "system",
                "content": f"{user.username} 离开了聊天",
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            # 获取用户当前的服务器ID
            conn_info = manager.get_connection_info(websocket)
            server_id = conn_info.get("current_server_id")
            
            # 广播消息
            if server_id:
                await manager.broadcast(json.dumps(leave_msg), server_id=server_id)
            else:
                await manager.broadcast(json.dumps(leave_msg))

# 个人资料页面
@app.get("/profile", response_class=HTMLResponse)
async def get_profile(user: Optional[User] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>个人资料 - 简易聊天应用</title>
        <meta charset="utf-8">
        <meta http-equiv="refresh" content="0; url=/static/profile.html">
    </head>
    <body>
        <p>正在跳转到个人资料页面...</p>
    </body>
    </html>
    """

# 更新用户资料API
@app.post("/api/users/profile")
async def update_profile(
    display_name: Optional[str] = Form(None),
    email: str = Form(...),
    bio: Optional[str] = Form(None),
    avatar: Optional[UploadFile] = File(None),
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录"
        )
    
    # 检查邮箱是否已被其他用户使用
    if email != user.email:
        existing_email = db.query(User).filter(User.email == email, User.id != user.id).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该邮箱已被其他用户使用"
            )
    
    # 更新基本资料
    user.email = email
    if display_name:
        user.display_name = display_name
    if bio:
        user.bio = bio
    
    # 处理头像上传
    if avatar:
        # 确保存储目录存在
        avatar_dir = "static/images/avatars"
        os.makedirs(avatar_dir, exist_ok=True)
        
        # 生成随机文件名
        file_extension = os.path.splitext(avatar.filename)[1]
        random_string = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(8))
        filename = f"avatar_{user.id}_{random_string}{file_extension}"
        file_path = os.path.join(avatar_dir, filename)
        
        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(avatar.file, buffer)
        
        # 更新用户头像URL
        user.avatar_url = f"/static/images/avatars/{filename}"
    
    db.commit()
    
    return {
        "message": "个人资料更新成功",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "bio": user.bio,
            "avatar_url": user.avatar_url
        }
    }

# 服务器相关的Pydantic模型
class ServerCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ServerResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    icon_url: str
    created_at: datetime.datetime
    owner_id: int
    
    class Config:
        orm_mode = True

# 服务器API路由
@app.post("/api/servers", response_model=ServerResponse)
async def create_server(
    server: ServerCreate,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录"
        )
    
    # 创建新服务器
    db_server = Server(
        name=server.name,
        description=server.description,
        owner_id=user.id
    )
    
    # 添加到数据库
    db.add(db_server)
    db.commit()
    db.refresh(db_server)
    
    # 将创建者添加为服务器成员
    db_server.members.append(user)
    db.commit()
    db.refresh(db_server)
    
    # 使用text()函数包装SQL语句
    db.execute(
        text(f"UPDATE server_members SET is_admin = 1 WHERE user_id = {user.id} AND server_id = {db_server.id}")
    )
    db.commit()
    
    return db_server

@app.get("/api/servers", response_model=List[ServerResponse])
async def get_servers(
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录"
        )
    
    # 获取用户加入的所有服务器
    return user.joined_servers

@app.get("/api/servers/{server_id}", response_model=ServerResponse)
async def get_server(
    server_id: int,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录"
        )
    
    # 获取服务器详情
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到服务器"
        )
    
    # 检查用户是否是服务器成员
    if user not in server.members:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您不是该服务器的成员"
        )
    
    return server

# 获取服务器消息API
@app.get("/api/servers/{server_id}/messages")
async def get_server_messages(
    server_id: int,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录"
        )
    
    # 获取服务器详情
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到服务器"
        )
    
    # 检查用户是否是服务器成员
    if user not in server.members:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您不是该服务器的成员"
        )
    
    # 获取服务器的消息
    messages = db.query(Message).filter(Message.server_id == server_id).order_by(Message.created_at).all()
    
    # 格式化消息
    result = []
    for msg in messages:
        sender_name = msg.sender
        if msg.user_id:
            msg_user = db.query(User).filter(User.id == msg.user_id).first()
            if msg_user:
                sender_name = msg_user.username
        
        result.append({
            "id": msg.id,
            "content": msg.content,
            "sender": sender_name,
            "created_at": msg.created_at.isoformat(),
            "user_id": msg.user_id,
            "server_id": msg.server_id
        })
    
    return result 
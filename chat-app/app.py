from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request, Form, Cookie, Response, HTTPException, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import json
from typing import List, Dict, Optional
import uuid
import datetime
import shutil
import os
import random
import string

from database import get_db, Message, User

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
    
    async def connect(self, websocket: WebSocket, user_id: Optional[int] = None):
        await websocket.accept()
        self.active_connections.append(websocket)
        
        # 如果有用户ID，将连接与用户关联
        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = []
            self.user_connections[user_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, user_id: Optional[int] = None):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        
        # 如果有用户ID，从用户连接列表中移除
        if user_id and user_id in self.user_connections:
            if websocket in self.user_connections[user_id]:
                self.user_connections[user_id].remove(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
    
    async def broadcast(self, message: str):
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
            if conn in self.active_connections:
                self.active_connections.remove(conn)
                print(f"已移除断开的连接，剩余连接数: {len(self.active_connections)}")

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
@app.websocket("/ws/chat")
async def websocket_endpoint(
    websocket: WebSocket, 
    db: Session = Depends(get_db)
):
    # 获取查询参数中的会话ID
    query_params = dict(websocket.query_params)
    session_id = query_params.get("session_id")
    
    print(f"WebSocket连接请求: 会话ID = {session_id}")
    
    # 获取用户信息（如果已登录）
    user_id = None
    username = None
    
    if session_id and session_id in user_sessions:
        user_id = user_sessions[session_id]
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            username = user.username
            print(f"已认证用户: {username} (ID: {user_id})")
        else:
            print(f"找不到用户ID: {user_id}")
    else:
        print(f"无效的会话ID或未登录: {session_id}")
    
    try:
        await manager.connect(websocket, user_id)
        print(f"WebSocket连接已建立，活跃连接数: {len(manager.active_connections)}")
        
        # 发送历史消息
        messages = db.query(Message).order_by(Message.created_at).all()
        print(f"发送 {len(messages)} 条历史消息")
        for msg in messages:
            sender_name = msg.sender
            if msg.user_id:
                user = db.query(User).filter(User.id == msg.user_id).first()
                if user:
                    sender_name = user.username
            
            message_data = {
                "sender": sender_name,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
                "user_id": msg.user_id
            }
            
            try:
                await websocket.send_text(json.dumps(message_data))
            except Exception as e:
                print(f"发送历史消息失败: {e}")
                break
        
        while True:
            # 接收消息
            try:
                data = await websocket.receive_text()
                print(f"收到消息: {data[:100]}...")
                message_data = json.loads(data)
                
                # 验证消息格式
                if "content" not in message_data:
                    print("消息缺少content字段")
                    continue
                
                # 保存消息到数据库
                try:
                    db_message = Message(
                        content=message_data["content"],
                        sender=message_data.get("sender", "匿名")
                    )
                    
                    # 如果用户已登录，关联消息与用户
                    if user_id:
                        db_message.user_id = user_id
                        # 使用用户名替代临时名称
                        if username:
                            message_data["sender"] = username
                    
                    db.add(db_message)
                    db.commit()
                    print(f"消息已保存到数据库，ID: {db_message.id}")
                except Exception as db_error:
                    print(f"保存消息到数据库失败: {db_error}")
                    db.rollback()
                
                # 广播消息给所有连接的客户端
                print(f"广播消息给 {len(manager.active_connections)} 个连接")
                await manager.broadcast(json.dumps(message_data))
            except json.JSONDecodeError as json_error:
                print(f"JSON解析错误: {json_error}")
                continue
            except Exception as receive_error:
                print(f"接收消息错误: {receive_error}")
                break
    except WebSocketDisconnect:
        print(f"WebSocket断开连接: 用户ID = {user_id}")
        manager.disconnect(websocket, user_id)
        if len(manager.active_connections) > 0:
            await manager.broadcast(json.dumps({
                "sender": "系统",
                "content": "有用户断开连接"
            }))
    except Exception as e:
        print(f"WebSocket错误: {e}")
        manager.disconnect(websocket, user_id)

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
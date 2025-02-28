from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import hashlib

# 创建SQLite数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./chat.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 服务器成员关联表（多对多关系）
ServerMember = Table(
    "server_members",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("server_id", Integer, ForeignKey("servers.id"), primary_key=True),
    Column("joined_at", DateTime, default=datetime.datetime.utcnow),
    Column("is_admin", Boolean, default=False),  # 是否为服务器管理员
)

# 用户模型
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # 个人资料字段
    display_name = Column(String, nullable=True)  # 显示名称
    avatar_url = Column(String, nullable=True, default="/static/images/default_avatar.svg")  # 头像URL
    bio = Column(String, nullable=True)  # 个人简介
    
    # 关系：一个用户可以有多条消息
    messages = relationship("Message", back_populates="user")
    
    # 关系：用户创建的服务器
    owned_servers = relationship("Server", back_populates="owner")
    
    # 关系：用户加入的服务器（多对多）
    joined_servers = relationship("Server", secondary=ServerMember, back_populates="members")
    
    @staticmethod
    def hash_password(password):
        """简单的密码哈希函数"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password):
        """验证密码"""
        return self.password_hash == self.hash_password(password)

# 服务器模型
class Server(Base):
    __tablename__ = "servers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)  # 服务器名称
    description = Column(String, nullable=True)  # 服务器描述
    icon_url = Column(String, nullable=True, default="/static/images/default_server_icon.svg")  # 服务器图标
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"))  # 创建者/所有者ID
    
    # 关系：服务器所有者
    owner = relationship("User", back_populates="owned_servers")
    
    # 关系：服务器成员（多对多）
    members = relationship("User", secondary=ServerMember, back_populates="joined_servers")
    
    # 关系：服务器中的消息
    messages = relationship("Message", back_populates="server")

# 消息模型
class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String)
    sender = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=True)
    
    # 关系：一条消息属于一个用户
    user = relationship("User", back_populates="messages")
    
    # 关系：一条消息属于一个服务器
    server = relationship("Server", back_populates="messages")

# 创建表
Base.metadata.create_all(bind=engine)

# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import hashlib

# 创建SQLite数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./chat.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 用户模型
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # 关系：一个用户可以有多条消息
    messages = relationship("Message", back_populates="user")
    
    @staticmethod
    def hash_password(password):
        """简单的密码哈希函数"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password):
        """验证密码"""
        return self.password_hash == self.hash_password(password)

# 消息模型
class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String)
    sender = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # 关系：一条消息属于一个用户
    user = relationship("User", back_populates="messages")

# 创建表
Base.metadata.create_all(bind=engine)

# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 
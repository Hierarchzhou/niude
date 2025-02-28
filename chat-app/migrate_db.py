from database import Base, engine, User, Message, Server, ServerMember
import os

# 检查数据库文件是否存在
db_exists = os.path.exists("./chat.db")

# 创建所有表
Base.metadata.create_all(bind=engine)

print("数据库迁移完成！")
print(f"{'更新' if db_exists else '创建'} 了以下表:")
print("- users (用户表)")
print("- messages (消息表)")
print("- servers (服务器表)")
print("- server_members (服务器成员关联表)") 
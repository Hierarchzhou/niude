import sqlite3
import os

# 数据库文件路径
db_path = 'chat.db'

def migrate_database():
    print("开始数据库迁移...")
    
    # 检查数据库文件是否存在
    if not os.path.exists(db_path):
        print(f"错误: 找不到数据库文件 {db_path}")
        return
    
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查表中是否已存在新字段
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # 添加新字段
        if 'display_name' not in columns:
            print("添加 display_name 字段...")
            cursor.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
        
        if 'avatar_url' not in columns:
            print("添加 avatar_url 字段...")
            cursor.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT '/images/default_avatar.svg'")
        
        if 'bio' not in columns:
            print("添加 bio 字段...")
            cursor.execute("ALTER TABLE users ADD COLUMN bio TEXT")
        
        # 提交更改
        conn.commit()
        print("数据库迁移完成!")
        
    except Exception as e:
        print(f"迁移过程中出错: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database() 
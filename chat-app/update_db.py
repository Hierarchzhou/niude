import sqlite3
import os

print("开始更新数据库...")

# 检查数据库文件是否存在
db_path = "./chat.db"
print(f"检查数据库文件: {db_path}")
if not os.path.exists(db_path):
    print("数据库文件不存在，请先运行 migrate_db.py 创建数据库")
    exit(1)
else:
    print("找到数据库文件")

# 连接到数据库
print("正在连接到数据库...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
print("数据库连接成功")

try:
    # 检查messages表是否存在server_id列
    print("检查messages表结构...")
    cursor.execute("PRAGMA table_info(messages)")
    columns = cursor.fetchall()
    print(f"表结构: {columns}")
    column_names = [column[1] for column in columns]
    print(f"列名: {column_names}")
    
    if "server_id" not in column_names:
        print("正在添加 server_id 列到 messages 表...")
        cursor.execute("ALTER TABLE messages ADD COLUMN server_id INTEGER REFERENCES servers(id)")
        print("成功添加 server_id 列！")
    else:
        print("messages 表已经包含 server_id 列，无需修改")
    
    # 提交更改
    conn.commit()
    print("数据库更新完成！")
    
except Exception as e:
    print(f"更新数据库时出错: {e}")
    conn.rollback()
finally:
    conn.close()
    print("数据库连接已关闭") 
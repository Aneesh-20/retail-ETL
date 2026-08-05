import os
import shutil
import sqlite3

PROJECT_ROOT = "/Users/aneeshnaren/Documents/retail_lakehouse"
DB_PATH = os.path.join(PROJECT_ROOT, "retail_fallback.db")
LAKEHOUSE_PATH = os.path.join(PROJECT_ROOT, "lakehouse")

def cleanup():
    print("--- Initiating Complete Platform Data Cleanup ---")
    
    # 1. Clear database tables
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Fetch all user tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            print("Truncating database tables:")
            for table in tables:
                print(f"  - Clearing table: {table}")
                cursor.execute(f"DELETE FROM {table}")
                
            conn.commit()
            conn.close()
            print("Successfully truncated all fallback database tables.")
        except Exception as e:
            print(f"Failed to clear database: {e}")
    else:
        print("Fallback database file does not exist.")

    # 2. Clear Spark Delta/Parquet files
    if os.path.exists(LAKEHOUSE_PATH):
        print(f"Removing raw files in Lakehouse directory: {LAKEHOUSE_PATH}")
        try:
            # Delete directories
            shutil.rmtree(LAKEHOUSE_PATH)
            # Recreate base folders so Spark is happy
            os.makedirs(os.path.join(LAKEHOUSE_PATH, "bronze"), exist_ok=True)
            os.makedirs(os.path.join(LAKEHOUSE_PATH, "silver"), exist_ok=True)
            print("Successfully cleared all raw Lakehouse storage folders.")
        except Exception as e:
            print(f"Failed to clear Lakehouse directories: {e}")
            
    print("Cleanup operation completed successfully!")

if __name__ == "__main__":
    cleanup()

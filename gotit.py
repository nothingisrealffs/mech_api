import sqlite3
import csv
import os

def export_tables_to_txt(db_path, delimiter='|'):
    """
    Export first 10 rows of each table (excluding staging_ tables) to a delimited text file.
    
    Args:
        db_path: Path to the SQLite database file
        delimiter: Delimiter to use in output file (default: '|')
    """
    # Generate output filename in same directory as database
    db_dir = os.path.dirname(db_path) or '.'
    db_name = os.path.splitext(os.path.basename(db_path))[0]
    output_file = os.path.join(db_dir, f'{db_name}_export.txt')
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    # Filter out staging tables
    tables = [t for t in tables if 'staging_' not in t.lower()]
    
    print(f"Found {len(tables)} non-staging tables")
    
    # Write to output file
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=delimiter)
        
        for table in tables:
            print(f"Processing table: {table}")
            
            # Write table header
            writer.writerow([f"=== TABLE: {table} ==="])
            
            # Get column names
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]
            writer.writerow(columns)
            
            # Get first 10 rows
            cursor.execute(f"SELECT * FROM {table} LIMIT 10")
            rows = cursor.fetchall()
            
            # Write rows
            for row in rows:
                writer.writerow(row)
            
            # Add blank line between tables
            writer.writerow([])
            
            print(f"  Exported {len(rows)} rows")
    
    conn.close()
    print(f"\nExport complete! Output saved to: {output_file}")

# Usage
if __name__ == "__main__":
    # Replace with your database path
    db_path = "mech_data_test.db"
    
    # You can change the delimiter if needed (e.g., ',' for CSV, '\t' for tab)
    export_tables_to_txt(db_path, delimiter='|')
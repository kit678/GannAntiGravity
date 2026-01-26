
import os

token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzY4NDE0MzQzLCJpYXQiOjE3NjgzMjc5NDMsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA5MzgxMTg5In0.q3O1eamgNyXBUujr57XYeyo2eaa_OJP4so_jmZb-BLof67juUIBrurTMp9GHUVW1tmlkmujqvaoInh9QixYq3w"
file_path = "dhan_auth.py"

try:
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Simple regex replacement or string replace
    import re
    # Replace ACCESS_TOKEN = "..."
    new_content = re.sub(r'ACCESS_TOKEN = ".*?"', f'ACCESS_TOKEN = "{token}"', content)
    
    with open(file_path, 'w') as f:
        f.write(new_content)
    print("dhan_auth.py updated.")
except Exception as e:
    print(f"Error: {e}")

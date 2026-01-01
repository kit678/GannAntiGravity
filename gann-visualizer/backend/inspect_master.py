import pandas as pd
import io
import requests

url = "https://images.dhan.co/api-data/api-scrip-master.csv"
print("Downloading CSV header...")
# Read only first few bytes/lines to avoid large download for peek
r = requests.get(url, stream=True)
chunk = next(r.iter_content(chunk_size=4096)).decode('utf-8')
print("--- HEADER ---")
print(chunk.split('\n')[0])
print("--- FIRST FEW ROWS ---")
for i in range(1, 5):
    print(chunk.split('\n')[i])

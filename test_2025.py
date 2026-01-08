
import requests
import json

# Use the NEW token
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzY3ODYxNTY2LCJpYXQiOjE3Njc3NzUxNjYsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA5MzgxMTg5In0.4kSyS5EBE00ul3ZEpOjXLrM6oo8VcTLjM-_u8cqE84U4wjh6R9x36UzVFVE3e11C1MVKrWlGLFs0Jj4Ujn2AKw"

URL = "https://api.dhan.co/v2/charts/intraday"

payload = {
    'securityId': '13', 
    'exchangeSegment': 'IDX_I', 
    'instrument': 'INDEX', 
    'interval': '1', 
    'fromDate': '2025-12-20 09:15:00', 
    'toDate': '2025-12-24 15:30:00'
}

headers = {
    "access-token": ACCESS_TOKEN,
    "client-id": "1109381189",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

try:
    response = requests.post(URL, headers=headers, json=payload)
    print(f"Status: {response.status_code}")
    data = response.json()
    
    if "data" in data and data["data"]:
        print(f"Success! Bars: {len(data['data'].get('close', []))}")
        # Print first timestamp to verify year
        ts = data['data']['start_time'][0]
        print(f"First Bar Time: {ts}")
    else:
        print("No Data Found")
        print(data)

except Exception as e:
    print(f"Error: {e}")

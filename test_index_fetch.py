import requests
import json

ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzY3ODYxNTY2LCJpYXQiOjE3Njc3NzUxNjYsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA5MzgxMTg5In0.4kSyS5EBE00ul3ZEpOjXLrM6oo8VcTLjM-_u8cqE84U4wjh6R9x36UzVFVE3e11C1MVKrWlGLFs0Jj4Ujn2AKw"
CLIENT_ID = "1109381189"

headers = {
    "access-token": ACCESS_TOKEN,
    "client-id": CLIENT_ID,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

url = "https://api.dhan.co/v2/charts/intraday" 

# Try 3: IDX_I
payload = {
    "exchangeSegment": "IDX_I", 
    "instrument": "INDEX",
    "securityId": "13", 
    "interval": "1",
    "fromDate": "2024-12-19 09:15:00",
    "toDate": "2024-12-20 15:30:00"
}

print(f"Testing {url} with {payload['exchangeSegment']}...")
try:
    response = requests.post(url, headers=headers, json=payload)
    print(f"Status: {response.status_code}")
    print(response.text[:300])
except Exception as e:
    print(e)

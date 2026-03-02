import codecs
with codecs.open(r'c:\Dev\GannTesting\gann-visualizer\backend\logs\backend_session_20260301_152959.log', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.readlines()
with open('debug.txt', 'w', encoding='utf-8') as f:
    for line in text:
        if 'Step-by-Step' in line or 'fetch_candles' in line or 'YFinance' in line or 'Age days' in line or 'Auto-adjusting' in line or 'Requested data' in line:
            f.write(line.strip() + '\n')

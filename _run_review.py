import urllib.request, json, time, sys, http.cookiejar

BASE = 'http://127.0.0.1:2708'
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def post(path, body=None):
    d = json.dumps(body or {}).encode()
    req = urllib.request.Request(BASE+path, data=d, headers={'Content-Type':'application/json'})
    resp = opener.open(req, timeout=10)
    return json.loads(resp.read().decode())

def get(path):
    resp = opener.open(urllib.request.Request(BASE+path), timeout=10)
    return json.loads(resp.read().decode())

# Login
post('/admin/api/login', {'password': ''})
print('Login OK')

# Start review
r = post('/admin/api/review/start')
print('Review started, taskId:', r.get('taskId'), 'status:', r.get('status'))

# Poll for 15 minutes (23 DXF files with zhipu API)
for i in range(450):
    time.sleep(2)
    p = get('/api/review/progress')
    issues = p.get('issues', 0)
    ready = p.get('ready', False)
    if i % 15 == 0:
        print(f'  [{i*2}s] issues={issues}, ready={ready}')
    if ready:
        print(f'DONE! issues={issues}, conflicts={p.get("conflicts", 0)}')
        
        s = get('/api/stats')
        print('Stats:', json.dumps(s, ensure_ascii=False, indent=2)[:500])
        
        iss = get('/api/issues')
        print('Issues total:', iss.get('total'))
        if iss.get('items'):
            for item in iss['items'][:5]:
                print(f'  - [{item.get("severity")}] {item.get("discipline")}: {item.get("title",item.get("finding",""))[:80]}')
        sys.exit(0)

print('TIMEOUT after 15 min')

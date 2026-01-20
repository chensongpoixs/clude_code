import http.client
import json

conn = http.client.HTTPSConnection("google.serper.dev")
payload = json.dumps({
  "q": "学习Transformer模型，有哪些重要的论文？",
  "gl": "cn",
  "hl": "zh-cn"
})
headers = {
  'X-API-KEY': 'a835b5beb674f8a41746500b01a36e64501f097f',
  'Content-Type': 'application/json'
}
conn.request("POST", "/images", payload, headers)
res = conn.getresponse()
data = res.read()
print(data.decode("utf-8"))
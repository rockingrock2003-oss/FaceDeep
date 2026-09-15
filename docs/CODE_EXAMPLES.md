# FaceDeep API Code Examples

## Python - Enroll a Face

```python
import httpx

API_KEY = "fd_your_api_key_here"
BASE_URL = "https://api.facedeep.com/api/v2"

# Enroll a face
with open("photo.jpg", "rb") as f:
    response = httpx.post(
        f"{BASE_URL}/face/enroll",
        headers={"X-API-Key": API_KEY},
        files={"file": ("photo.jpg", f, "image/jpeg")},
        data={"person_id": "john_doe"},
    )
print(response.json())
```

## Python - Recognize a Face

```python
import httpx

API_KEY = "fd_your_api_key_here"
BASE_URL = "https://api.facedeep.com/api/v2"

with open("photo.jpg", "rb") as f:
    response = httpx.post(
        f"{BASE_URL}/face/recognize",
        headers={"X-API-Key": API_KEY},
        files={"file": ("photo.jpg", f, "image/jpeg")},
    )
result = response.json()
if result["status"] == "found":
    print(f"Recognized: {result['person_id']} (confidence: {result['confidence']})")
else:
    print("No match found")
```

## Python - Bulk Import from URLs

```python
import httpx

API_KEY = "fd_your_api_key_here"
BASE_URL = "https://api.facedeep.com/api/v2"

response = httpx.post(
    f"{BASE_URL}/face/bulk-import",
    headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
    json={
        "person_id": "jane_smith",
        "image_urls": [
            "https://example.com/photo1.jpg",
            "https://example.com/photo2.jpg",
            "https://example.com/photo3.jpg",
        ],
    },
)
job = response.json()
print(f"Import started: {job['job_id']}")

# Check status
status = httpx.get(
    f"{BASE_URL}/face/import-status/{job['job_id']}",
    headers={"X-API-Key": API_KEY},
)
print(status.json())
```

## Python - Webhook Setup

```python
import httpx

API_KEY = "fd_your_api_key_here"
BASE_URL = "https://api.facedeep.com/api/v2"

# Create webhook
response = httpx.post(
    f"{BASE_URL}/webhooks",
    headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
    json={
        "url": "https://your-server.com/webhook",
        "events": ["bulk-import.completed", "recognition.event"],
    },
)
webhook = response.json()
print(f"Webhook created: {webhook['id']}")
print(f"Secret: {webhook['secret']}")
```

## Node.js - Recognize a Face

```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

const API_KEY = 'fd_your_api_key_here';
const BASE_URL = 'https://api.facedeep.com/api/v2';

const form = new FormData();
form.append('file', fs.createReadStream('photo.jpg'));

const response = await axios.post(`${BASE_URL}/face/recognize`, form, {
  headers: {
    'X-API-Key': API_KEY,
    ...form.getHeaders(),
  },
});

console.log(response.data);
```

## cURL - List Persons

```bash
curl -X GET "https://api.facedeep.com/api/v2/face/persons?limit=50&offset=0" \
  -H "X-API-Key: fd_your_api_key_here"
```

## cURL - Check Usage

```bash
curl -X GET "https://api.facedeep.com/api/v2/billing/realtime-usage" \
  -H "X-API-Key: fd_your_api_key_here"
```

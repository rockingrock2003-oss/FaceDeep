'use client'

import { useState } from 'react'
import { Copy, Check, ExternalLink } from 'lucide-react'

type Language = 'curl' | 'python' | 'javascript' | 'java' | 'csharp' | 'go' | 'ruby' | 'php' | 'swift'
type Endpoint = 'enroll' | 'recognize' | 'ismatch' | 'delete' | 'bulk-enroll' | 'list-persons'

const LANGUAGES: { id: Language; label: string; icon: string }[] = [
  { id: 'curl', label: 'cURL', icon: '>' },
  { id: 'python', label: 'Python', icon: '' },
  { id: 'javascript', label: 'JavaScript', icon: 'JS' },
  { id: 'java', label: 'Java', icon: 'J' },
  { id: 'csharp', label: 'C#', icon: 'C#' },
  { id: 'go', label: 'Go', icon: 'Go' },
  { id: 'ruby', label: 'Ruby', icon: 'RB' },
  { id: 'php', label: 'PHP', icon: '?' },
  { id: 'swift', label: 'Swift', icon: 'S' },
]

const ENDPOINTS: { id: Endpoint; method: string; path: string; label: string; description: string }[] = [
  { id: 'enroll', method: 'POST', path: '/api/v2/face/enroll', label: 'Enroll Face', description: 'Add a new face to your database' },
  { id: 'recognize', method: 'POST', path: '/api/v2/face/recognize', label: 'Recognize Face', description: 'Identify a face against enrolled faces' },
  { id: 'ismatch', method: 'POST', path: '/api/v2/face/ismatch', label: 'Is Match', description: 'Check if a face matches any enrolled face' },
  { id: 'delete', method: 'DELETE', path: '/api/v2/face/delete', label: 'Delete Face', description: 'Remove all embeddings for a person_id' },
  { id: 'bulk-enroll', method: 'POST', path: '/api/v2/face/bulk-enroll', label: 'Bulk Enroll', description: 'Enroll multiple face images at once' },
  { id: 'list-persons', method: 'GET', path: '/api/v2/face/persons', label: 'List Persons', description: 'List all enrolled person IDs' },
]

const BASE = 'https://facedeep.me'

function codeExamples(lang: Language): Record<Endpoint, string> {
  const K = 'YOUR_API_KEY'
  const P = 'employee_001'

  return {
    enroll: {
      curl: `curl -X POST ${BASE}/api/v2/face/enroll \\
  -H "X-API-Key: ${K}" \\
  -F "file=@photo.jpg" \\
  -F "person_id=${P}"`,

      python: `import requests

url = "${BASE}/api/v2/face/enroll"
headers = {"X-API-Key": "${K}"}

with open("photo.jpg", "rb") as f:
    response = requests.post(
        url,
        headers=headers,
        files={"file": f},
        data={"person_id": "${P}"}
    )

print(response.json())`,

      javascript: `const FormData = require("form-data");
const fs = require("fs");
const axios = require("axios");

const form = new FormData();
form.append("file", fs.createReadStream("photo.jpg"));
form.append("person_id", "${P}");

const response = await axios.post(
  "${BASE}/api/v2/face/enroll",
  form,
  {
    headers: {
      "X-API-Key": "${K}",
      ...form.getHeaders(),
    },
  }
);

console.log(response.data);`,

      java: `import java.net.http.*;
import java.nio.file.*;

HttpClient client = HttpClient.newHttpClient();
String apiKey = "${K}";

MultipartBody.Builder builder = new MultipartBody.Builder()
    .setType(MultipartBody.FORM)
    .addFormDataPart("person_id", "${P}")
    .addFormDataPart("file", "photo.jpg",
        RequestBody.create(Files.readAllBytes(Path.of("photo.jpg"))));

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("${BASE}/api/v2/face/enroll"))
    .header("X-API-Key", apiKey)
    .POST(HttpRequest.BodyPublishers.ofByteArray(builder.build().toString().getBytes()))
    .build();

HttpResponse<String> response = client.send(request,
    HttpResponse.BodyHandlers.ofString());
System.out.println(response.body());`,

      csharp: `using System.Net.Http.Headers;

var client = new HttpClient();
client.DefaultRequestHeaders.Add("X-API-Key", "${K}");

var form = new MultipartFormDataContent();
form.Add(new ByteArrayContent(File.ReadAllBytes("photo.jpg")), "file", "photo.jpg");
form.Add(new StringContent("${P}"), "person_id");

var response = await client.PostAsync(
    "${BASE}/api/v2/face/enroll", form);
var result = await response.Content.ReadAsStringAsync();
Console.WriteLine(result);`,

      go: `package main

import (
    "bytes"
    "fmt"
    "mime/multipart"
    "net/http"
    "os"
)

func main() {
    file, _ := os.Open("photo.jpg")
    defer file.Close()

    body := &bytes.Buffer{}
    writer := multipart.NewWriter(body)
    part, _ := writer.CreateFormFile("file", "photo.jpg")
    io.Copy(part, file)
    writer.WriteField("person_id", "${P}")
    writer.Close()

    req, _ := http.NewRequest("POST",
        "${BASE}/api/v2/face/enroll", body)
    req.Header.Set("X-API-Key", "${K}")
    req.Header.Set("Content-Type", writer.FormDataContentType())

    resp, _ := http.DefaultClient.Do(req)
    defer resp.Body.Close()
    fmt.Println(resp.Status)
}`,

      ruby: `require "net/http"
require "json"
require "mime/types"

uri = URI("${BASE}/api/v2/face/enroll")
request = Net::HTTP::Post.new(uri)
request["X-API-Key"] = "${K}"

form_data = Net::HTTP::FormData::Form.new
form_data.add_field("person_id", "${P}")
file_part = Net::HTTP::FormData::File.new("photo.jpg")
form_data.add_field("file", file_part, content_type: "image/jpeg")

request.body = form_data.read
request.content_type = form_data.content_type

response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) do |http|
    http.request(request)
end

puts response.body`,

      php: `<?php

$ch = curl_init("${BASE}/api/v2/face/enroll");
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    "X-API-Key: ${K}"
]);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, [
    "file" => new CURLFile("photo.jpg", "image/jpeg"),
    "person_id" => "${P}"
]);

$response = curl_exec($ch);
curl_close($ch);
echo $response;`,

      swift: `import Foundation

let url = URL(string: "${BASE}/api/v2/face/enroll")!
var request = URLRequest(url: url)
request.httpMethod = "POST"
request.addValue("${K}", forHTTPHeaderField: "X-API-Key")

let boundary = UUID().uuidString
let imageData = try! Data(contentsOf: URL(fileURLWithPath: "photo.jpg"))

var body = Data()
body.append("--\(boundary)\r\n".data(using: .utf8)!)
body.append("Content-Disposition: form-data; name=\"person_id\"\r\n\r\n".data(using: .utf8)!)
body.append("${P}\r\n".data(using: .utf8)!)
body.append("--\(boundary)\r\n".data(using: .utf8)!)
body.append("Content-Disposition: form-data; name=\"file\"; filename=\"photo.jpg\"\r\n".data(using: .utf8)!)
body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
body.append(imageData)
body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)

request.httpBody = body
request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

URLSession.shared.dataTask(with: request) { data, response, error in
    print(String(data: data!, encoding: .utf8)!)
}.resume()`,
    },

    recognize: {
      curl: `curl -X POST ${BASE}/api/v2/face/recognize \\
  -H "X-API-Key: ${K}" \\
  -F "file=@photo.jpg"`,

      python: `import requests

url = "${BASE}/api/v2/face/recognize"
headers = {"X-API-Key": "${K}"}

with open("photo.jpg", "rb") as f:
    response = requests.post(url, headers=headers, files={"file": f})

print(response.json())
# {"status":"found","person_id":"${P}","confidence":0.8543,...}`,

      javascript: `const FormData = require("form-data");
const fs = require("fs");
const axios = require("axios");

const form = new FormData();
form.append("file", fs.createReadStream("photo.jpg"));

const { data } = await axios.post(
  "${BASE}/api/v2/face/recognize",
  form,
  { headers: { "X-API-Key": "${K}", ...form.getHeaders() } }
);

console.log(data.person_id, data.confidence);`,

      java: `HttpClient client = HttpClient.newHttpClient();
// Build multipart with file only, same as enroll but no person_id
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("${BASE}/api/v2/face/recognize"))
    .header("X-API-Key", "${K}")
    .POST(/* multipart body with file */)
    .build();

HttpResponse<String> resp = client.send(request,
    HttpResponse.BodyHandlers.ofString());
System.out.println(resp.body());`,

      csharp: `var client = new HttpClient();
client.DefaultRequestHeaders.Add("X-API-Key", "${K}");

var form = new MultipartFormDataContent();
form.Add(new ByteArrayContent(File.ReadAllBytes("photo.jpg")), "file", "photo.jpg");

var resp = await client.PostAsync("${BASE}/api/v2/face/recognize", form);
Console.WriteLine(await resp.Content.ReadAsStringAsync());`,

      go: `// Same multipart setup as enroll, but only "file" field
req, _ := http.NewRequest("POST",
    "${BASE}/api/v2/face/recognize", body)
req.Header.Set("X-API-Key", "${K}")
req.Header.Set("Content-Type", writer.FormDataContentType())
resp, _ := http.DefaultClient.Do(req)`,

      ruby: `# Same pattern as enroll, omit person_id field
request["X-API-Key"] = "${K}"
# ...
response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) { |http|
    http.request(request)
}`,

      php: `curl_setopt($ch, CURLOPT_URL, "${BASE}/api/v2/face/recognize");
curl_setopt($ch, CURLOPT_POSTFIELDS, [
    "file" => new CURLFile("photo.jpg", "image/jpeg")
]);`,

      swift: `// Same multipart as enroll, omit person_id field
request.addValue("${K}", forHTTPHeaderField: "X-API-Key")
// ...`,
    },

    ismatch: {
      curl: `curl -X POST ${BASE}/api/v2/face/ismatch \\
  -H "X-API-Key: ${K}" \\
  -F "file=@photo.jpg"`,

      python: `import requests

with open("photo.jpg", "rb") as f:
    response = requests.post(
        "${BASE}/api/v2/face/ismatch",
        headers={"X-API-Key": "${K}"},
        files={"file": f}
    )

data = response.json()
print(f"Match: {data['is_match']}, Confidence: {data.get('confidence')}")`,

      javascript: `const form = new FormData();
form.append("file", fs.createReadStream("photo.jpg"));

const { data } = await axios.post(
  "${BASE}/api/v2/face/ismatch",
  form,
  { headers: { "X-API-Key": "${K}", ...form.getHeaders() } }
);

console.log(data.is_match, data.confidence);`,

      java: `// Same as recognize - POST multipart with file only
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("${BASE}/api/v2/face/ismatch"))
    .header("X-API-Key", "${K}")
    .POST(/* multipart body with file */)
    .build();`,

      csharp: `// Same as recognize - POST multipart with file only
var resp = await client.PostAsync("${BASE}/api/v2/face/ismatch", form);`,

      go: `req, _ := http.NewRequest("POST",
    "${BASE}/api/v2/face/ismatch", body)
req.Header.Set("X-API-Key", "${K}")`,

      ruby: `# Same as recognize
uri = URI("${BASE}/api/v2/face/ismatch")`,

      php: `curl_setopt($ch, CURLOPT_URL, "${BASE}/api/v2/face/ismatch");
curl_setopt($ch, CURLOPT_POSTFIELDS, [
    "file" => new CURLFile("photo.jpg", "image/jpeg")
]);`,

      swift: `// Same as recognize - POST multipart with file only
request.url = URL(string: "${BASE}/api/v2/face/ismatch")!`,
    },

    delete: {
      curl: `curl -X DELETE ${BASE}/api/v2/face/delete \\
  -H "X-API-Key: ${K}" \\
  -H "Content-Type: application/json" \\
  -d '{"person_id": "${P}"}'`,

      python: `import requests

response = requests.delete(
    "${BASE}/api/v2/face/delete",
    headers={"X-API-Key": "${K}", "Content-Type": "application/json"},
    json={"person_id": "${P}"}
)

print(response.json())
# {"status":"success","deleted_count":3,...}`,

      javascript: `const { data } = await axios.delete(
  "${BASE}/api/v2/face/delete",
  {
    headers: { "X-API-Key": "${K}" },
    data: { person_id: "${P}" },
  }
);

console.log(data.deleted_count);`,

      java: `String json = "{\"person_id\": \"${P}\"}";
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("${BASE}/api/v2/face/delete"))
    .header("X-API-Key", "${K}")
    .header("Content-Type", "application/json")
    .DELETE()
    .build();

HttpResponse<String> resp = client.send(request,
    HttpResponse.BodyHandlers.ofString());`,

      csharp: `var request = new HttpRequestMessage {
    Method = HttpMethod.Delete,
    RequestUri = new Uri("${BASE}/api/v2/face/delete"),
    Headers = { { "X-API-Key", "${K}" } },
    Content = new StringContent(
        "{\"person_id\": \"${P}\"}",
        Encoding.UTF8, "application/json")
};

var resp = await client.SendAsync(request);
Console.WriteLine(await resp.Content.ReadAsStringAsync());`,

      go: `body, _ := json.Marshal(map[string]string{
    "person_id": "${P}",
})

req, _ := http.NewRequest("DELETE",
    "${BASE}/api/v2/face/delete",
    bytes.NewBuffer(body))
req.Header.Set("X-API-Key", "${K}")
req.Header.Set("Content-Type", "application/json")

resp, _ := http.DefaultClient.Do(req)`,

      ruby: `uri = URI("${BASE}/api/v2/face/delete")
request = Net::HTTP::Delete.new(uri)
request["X-API-Key"] = "${K}"
request["Content-Type"] = "application/json"
request.body = { person_id: "${P}" }.to_json

response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) { |http|
    http.request(request)
}`,

      php: `$data = json_encode(["person_id" => "${P}"]);
curl_setopt($ch, CURLOPT_URL, "${BASE}/api/v2/face/delete");
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "DELETE");
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    "X-API-Key: ${K}",
    "Content-Type: application/json"
]);
curl_setopt($ch, CURLOPT_POSTFIELDS, $data);`,

      swift: `var request = URLRequest(url: URL(string: "${BASE}/api/v2/face/delete")!)
request.httpMethod = "DELETE"
request.addValue("${K}", forHTTPHeaderField: "X-API-Key")
request.addValue("application/json", forHTTPHeaderField: "Content-Type")
request.httpBody = try! JSONEncoder().encode(["person_id": "${P}"])`,
    },

    'bulk-enroll': {
      curl: `curl -X POST ${BASE}/api/v2/face/bulk-enroll \\
  -H "X-API-Key: ${K}" \\
  -F "files=@photo1.jpg" \\
  -F "files=@photo2.jpg" \\
  -F "files=@photo3.jpg" \\
  -F "person_id=${P}"`,

      python: `import requests

url = "${BASE}/api/v2/face/bulk-enroll"
headers = {"X-API-Key": "${K}"}

files = [
    ("files", open("photo1.jpg", "rb")),
    ("files", open("photo2.jpg", "rb")),
    ("files", open("photo3.jpg", "rb")),
]

response = requests.post(
    url, headers=headers, files=files,
    data={"person_id": "${P}"}
)

data = response.json()
print(f"Success: {data['success']}, Failed: {data['failed']}")`,

      javascript: `const form = new FormData();
form.append("files", fs.createReadStream("photo1.jpg"));
form.append("files", fs.createReadStream("photo2.jpg"));
form.append("files", fs.createReadStream("photo3.jpg"));
form.append("person_id", "${P}");

const { data } = await axios.post(
  "${BASE}/api/v2/face/bulk-enroll",
  form,
  { headers: { "X-API-Key": "${K}", ...form.getHeaders() } }
);

console.log(\`Enrolled \${data.success} faces\`);`,

      java: `// Build multipart with multiple "files" parts + "person_id"
MultipartBody.Builder builder = new MultipartBody.Builder()
    .setType(MultipartBody.FORM)
    .addFormDataPart("person_id", "${P}")
    .addFormDataPart("files", "photo1.jpg",
        RequestBody.create(Files.readAllBytes(Path.of("photo1.jpg"))))
    .addFormDataPart("files", "photo2.jpg",
        RequestBody.create(Files.readAllBytes(Path.of("photo2.jpg"))));

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("${BASE}/api/v2/face/bulk-enroll"))
    .header("X-API-Key", "${K}")
    .POST(HttpRequest.BodyPublishers.ofByteArray(
        builder.build().toString().getBytes()))
    .build();`,

      csharp: `var form = new MultipartFormDataContent();
form.Add(new StringContent("${P}"), "person_id");
form.Add(new ByteArrayContent(File.ReadAllBytes("photo1.jpg")), "files", "photo1.jpg");
form.Add(new ByteArrayContent(File.ReadAllBytes("photo2.jpg")), "files", "photo2.jpg");

var resp = await client.PostAsync("${BASE}/api/v2/face/bulk-enroll", form);`,

      go: `writer.WriteField("person_id", "${P}")
part1, _ := writer.CreateFormFile("files", "photo1.jpg")
io.Copy(part1, file1)
part2, _ := writer.CreateFormFile("files", "photo2.jpg")
io.Copy(part2, file2)
writer.Close()

req, _ := http.NewRequest("POST",
    "${BASE}/api/v2/face/bulk-enroll", body)
req.Header.Set("X-API-Key", "${K}")`,

      ruby: `form_data = Net::HTTP::FormData::Form.new
form_data.add_field("person_id", "${P}")
form_data.add_field("files",
    Net::HTTP::FormData::File.new("photo1.jpg"))
form_data.add_field("files",
    Net::HTTP::FormData::File.new("photo2.jpg"))

request.body = form_data.read
request.content_type = form_data.content_type`,

      php: `curl_setopt($ch, CURLOPT_POSTFIELDS, [
    "person_id" => "${P}",
    "files[0]" => new CURLFile("photo1.jpg", "image/jpeg"),
    "files[1]" => new CURLFile("photo2.jpg", "image/jpeg"),
]);`,

      swift: `body.append("--\(boundary)\\r\\n".data(using: .utf8)!)
body.append("Content-Disposition: form-data; name=\\"person_id\\"\\r\\n\\r\\n".data(using: .utf8)!)
body.append("${P}\\r\\n".data(using: .utf8)!)
// Repeat file parts for each image...`,
    },

    'list-persons': {
      curl: `curl -X GET "${BASE}/api/v2/face/persons?limit=100&offset=0" \\
  -H "X-API-Key: ${K}"`,

      python: `import requests

response = requests.get(
    "${BASE}/api/v2/face/persons",
    headers={"X-API-Key": "${K}"},
    params={"limit": 100, "offset": 0}
)

data = response.json()
for person in data["persons"]:
    print(f"{person['person_id']}: {person['face_count']} faces")`,

      javascript: `const { data } = await axios.get(
  "${BASE}/api/v2/face/persons",
  {
    headers: { "X-API-Key": "${K}" },
    params: { limit: 100, offset: 0 },
  }
);

data.persons.forEach(p =>
  console.log(\`\${p.person_id}: \${p.face_count} faces\`)
);`,

      java: `HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("${BASE}/api/v2/face/persons?limit=100&offset=0"))
    .header("X-API-Key", "${K}")
    .GET()
    .build();

HttpResponse<String> resp = client.send(request,
    HttpResponse.BodyHandlers.ofString());`,

      csharp: `var resp = await client.GetAsync(
    "${BASE}/api/v2/face/persons?limit=100&offset=0");
Console.WriteLine(await resp.Content.ReadAsStringAsync());`,

      go: `req, _ := http.NewRequest("GET",
    "${BASE}/api/v2/face/persons?limit=100&offset=0", nil)
req.Header.Set("X-API-Key", "${K}")

resp, _ := http.DefaultClient.Do(req)`,

      ruby: `uri = URI("${BASE}/api/v2/face/persons?limit=100&offset=0")
request = Net::HTTP::Get.new(uri)
request["X-API-Key"] = "${K}"

response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true) { |http|
    http.request(request)
}`,

      php: `curl_setopt($ch, CURLOPT_URL,
    "${BASE}/api/v2/face/persons?limit=100&offset=0");
curl_setopt($ch, CURLOPT_HTTPHEADER, ["X-API-Key: ${K}"]);
$response = curl_exec($ch);`,

      swift: `var request = URLRequest(
    url: URL(string: "${BASE}/api/v2/face/persons?limit=100&offset=0")!)
request.addValue("${K}", forHTTPHeaderField: "X-API-Key")

URLSession.shared.dataTask(with: request) { data, _, _ in
    print(String(data: data!, encoding: .utf8)!)
}.resume()`,
    },
  }
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
    >
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied!' : 'Copy'}
    </button>
  )
}

export default function ApiDocsPage() {
  const [selectedLang, setSelectedLang] = useState<Language>('curl')
  const [selectedEndpoint, setSelectedEndpoint] = useState<Endpoint>('enroll')
  const examples = codeExamples(selectedLang)

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">API Reference</h1>
        <a
          href="http://localhost:8000/docs"
          target="_blank"
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
        >
          <ExternalLink className="w-4 h-4" />
          Swagger UI
        </a>
      </div>

      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h2 className="text-lg font-semibold mb-2">Authentication</h2>
        <p className="text-sm text-gray-600 mb-3">
          All Face API endpoints accept <code className="bg-gray-100 px-1.5 py-0.5 rounded">X-API-Key</code> header.
          Get your API key from the <a href="/api-keys" className="text-blue-600 underline">API Keys</a> page.
        </p>
        <div className="bg-gray-900 text-green-400 p-3 rounded-lg text-sm font-mono">
          X-API-Key: fd_your_api_key_here
        </div>
      </div>

      <div className="mb-6">
        <h2 className="text-sm font-medium text-gray-700 mb-3">Select Language</h2>
        <div className="flex flex-wrap gap-2">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.id}
              onClick={() => setSelectedLang(lang.id)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                selectedLang === lang.id
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {lang.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-1">
          <div className="bg-white rounded-lg shadow">
            <div className="p-4 border-b">
              <h2 className="font-semibold text-sm">Endpoints</h2>
            </div>
            <div className="divide-y">
              {ENDPOINTS.map((ep) => (
                <button
                  key={ep.id}
                  onClick={() => setSelectedEndpoint(ep.id)}
                  className={`w-full p-4 text-left hover:bg-gray-50 transition-colors ${
                    selectedEndpoint === ep.id ? 'bg-blue-50 border-l-2 border-blue-600' : ''
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                      ep.method === 'DELETE' ? 'bg-red-100 text-red-700' :
                      ep.method === 'GET' ? 'bg-green-100 text-green-700' :
                      'bg-blue-100 text-blue-700'
                    }`}>
                      {ep.method}
                    </span>
                    <span className="text-xs text-gray-500 font-mono">{ep.path}</span>
                  </div>
                  <div className="font-medium text-sm">{ep.label}</div>
                  <div className="text-xs text-gray-400 mt-0.5">{ep.description}</div>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="lg:col-span-3">
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b">
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold px-2 py-1 rounded ${
                  ENDPOINTS.find(e => e.id === selectedEndpoint)?.method === 'DELETE' ? 'bg-red-100 text-red-700' :
                  ENDPOINTS.find(e => e.id === selectedEndpoint)?.method === 'GET' ? 'bg-green-100 text-green-700' :
                  'bg-blue-100 text-blue-700'
                }`}>
                  {ENDPOINTS.find(e => e.id === selectedEndpoint)?.method}
                </span>
                <span className="font-mono text-sm">{ENDPOINTS.find(e => e.id === selectedEndpoint)?.path}</span>
              </div>
              <CopyButton text={examples[selectedEndpoint]} />
            </div>
            <pre className="p-4 text-sm text-gray-800 overflow-x-auto bg-gray-900 text-green-400 font-mono leading-relaxed">
              {examples[selectedEndpoint]}
            </pre>
          </div>
        </div>
      </div>
    </div>
  )
}

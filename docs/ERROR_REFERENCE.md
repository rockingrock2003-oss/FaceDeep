# FaceDeep API Error Reference

## Authentication Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `auth/invalid-credentials` | 401 | Username or password is incorrect | Verify your credentials |
| `auth/email-not-verified` | 403 | Email address has not been verified | Check your inbox for verification email |
| `auth/account-deactivated` | 403 | Account has been deactivated | Contact support |
| `auth/token-expired` | 401 | JWT token has expired | Generate a new token via login |
| `auth/invalid-api-key` | 401 | API key is invalid or missing | Check your X-API-Key header |

## Rate Limiting Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `rate_limit/minute-exceeded` | 429 | Requests per minute limit exceeded | Wait for the minute window to reset |
| `rate_limit/day-exceeded` | 429 | Daily request limit exceeded | Upgrade your plan or wait for daily reset |
| `rate_limit/plan-expired` | 429 | Plan has expired | Renew or upgrade your plan |

## Face Recognition Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `face/invalid-image` | 400 | Uploaded file is not a valid image | Upload a valid JPEG, PNG, WebP, or BMP image |
| `face/image-too-large` | 413 | Image exceeds 10MB limit | Compress or resize the image |
| `face/no-face-detected` | 422 | No face found in the image | Ensure the image contains a clear face |
| `face/low-quality` | 422 | Face quality is too low for processing | Use a higher quality image |
| `face/person-not-found` | 404 | The specified person_id does not exist | Check the person_id or enroll the face first |
| `face/liveness-failed` | 200 | Liveness check failed (possible spoofing) | Use a live photo, not a screenshot or print |
| `face/recognition-failed` | 200 | No matching face found above threshold | Enroll the face first or lower the threshold |

## Billing Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `billing/invalid-plan` | 400 | The specified plan does not exist | Choose from: free, starter, pro, enterprise |
| `billing/checkout-failed` | 400 | Stripe checkout session failed | Try again or contact support |

## Upload Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `upload/session-not-found` | 404 | Upload session does not exist or expired | Start a new upload session |
| `upload/unauthorized` | 403 | You don't own this upload session | Check the upload_id |
| `upload/unsupported-format` | 400 | Image format not supported | Use JPEG, PNG, WebP, or BMP |

## Webhook Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `webhook/invalid-url` | 400 | Webhook URL must use HTTPS | Use an HTTPS URL |
| `webhook/invalid-event` | 400 | Subscribed to an unsupported event | Check supported events list |
| `webhook/not-found` | 404 | Webhook subscription not found | Check the webhook ID |

## Organization Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `org/slug-taken` | 409 | Organization slug already exists | Choose a different slug |
| `org/not-member` | 403 | User is not a member of this organization | Ask an admin to add you |
| `org/invalid-role` | 400 | Role must be admin, editor, or viewer | Use a valid role |

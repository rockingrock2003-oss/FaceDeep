# Data Processing Agreement

**Last Updated:** September 15, 2026

This Data Processing Agreement ("DPA") governs the processing of personal data by FaceDeep ("Processor") on behalf of the Customer ("Controller") when using the FaceDeep API service.

## 1. Definitions

- **Personal Data**: Any data relating to an identified or identifiable natural person processed via the API
- **Processing**: Any operation performed on personal data (collection, storage, analysis, deletion)
- **Controller**: The customer whose end-users' data is processed
- **Processor**: FaceDeep, providing face recognition API services
- **Sub-processor**: Third parties engaged by FaceDeep for data processing

## 2. Scope of Processing

| Data Type | Purpose | Retention |
|-----------|---------|-----------|
| Face images | Face recognition/embedding | Until deleted by user |
| Face embeddings | Vector comparison | Until deleted by user |
| API request logs | Rate limiting, analytics | 90 days |
| Account information | Authentication, billing | Account lifetime |
| Webhook deliveries | Event notifications | 30 days |

## 3. Processor Obligations

FaceDeep agrees to:

- Process personal data only on documented instructions from the Controller
- Ensure personnel are bound by confidentiality obligations
- Implement appropriate technical and organizational security measures
- Assist the Controller in responding to data subject rights requests
- Delete or return all personal data upon termination
- Make available all information necessary to demonstrate compliance

## 4. Security Measures

FaceDeep implements the following security measures:

- **Encryption**: TLS 1.3 in transit, AES-256 at rest
- **Access Control**: Role-based access, API key authentication
- **Audit Logging**: All data access logged and retained
- **Network Security**: WAF, DDoS protection, IP allowlisting
- **Infrastructure**: SOC 2 compliant cloud providers

## 5. Sub-processors

FaceDeep uses the following sub-processors:

| Sub-processor | Purpose | Location |
|---------------|---------|----------|
| Supabase | Database hosting | US/EU |
| Upstash | Redis caching | US/EU |
| Cloudflare | CDN, DDoS protection | Global |
| Stripe | Payment processing | US |

FaceDeep will notify the Controller of any changes to sub-processors at least 30 days in advance.

## 6. Data Subject Rights

FaceDeep will assist the Controller in fulfilling data subject rights requests:

- **Right of Access**: Export user data via API
- **Right to Erasure**: Delete user data via API
- **Right to Portability**: Data export in standard formats
- **Right to Rectification**: Update user data via API

## 7. Data Breach Notification

FaceDeep will notify the Controller of any personal data breach:

- Within 48 hours of becoming aware of the breach
- With details including nature, scope, and remediation steps
- With cooperation for regulatory notifications as needed

## 8. Data Transfers

Personal data may be transferred to jurisdictions outside the EEA. FaceDeep ensures:

- Standard Contractual Clauses (SCCs) are in place
- Adequate safeguards for international transfers
- Data residency options where available (EU, US, AP)

## 9. Term and Termination

- This DPA remains in effect for the duration of the service agreement
- Upon termination, FaceDeep will delete all personal data within 30 days
- Retention obligations under applicable law are excepted

## 10. Contact

For data protection inquiries, contact:

- Email: privacy@facedeep.com
- DPO: dpo@facedeep.com

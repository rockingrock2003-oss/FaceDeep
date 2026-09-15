# Deployment & Monetization Strategy

## The Reality Check

Your API uses **ML models (ArcFace)** which are compute-heavy. Pure serverless (Lambda/Cloud Functions) won't work because:
- Model loading takes 5-10 seconds (cold start killer)
- Model files are 300MB+
- Inference needs significant CPU/RAM

**Best fit: Serverless Containers** — pay per request, scale to zero when idle.

---

## Phase 1: $0/mo — MVP Launch

| Service | Provider | Cost | Notes |
|---------|----------|------|-------|
| API Hosting | **Railway** | $0 (free trial: $5 credit) | Docker deploy, auto-scaling |
| PostgreSQL | **Supabase** | $0 (free: 500MB, 50K rows) | Managed Postgres |
| Redis | **Upstash** | $0 (free: 10K cmds/day) | Serverless Redis |
| CDN/DDoS | **Cloudflare** | $0 (free tier) | Custom domain, SSL, DDoS |
| Email | **Resend** | $0 (free: 100 emails/day) | Transactional email |
| **Total** | | **$0/mo** | |

### Railway Deploy (simplest):
```bash
# 1. Install Railway CLI
npm i -g @railway/cli

# 2. Login & init
railway login
railway init

# 3. Add PostgreSQL
railway add --plugin postgresql

# 4. Add Redis (Upstash Railway integration or use Upstash directly)
railway add --plugin redis

# 5. Set env vars
railway variables set DATABASE_URL=... REDIS_URL=... SECRET_KEY=...

# 6. Deploy
railway up
```

### Alternative: Fly.io (also free tier)
```bash
flyctl auth login
flyctl launch
flyctl deploy
```

---

## Phase 2: $5-30/mo — First 100 Users

| Service | Provider | Cost | Notes |
|---------|----------|------|-------|
| API Hosting | Railway Pro | $5-20/mo | 1GB RAM, shared CPU |
| PostgreSQL | Supabase Pro | $25/mo | 8GB, daily backups |
| Redis | Upstash | $0-10/mo | Pay-per-command |
| Domain | Cloudflare | $0 | Free SSL |
| **Total** | | **$10-30/mo** | |

**Trigger to upgrade:** When you hit Railway free tier limits or need better reliability.

---

## Phase 3: $50-200/mo — Growth (1K-10K Users)

| Service | Provider | Cost | Notes |
|---------|----------|------|-------|
| API (2x) | Railway / Fly.io | $30-80/mo | 2GB RAM instances |
| PostgreSQL | Neon / Supabase Pro | $25/mo | Branching, backups |
| Redis | Upstash Pro | $20/mo | 100K cmds/day |
| Monitoring | Sentry Free | $0 | Error tracking |
| **Total** | | **$50-150/mo** | |

---

## Phase 4: $200+/mo — Scale (10K+ Users)

At this point you should have revenue to fund infrastructure.

| Service | Provider | Cost | Notes |
|---------|----------|------|-------|
| API (multi-region) | AWS ECS / GCP Cloud Run | $100-500/mo | Auto-scaling |
| GPU Instance | Modal / RunPod | $50-200/mo | ML inference |
| PostgreSQL | AWS RDS / Neon Scale | $50-100/mo | Managed, HA |
| Redis | Upstash / ElastiCache | $30-50/mo | Production cache |
| CDN | Cloudflare Pro | $20/mo | WAF, analytics |
| Monitoring | Grafana Cloud | $0-50/mo | Dashboards |
| **Total** | | **$200-900/mo** | |

---

## Monetization: Supabase-Style Pricing

### Pricing Table

| Plan | Price | Requests/day | Faces Storage | Features |
|------|-------|-------------|---------------|----------|
| **Free** | $0 | 100 | 1,000 | Basic recognition, email support |
| **Starter** | $29/mo | 10,000 | 50,000 | Webhooks, priority support |
| **Pro** | $99/mo | 100,000 | 500,000 | Analytics, custom branding |
| **Enterprise** | $299+/mo | Unlimited | Unlimited | SLA, SSO, dedicated support |

### Unit Economics

| Metric | Value |
|--------|-------|
| Cost per API call (infra) | ~$0.0001-0.001 |
| Free tier cost/user/mo | ~$0.50 |
| Starter tier margin | ~85-90% |
| Pro tier margin | ~90-95% |
| Break-even point | ~30 paying users |

### Revenue Projections

| Users | Paying (10% conv) | MRR | Infrastructure Cost | Profit |
|-------|-------------------|-----|---------------------|--------|
| 100 | 10 | $290 | $30 | $260 |
| 500 | 50 | $1,450 | $80 | $1,370 |
| 1,000 | 100 | $2,900 | $150 | $2,750 |
| 5,000 | 500 | $14,500 | $500 | $14,000 |

### Key Revenue Levers
1. **Usage-based overages** — charge per request above plan limit
2. **Webhook delivery** — premium feature
3. **Custom model training** — enterprise upsell
4. **SLA guarantees** — enterprise tier
5. **On-premise deployment** — one-time setup fee

---

## Critical: Before You Launch

### Must-Have (do these first):
1. **Domain name** — Buy `facedeep.com` or similar ($10/year)
2. **Landing page** — Simple Next.js page with pricing table
3. **Stripe Checkout** — Payment links for each plan
4. **Rate limiting** — Already built, just configure tiers
5. **Email service** — Resend or SendGrid for transactional emails
6. **Analytics** — Plausible or Umami for traffic tracking

### Nice-to-Have:
- Status page (use Instatus free tier)
- Discord community
- Developer blog
- API changelog

---

## Tech Stack Summary ($0 Start)

```
Frontend:  Next.js (Vercel free tier)
API:       FastAPI (Railway free trial → $5/mo)
Database:  PostgreSQL (Supabase free tier)
Cache:     Redis (Upstash free tier)
Auth:      Custom JWT (already built)
Payments:  Stripe (free until revenue)
CDN:       Cloudflare (free tier)
Email:     Resend (free tier)
Monitoring: Sentry free tier
```

**Total monthly cost at launch: $0**
**Total monthly cost at 100 paying users: ~$30-50**

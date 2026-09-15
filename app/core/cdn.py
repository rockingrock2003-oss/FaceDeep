import os

CLOUDFLARE_ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")

CDN_CONFIG = {
    "default_ttl": 3600,
    "api_ttl": 0,
    "static_ttl": 86400,
    "cache_everything": True,
    "bypass_cache_for_patterns": [
        "/api/v2/billing/*",
        "/api/v2/observability/*",
    ],
}

WAF_RULES = {
    "rate_limiting": {
        "enabled": True,
        "threshold": 100,
        "period": 60,
        "action": "challenge",
    },
    "bot_protection": {
        "enabled": True,
        "mode": "managed",
    },
    "ddos_protection": {
        "enabled": True,
        "level": "medium",
    },
    "custom_rules": [
        {
            "name": "Block known bad bots",
            "expression": "(cf.bot_management.score lt 20)",
            "action": "block",
        },
        {
            "name": "Protect admin endpoints",
            "expression": "(http.request.uri.path contains \"/admin\") and not ip.src in {10.0.0.0/8}",
            "action": "block",
        },
    ],
}

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

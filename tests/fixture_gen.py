"""Fixture mínimo para ensayar la infraestructura. No es el generador del dataset."""
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

START = datetime(2025, 1, 1, tzinfo=timezone.utc)
COUNTRIES = ["MX", "US", "CO", "AR", "ES", "CL", "PE", "BR"]
CATEGORIES = ["books", "toys", "tools", "food", "tech", "home"]


def doc(rng):
    moment = START + timedelta(seconds=rng.randrange(636 * 86400))
    items = [{"sku": f"S{rng.randrange(9999)}", "category": rng.choice(CATEGORIES), "brand": "b",
              "qty": rng.randint(1, 5), "price": round(rng.uniform(1, 200), 2), "tax_pct": 16, "discounts": 0}
             for _ in range(rng.randint(1, 5))]
    return {
        "order_id": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
        "timestamp": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "customer": {"id": f"C{rng.randrange(9999)}", "tier": "gold", "segment": "retail",
                     "geo": {"country": rng.choice(COUNTRIES), "state": "s", "city": "c", "zip": "0",
                             "coordinates": [0.0, 0.0]}},
        "items": items,
        "payment": {"method": "card", "status": rng.choice(["completed"] * 3 + ["failed"]),
                    "transaction_id": "t", "gateway_latency_ms": 10, "totals": {},
                    "final_total": round(sum(i["qty"] * i["price"] for i in items), 2)},
        "metadata": {"channel": "web", "user_agent": "ua", "session_id": "s", "flags": {}},
    }


def main(count, out):
    rng = random.Random(1)
    with open(out, "w") as f:
        for _ in range(count):
            f.write(json.dumps(doc(rng)) + "\n")


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])

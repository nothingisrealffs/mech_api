# BattleTech Database REST API

Complete REST API with web interface for the BattleTech mech database.

## Quick Start (local Python)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="sqlite:///$(pwd)/mech_data_test.db"   # or your Postgres DSN
uvicorn battletech_api:app --host 0.0.0.0 --port 8000
```

- API docs: http://localhost:8000/docs or http://localhost:8000/redoc  
- Use the bundled `api_frontend.html` by opening it in your browser (or `python -m http.server 8080` then visit http://localhost:8080/api_frontend.html).

## Quick Start (Docker)

### Docker Compose (recommended)
```bash
docker compose up --build
```
- API: http://localhost:8000  
- Postgres is included (default DSN `postgresql+psycopg2://mek_api:mek_api@db:5432/mek_api`). Load data separately.
- To use your own SQLite DB instead, set `DATABASE_URL=sqlite:////app/mech_data_test.db` and uncomment the volume line in `docker-compose.yml` to mount your file.

### Standalone image
```bash
docker build -t mek-api .
docker run -p 8000:8000 \
  -e DATABASE_URL="sqlite:////app/mech_data_test.db" \
  -v $(pwd)/mech_data_test.db:/app/mech_data_test.db:ro \
  mek-api
```

## Configuration
- `DATABASE_URL` (or `MEK_DATABASE_URL`): SQLAlchemy URL. SQLite and Postgres are both supported.
- `MEK_SQLITE_PATH`: Path to SQLite file if you want a shorthand instead of `DATABASE_URL`.
- CORS: currently open to all origins; tighten for production.

## API Endpoints

### Health & Status

#### `GET /`
Root endpoint - API health check
```json
{
  "status": "online",
  "api": "BattleTech Mech Database",
  "version": "1.0.0",
  "database": "connected"
}
```

#### `GET /health`
Detailed health check with database statistics
```json
{
  "status": "healthy",
  "database": "connected",
  "mechs": 150,
  "weapons": 90,
  "timestamp": "2025-01-15T10:30:00"
}
```

---

### Mech Endpoints

#### `GET /mechs`
List mechs with optional filtering and pagination

**Query Parameters:**
- `skip` (int): Records to skip (default: 0)
- `limit` (int): Max records to return (default: 100, max: 500)
- `chassis` (string): Filter by chassis name (partial match)
- `techbase` (string): Filter by techbase (IS, Clan, Mixed)
- `era` (string): Filter by era
- `role` (string): Filter by role
- `search` (string): Search across chassis and model

**Example:**
```bash
curl "http://localhost:8000/mechs?techbase=Clan&limit=10"
```

**Response:**
```json
[
  {
    "id": 1,
    "chassis": "Atlas",
    "model": "AS7-D",
    "mul_id": 123,
    "config": "Biped",
    "techbase": "Inner Sphere",
    "era": "Succession Wars",
    "role": "Juggernaut"
  }
]
```

#### `GET /mechs/{mech_id}`
Get detailed mech information including full loadout

**Example:**
```bash
curl "http://localhost:8000/mechs/1"
```

**Response:**
```json
{
  "id": 1,
  "chassis": "Atlas",
  "model": "AS7-D",
  "mul_id": 123,
  "techbase": "Inner Sphere",
  "era": "Succession Wars",
  "role": "Juggernaut",
  "locations": [
    {
      "name": "Right Arm",
      "slots": [
        {
          "slot_index": 1,
          "raw_text": "Shoulder",
          "weapon": null,
          "component_type": "actuator"
        },
        {
          "slot_index": 2,
          "raw_text": "AC/20",
          "weapon": {
            "id": 15,
            "name": "ac 20",
            "category": "IS",
            "damage": 20
          }
        }
      ]
    }
  ],
  "quirks": [
    {
      "code": "battle_fists_la",
      "description": "Battle Fists (LA)"
    }
  ],
  "manufacturers": ["Defiance Industries"],
  "factories": ["Hesperus II"]
}
```

#### `GET /mechs/by-mul-id/{mul_id}`
Get mech by Master Unit List ID

**Example:**
```bash
curl "http://localhost:8000/mechs/by-mul-id/123"
```

---

### Weapon Endpoints

#### `GET /weapons`
List all weapons with optional filtering

**Query Parameters:**
- `skip` (int): Records to skip
- `limit` (int): Max records to return
- `category` (string): Filter by category (IS, Clan)
- `search` (string): Search weapon names

**Example:**
```bash
curl "http://localhost:8000/weapons?category=IS&search=laser"
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "laser lg",
    "category": "IS",
    "damage": 8
  }
]
```

#### `GET /weapons/{weapon_id}`
Get detailed weapon information

#### `GET /weapons/{weapon_id}/aliases`
Get all aliases for a weapon

**Example:**
```bash
curl "http://localhost:8000/weapons/1/aliases"
```

**Response:**
```json
["large laser", "ll", "l laser", "laser large"]
```

#### `GET /weapons/{weapon_id}/mechs`
Get all mechs that mount a specific weapon

**Query Parameters:**
- `skip` (int): Records to skip
- `limit` (int): Max records to return

**Example:**
```bash
curl "http://localhost:8000/weapons/1/mechs?limit=20"
```

#### `GET /weapons/search/{query_text}`
Search weapons by name or alias with intelligent matching

**Example:**
```bash
curl "http://localhost:8000/weapons/search/large%20laser"
```

**Response:**
```json
{
  "query": "large laser",
  "normalized": "large laser",
  "exact_match": {
    "id": 1,
    "name": "laser lg",
    "category": "IS",
    "damage": 8
  },
  "alias_match": null,
  "partial_matches": [
    {"id": 1, "name": "laser lg", "category": "IS"},
    {"id": 5, "name": "laser lg pulse", "category": "IS"}
  ]
}
```

---

### Statistics Endpoints

#### `GET /stats/overview`
Get overall database statistics

**Response:**
```json
{
  "total_mechs": 150,
  "total_weapons": 90,
  "total_locations": 1050,
  "total_slots": 12600,
  "by_techbase": {
    "Inner Sphere": 100,
    "Clan": 45,
    "Mixed": 5
  },
  "by_era": {
    "Succession Wars": 75,
    "Clan Invasion": 50,
    "Dark Age": 25
  },
  "by_role": {
    "Brawler": 40,
    "Sniper": 35,
    "Juggernaut": 30
  }
}
```

#### `GET /stats/weapons`
Get weapon usage statistics

**Query Parameters:**
- `limit` (int): Number of weapons to return (default: 20)

**Response:**
```json
[
  {
    "weapon_name": "laser med",
    "total_instances": 450,
    "mech_count": 120,
    "avg_per_mech": 3.75
  }
]
```

#### `GET /stats/staging`
Get staging resolution statistics (data quality metrics)

**Response:**
```json
{
  "total_staging_slots": 12600,
  "resolved": 10800,
  "unresolved": 1800,
  "resolution_rate": 85.71,
  "top_unresolved": [
    {
      "token": "lrm 20 artemis iv",
      "count": 45,
      "sample": "LRM-20 (Artemis IV capable)"
    }
  ]
}
```

---

### Search & Query Endpoints

#### `GET /search`
Global search across mechs and weapons

**Query Parameters:**
- `q` (string, required): Search query (min 2 chars)
- `limit` (int): Max total results (default: 50)

**Example:**
```bash
curl "http://localhost:8000/search?q=atlas"
```

**Response:**
```json
{
  "query": "atlas",
  "mechs": [
    {"id": 1, "chassis": "Atlas", "model": "AS7-D"}
  ],
  "weapons": [],
  "total_results": 1
}
```

#### `GET /compare/mechs`
Compare multiple mechs side-by-side

**Query Parameters:**
- `mech_ids` (array of int): List of mech IDs to compare (max 5)

**Example:**
```bash
curl "http://localhost:8000/compare/mechs?mech_ids=1&mech_ids=2&mech_ids=3"
```

**Response:**
```json
{
  "comparison": [
    {
      "mech": {
        "id": 1,
        "chassis": "Atlas",
        "model": "AS7-D"
      },
      "weapons": {
        "ac 20": 1,
        "laser med": 4,
        "srm 6": 1
      }
    }
  ]
}
```

---

## Web Interface Features

The included HTML interface provides:

### 1. **Mech Browser**
- Grid view of all mechs
- Search and filter capabilities
- Click to view detailed loadout

### 2. **Weapon Catalog**
- Browse all weapons
- View aliases and usage statistics
- See which mechs use each weapon

### 3. **Statistics Dashboard**
- Total counts and breakdowns
- Most popular weapons
- Database health metrics

### 4. **Modal Detail Views**
- Full mech specifications
- Location-by-location equipment breakdown
- Interactive weapon cards

---

## Example Usage Patterns

### Get All Clan Mechs from Clan Invasion Era

```bash
curl "http://localhost:8000/mechs?techbase=Clan&era=Clan%20Invasion"
```

### Find Mechs with LRM-20

```bash
# First find the weapon
curl "http://localhost:8000/weapons/search/lrm%2020"

# Then get mechs using it (assuming weapon_id = 10)
curl "http://localhost:8000/weapons/10/mechs"
```

### Compare Three Assault Mechs

```bash
curl "http://localhost:8000/compare/mechs?mech_ids=1&mech_ids=5&mech_ids=12"
```

### Get Most Popular Weapons

```bash
curl "http://localhost:8000/stats/weapons?limit=10"
```

---

## API Response Codes

- `200 OK` - Successful request
- `404 Not Found` - Resource not found
- `400 Bad Request` - Invalid parameters
- `500 Internal Server Error` - Database or server error

---

## CORS Configuration

The API includes CORS middleware for web frontend access. For production, update the allowed origins:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # Specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Production Deployment

### Using Gunicorn (Production WSGI Server)

```bash
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker api:app --bind 0.0.0.0:8000
```

### Using Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t battletech-api .
docker run -p 8000:8000 battletech-api
```

### Environment Variables

Configure database connection via environment:

```python
# In api.py
import os

USE_POSTGRES = os.getenv('USE_POSTGRES', 'false').lower() == 'true'
POSTGRES_DSN = os.getenv('DATABASE_URL', 'postgresql://...')
```

Then run:

```bash
export USE_POSTGRES=true
export DATABASE_URL=postgresql://user:pass@localhost/mechdb
python api.py
```

---

## Performance Optimization

### Database Indexes

The schema already includes indexes on key fields:
- `mech.chassis`, `mech.mul_id`
- `location.mech_id`, `location.name`
- `weapon.name`
- `staging_slot.mech_external_id`, `staging_slot.parsed_name`

### Caching

Add Redis caching for expensive queries:

```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis

@app.on_event("startup")
async def startup():
    redis = aioredis.from_url("redis://localhost")
    FastAPICache.init(RedisBackend(redis), prefix="battletech:")

@app.get("/mechs")
@cache(expire=300)  # Cache for 5 minutes
async def list_mechs(...):
    ...
```

### Query Optimization

Use `joinedload` for related data to avoid N+1 queries:

```python
mechs = db.query(Mech).options(
    joinedload(Mech.locations).joinedload(Location.slots),
    joinedload(Mech.quirks)
).all()
```

---

## Testing the API

### Using curl

```bash
# Health check
curl http://localhost:8000/health

# Get mechs
curl http://localhost:8000/mechs?limit=5

# Search
curl "http://localhost:8000/search?q=laser"
```

### Using Python requests

```python
import requests

# Get all mechs
response = requests.get('http://localhost:8000/mechs')
mechs = response.json()

# Search for a specific mech
response = requests.get('http://localhost:8000/mechs', params={'chassis': 'Atlas'})
atlas_variants = response.json()

# Get detailed mech info
mech_id = mechs[0]['id']
detail = requests.get(f'http://localhost:8000/mechs/{mech_id}').json()
```

### Using JavaScript fetch

```javascript
// Get weapon statistics
fetch('http://localhost:8000/stats/weapons')
    .then(response => response.json())
    .then(data => console.log(data));

// Search mechs
fetch('http://localhost:8000/mechs?search=Atlas&limit=10')
    .then(response => response.json())
    .then(mechs => mechs.forEach(m => console.log(m.chassis, m.model)));
```

---

## Extending the API

### Add Custom Endpoints

```python
@app.get("/custom/mechs-by-weight")
def mechs_by_weight_class(
    weight_class: str,
    db: Session = Depends(get_db)
):
    """Custom endpoint for weight class filtering"""
    # Add your logic here
    pass
```

### Add Authentication

```python
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

@app.get("/admin/stats")
def admin_stats(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    # Verify token
    if not verify_token(credentials.credentials):
        raise HTTPException(status_code=401, detail="Invalid token")
    # Return admin data
```

### Add WebSocket Support

```python
from fastapi import WebSocket

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        # Process and send real-time updates
        await websocket.send_text(f"Response: {data}")
```

---

## Troubleshooting

### "Connection refused" errors
- Ensure API is running: `python api.py`
- Check port 8000 is not in use
- Verify firewall settings

### CORS errors in browser
- Update `allow_origins` in CORS middleware
- Ensure API URL matches in frontend code

### Slow queries
- Check database indexes
- Use query profiling: `query.statement.compile()`
- Consider adding caching

### Empty results
- Verify data was loaded via CSV loader
- Check `--finalize` was run
- Use `/stats/staging` to check resolution status

---

## Complete Workflow

```bash
# 1. Load equipment from CSVs
python load_equipment_csv.py

# 2. Ingest MTF files
python mtf_ingest_fixed.py --folder /path/to/mtf

# 3. Resolve and finalize
python mtf_ingest_fixed.py --folder /path/to/mtf --reconcile --finalize

# 4. Start API
python api.py

# 5. Open web interface
# Navigate to http://localhost:8000/docs (API docs)
# Or open index.html in browser (web UI)
```

Now you have a complete REST API with interactive documentation and a beautiful web interface for exploring your BattleTech database!

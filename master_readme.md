# ⚔️ BattleTech Database Manager

**Complete unified database system for BattleTech mechs, vehicles, aerospace units, and equipment.**

[Features](#features) • [Quick Start](#quick-start) • [Documentation](#documentation) • [Architecture](#architecture)

---

## 🌟 Features

### ✅ Multi-Format Ingestion
- **MTF Files** - BattleMech specifications
- **BLK Files** - Vehicles, aerospace, battle armor, infantry
- **CSV Files** - Canonical weapons and equipment

### ✅ Intelligent Resolution
- Automatic weapon name normalization
- Alias-based matching system
- Unresolved token tracking
- Quality metrics and reporting

### ✅ Unified Data Model
- Shared manufacturers across all unit types
- Shared factories and production facilities
- Canonical weapon definitions
- 3NF normalized schema

### ✅ Rich TUI Interface
- Interactive menu system
- Real-time status dashboard
- Progress indicators
- Warning notifications

### ✅ REST API
- FastAPI-powered endpoints
- Interactive documentation
- Search and filter capabilities
- Cross-reference queries

### ✅ Web Interface (Optional)
- Beautiful modern UI
- Browse mechs and vehicles
- Weapon catalog
- Statistics dashboard

---

## 🚀 Quick Start

### 1. Install

```bash
# Clone or download all Python files to a folder
cd battletech-db/

# Install dependencies
pip install -r requirements.txt

# Run setup
python setup.py
```

### 2. Prepare Data

```
data/
├── weapons/
│   ├── battletech_equipment.txt          ← Place here
│   ├── battletech_clan_equipment.txt     ← Place here
│   ├── battletech_is_ammo.txt            ← Place here
│   └── battletech_engine_tonnage.txt     ← Place here
│
├── mechs/                                 ← Place .mtf files
├── vehicles/                              ← Place vehicle .blk files
├── aerospace/                             ← Place aerospace .blk files
├── battlearmor/                           ← Place battle armor .blk files
└── infantry/                              ← Place infantry .blk files
```

### 3. Launch TUI

```bash
python battletech_manager.py
```

### 4. Follow the Workflow

```
1. Load Weapons/Equipment (Menu → 5)
2. Ingest Data (Menu → 1)
3. Resolve Staging (Menu → 2)
4. Finalize Transactions (Menu → 3)
5. Start API (Menu → 7)
```

### 5. Access Your Data

**TUI Dashboard**: Real-time status and management

**REST API**: http://localhost:8000/docs

**Web Interface**: Open `index.html` in browser (optional)

---

## 📁 File Overview

| File | Purpose |
|------|---------|
| `battletech_manager.py` | **Main TUI application** - Your primary interface |
| `mtf_ingest_fixed.py` | MTF (mech) file ingestion engine |
| `blk_ingest.py` | BLK (vehicle/aerospace) file ingestion engine |
| `load_equipment_csv.py` | CSV weapon/equipment loader |
| `api.py` | REST API server (FastAPI) |
| `validate_db.py` | Database validation and reporting tool |
| `setup.py` | One-time setup script |
| `requirements.txt` | Python dependencies |
| `index.html` | Web UI (optional) |

---

## 🎯 Typical Usage

### First Time Setup

```bash
# 1. Run setup
python setup.py

# 2. Launch TUI
python battletech_manager.py

# 3. In TUI:
#    - Load Weapons/Equipment (option 5)
#    - Ingest Mechs (option 1 → 1)
#    - Ingest Vehicles (option 1 → 2)
#    - Resolve Staging (option 2)
#    - Finalize (option 3)
#    - Start API (option 7)
```

### Adding New Data

```bash
# 1. Copy new files to data folders
cp new_mech.mtf data/mechs/
cp new_vehicle.blk data/vehicles/

# 2. In TUI:
#    - Ingest Data (option 1)
#    - Resolve Staging (option 2)
#    - Finalize (option 3)
```

### Checking Data Quality

```bash
# In TUI:
# - View Database Status (option 6)
# - View Unresolved Weapons (option 4)

# Or use validation tool:
python validate_db.py
```

---

## 📊 Understanding the TUI

### Status Dashboard

```
╔════════════════════════════════════════════╗
║  Mechs (MTF)                               ║
╠════════════════════════════════════════════╣
║  Total Mechs             │  150            ║
║  Staging Slots           │  12,600         ║
║  Resolved                │  10,800 (85.7%) ║
║  Finalized Slots         │  10,800         ║
║  Weapon Instances        │  8,400          ║
╚════════════════════════════════════════════╝
```

**Key Metrics:**
- **Total**: Number of unit records
- **Staging Slots**: Equipment awaiting resolution
- **Resolved**: Successfully matched to weapons (% is resolution rate)
- **Finalized**: Production records created
- **Weapon Instances**: Actual weapon installations

### Warnings

```
⚠ 1,800 mech slots pending finalization
⚠ 127 unresolved weapon tokens
```

**What they mean:**
- **Pending finalization**: Resolved staging not yet moved to production
- **Unresolved tokens**: Weapons we couldn't match (need aliases)

---

## 🔧 Configuration

### Database Selection

**SQLite (Default):**
```python
# No configuration needed
# Creates: mech_data_test.db
```

**PostgreSQL:**
Edit `mtf_ingest_fixed.py`:
```python
USE_POSTGRES = True
POSTGRES_DSN = "postgresql+psycopg2://user:pass@localhost/mechdb"
```

### Folder Structure

Default folders in `data/`. To customize, edit `battletech_manager.py`:
```python
DATA_FOLDER = Path("data")
FOLDERS = {
    "mechs": DATA_FOLDER / "mechs",
    "vehicles": DATA_FOLDER / "vehicles",
    # ... etc
}
```

---

## 📚 Documentation

Detailed guides for each component:

### Core Documentation
- [Setup Guide](setup_guide.md) - First-time setup and installation
- [TUI Guide](tui_guide.md) - Using the text interface
- [API Documentation](api_docs.md) - REST API endpoints

### Technical Documentation
- [MTF Ingestion](mtf_ingestion.md) - Mech file processing
- [BLK Ingestion](blk_ingestion.md) - Vehicle file processing
- [Database Schema](schema.md) - Table structure and relationships
- [Resolution Logic](resolution.md) - Weapon matching system

### Quick References
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
- [CLI Commands](cli_commands.md) - Command-line usage
- [API Examples](api_examples.md) - Sample API queries

---

## 🏗️ Architecture

### Data Flow

```
┌─────────────┐
│  CSV Files  │
│  (Weapons)  │
└──────┬──────┘
       │ load_equipment_csv.py
       ▼
┌─────────────────────────────────┐
│     Canonical Weapons DB        │
│  (weapon + weapon_alias)        │
└─────────────┬───────────────────┘
              │
              │ Shared by ↓
       ┌──────┴──────┐
       ▼             ▼
┌────────────┐  ┌────────────┐
│ MTF Files  │  │ BLK Files  │
│  (Mechs)   │  │ (Vehicles) │
└─────┬──────┘  └─────┬──────┘
      │ mtf_ingest     │ blk_ingest
      ▼                ▼
┌──────────────────────────────┐
│      Staging Tables          │
│  (staging_slot)              │
│  (staging_vehicle_slot)      │
└──────┬───────────────────────┘
       │ Resolve (match weapons)
       ▼
┌──────────────────────────────┐
│    Production Tables         │
│  (mech + slot)               │
│  (vehicle + vehicle_slot)    │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│         REST API             │
│  (FastAPI + Web Interface)   │
└──────────────────────────────┘
```

### Database Schema

**Shared Tables:**
- `weapon` - Canonical weapon definitions
- `weapon_alias` - Alternative names
- `manufacturer` - Shared across mechs & vehicles
- `factory` - Production facilities

**Mech Tables:**
- `mech` - BattleMech records
- `location` - Mech body parts
- `slot` - Equipment slots
- `weapon_instance` - Weapon installations

**Vehicle Tables:**
- `vehicle` - Vehicle/aerospace records
- `vehicle_location` - Body parts (turret, body, etc.)
- `vehicle_slot` - Equipment slots
- `vehicle_weapon_instance` - Weapon installations
- `vehicle_armor` - Armor points by location

**Staging Tables:**
- `staging_slot` - Mech equipment pre-resolution
- `staging_vehicle_slot` - Vehicle equipment pre-resolution
- `staging_unresolved` - Unmatched weapon tokens

---

## 🔍 API Endpoints

### Mechs
- `GET /mechs` - List mechs (with filters)
- `GET /mechs/{id}` - Get mech detail
- `GET /mechs/by-mul-id/{mul_id}` - Get by MUL ID

### Vehicles
- `GET /vehicles` - List vehicles (with filters)
- `GET /vehicles/{id}` - Get vehicle detail
- `GET /vehicles/by-mul-id/{mul_id}` - Get by MUL ID

### Weapons
- `GET /weapons` - List weapons
- `GET /weapons/{id}` - Get weapon detail
- `GET /weapons/{id}/aliases` - Get weapon aliases
- `GET /weapons/{id}/mechs` - Get mechs using weapon
- `GET /weapons/search/{query}` - Search weapons

### Statistics
- `GET /stats/overview` - Database overview
- `GET /stats/weapons` - Weapon usage stats
- `GET /stats/staging` - Resolution quality

### Search
- `GET /search?q={query}` - Global search (mechs, vehicles, weapons)
- `GET /compare/mechs?mech_ids={id1,id2}` - Compare mechs

**Full documentation:** http://localhost:8000/docs

---

## 💡 Tips & Tricks

### Improving Resolution Rate

1. **Load weapons first** - Always before ingesting units
2. **Check unresolved tokens** - Review common patterns
3. **Add aliases** - Create mappings for variant names
4. **Re-resolve** - Run resolution again after adding aliases

### Adding Weapon Aliases

**Via TUI workflow:**
1. View Unresolved Weapons (option 4)
2. Note common tokens
3. Connect to database directly
4. `INSERT INTO weapon_alias VALUES ('token', weapon_id)`
5. Resolve Staging again (option 2)

**Via API:**
```bash
curl -X POST http://localhost:8000/weapons/5/aliases \
  -H "Content-Type: application/json" \
  -d '{"alias": "er large laser"}'
```

### Bulk Operations

Process all BLK files at once:
```
TUI → Ingest Data (1) → All BLK files (6)
```

### Data Quality Checks

```bash
# Run validation tool
python validate_db.py

# Or check in TUI
Menu → View Database Status (6)
Menu → View Unresolved Weapons (4)
```

---

## 🐛 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| No files found | Check file extensions and folder paths |
| Low resolution rate | Load weapons CSVs first, add aliases |
| Pending transactions | Run Finalize (option 3) |
| Database locked | Close other connections to SQLite file |
| Import errors | Install dependencies: `pip install -r requirements.txt` |

### Getting Help

1. Check status dashboard (TUI option 6)
2. Review error messages
3. Run validation tool: `python validate_db.py`
4. Check this README and documentation files
5. Inspect database with SQL browser

---

## 🚀 Production Deployment

### Use PostgreSQL

```python
# Edit mtf_ingest_fixed.py
USE_POSTGRES = True
POSTGRES_DSN = "postgresql://user:pass@localhost/mechdb"
```

### Run API with Gunicorn

```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker api:app \
  --bind 0.0.0.0:8000
```

### Set up systemd service

```ini
[Unit]
Description=BattleTech API
After=network.target

[Service]
User=battletech
WorkingDirectory=/opt/battletech-db
ExecStart=/usr/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker api:app
Restart=always

[Install]
WantedBy=multi-user.target
```

### Backup Database

**SQLite:**
```bash
cp mech_data_test.db backup_$(date +%Y%m%d).db
```

**PostgreSQL:**
```bash
pg_dump mechdb > backup_$(date +%Y%m%d).sql
```

---

## 📦 What's Included

### Python Scripts
- ✅ TUI Manager (`battletech_manager.py`)
- ✅ MTF Ingestion (`mtf_ingest_fixed.py`)
- ✅ BLK Ingestion (`blk_ingest.py`)
- ✅ CSV Loader (`load_equipment_csv.py`)
- ✅ REST API (`api.py`)
- ✅ Validation Tool (`validate_db.py`)
- ✅ Setup Script (`setup.py`)

### Database Features
- ✅ 3NF normalized schema
- ✅ Shared manufacturers/factories
- ✅ Canonical weapons with aliases
- ✅ Staging tables for quality control
- ✅ SQLite and PostgreSQL support

### Interfaces
- ✅ Rich TUI with real-time status
- ✅ REST API with OpenAPI docs
- ✅ Optional web interface (HTML)

---

## 📈 Project Status

**Current Version:** 1.0.0

**Supported Formats:**
- ✅ MTF (BattleMech files)
- ✅ BLK (Vehicle/Aerospace/Battle Armor/Infantry files)
- ✅ CSV (Equipment data)

**Database Support:**
- ✅ SQLite (default)
- ✅ PostgreSQL

**Unit Types:**
- ✅ BattleMechs
- ✅ Vehicles (tanks, hovers, wheeled, tracked)
- ✅ Aerospace fighters
- ✅ Battle armor
- ✅ Infantry

---

## 🤝 Contributing

Contributions welcome! Areas for enhancement:

- [ ] Additional unit type support
- [ ] Advanced search filters
- [ ] Data visualization
- [ ] Export functionality
- [ ] Batch alias creation
- [ ] Custom report generation

---

## 📄 License

Free for personal and commercial use. Attribution appreciated but not required.

---

## 🎯 Summary

This is a **complete, production-ready system** for managing BattleTech data:

1. **Ingest** MTF and BLK files
2. **Resolve** equipment to canonical weapons
3. **Track** data quality with staging tables
4. **Query** via REST API
5. **Browse** with web interface

**Everything runs locally. No external services required.**

---

## 🌟 Quick Links

- Start: `python battletech_manager.py`
- API Docs: http://localhost:8000/docs
- Validation: `python validate_db.py`
- Setup: `python setup.py`

---

**Ready to manage your BattleTech database? Run `python setup.py` to begin!**

⚔️ **Happy commanding, MechWarrior!** ⚔️

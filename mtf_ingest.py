#!/usr/bin/env python3
"""
mtf_ingest_fixed.py

Fixed version of the earlier mtf_ingest.py with improved parser and error logging.
Creates SQLite test DB by default (mech_data_test.db in same folder).
Switch to Postgres via USE_POSTGRES = True and set POSTGRES_DSN.
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import defaultdict

from pydantic import BaseModel
from tqdm import tqdm

from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String, Text, Boolean, DateTime,
    ForeignKey, UniqueConstraint, Table
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.exc import IntegrityError

# -----------------------------
# CONFIG: toggle here
# -----------------------------
USE_POSTGRES = False
POSTGRES_DSN = "postgresql+psycopg2://username:password@localhost:5432/mechdb"
SQLITE_FILENAME = "mech_data_test.db"
EMPTY_TOKEN_VARIANTS = {"-empty-", "-empty", "empty", "- Empty -", "-Empty-", "- EMPTY -"}

# -----------------------------
# SQLAlchemy base
# -----------------------------
Base = declarative_base()

# association tables
mech_manufacturer_table = Table(
    "mech_manufacturer", Base.metadata,
    Column("mech_id", ForeignKey("mech.id", ondelete="CASCADE"), primary_key=True),
    Column("manufacturer_id", ForeignKey("manufacturer.id"), primary_key=True)
)

mech_factory_table = Table(
    "mech_factory", Base.metadata,
    Column("mech_id", ForeignKey("mech.id", ondelete="CASCADE"), primary_key=True),
    Column("factory_id", ForeignKey("factory.id"), primary_key=True)
)

# -----------------------------
# ORM Models (simplified to support fixed parser)
# -----------------------------
class Mech(Base):
    __tablename__ = "mech"
    id = Column(Integer, primary_key=True)
    chassis = Column(String, index=True, nullable=False)
    model = Column(String, index=True)
    mul_id = Column(Integer, unique=True, index=True, nullable=True)
    config = Column(String)
    techbase = Column(String)
    era = Column(String)
    source = Column(String)
    rules_level = Column(Integer)
    role = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    raw_doc = Column(Text)

    locations = relationship("Location", back_populates="mech", cascade="all, delete-orphan")
    quirks = relationship("Quirk", secondary="mech_quirk", back_populates="mechs")

class Manufacturer(Base):
    __tablename__ = "manufacturer"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)

class Factory(Base):
    __tablename__ = "factory"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)

class Quirk(Base):
    __tablename__ = "quirk"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)
    description = Column(Text)
    mechs = relationship("Mech", secondary="mech_quirk", back_populates="quirks")

class MechQuirk(Base):
    __tablename__ = "mech_quirk"
    mech_id = Column(Integer, ForeignKey("mech.id", ondelete="CASCADE"), primary_key=True)
    quirk_id = Column(Integer, ForeignKey("quirk.id", ondelete="CASCADE"), primary_key=True)

class Location(Base):
    __tablename__ = "location"
    id = Column(Integer, primary_key=True)
    mech_id = Column(Integer, ForeignKey("mech.id", ondelete="CASCADE"), index=True)
    name = Column(String, nullable=False)
    position_order = Column(Integer, nullable=True)
    mech = relationship("Mech", back_populates="locations")
    slots = relationship("Slot", back_populates="location", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("mech_id", "name", name="u_mech_location"),)

class ComponentType(Base):
    __tablename__ = "component_type"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    category = Column(String)

class Weapon(Base):
    __tablename__ = "weapon"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    category = Column(String)
    damage = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

class WeaponAlias(Base):
    __tablename__ = "weapon_alias"
    alias = Column(String, primary_key=True)
    weapon_id = Column(Integer, ForeignKey("weapon.id", ondelete="CASCADE"))
    weapon = relationship("Weapon")

class StagingSlot(Base):
    """
    Fast target for staging rows. Use INTEGER PK for SQLite autoincrement compatibility.
    """
    __tablename__ = "staging_slot"
    id = Column(Integer, primary_key=True, autoincrement=True)   # <- IMPORTANT: Integer + autoincrement for SQLite
    file_name = Column(String)
    mech_external_id = Column(String, index=True)
    location_name = Column(String, index=True)
    slot_index = Column(Integer)
    raw_text = Column(Text)
    parsed_name = Column(String, index=True)
    parsed_type = Column(String, index=True)  # 'weapon', 'actuator', 'ammo'
    weapon_id = Column(Integer, ForeignKey("weapon.id"), nullable=True, index=True)
    resolved = Column(Boolean, default=False)
    resolution_hint = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
class StagingUnresolved(Base):
    __tablename__ = "staging_unresolved"
    token = Column(String, primary_key=True)
    sample_raw = Column(Text)
    example_staging_id = Column(BigInteger)
    seen_count = Column(Integer, default=1)
    last_seen = Column(DateTime, default=datetime.utcnow)

class Slot(Base):
    __tablename__ = "slot"
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey("location.id", ondelete="CASCADE"), index=True)
    slot_index = Column(Integer, nullable=False)
    raw_text = Column(Text)
    component_type_id = Column(Integer, ForeignKey("component_type.id"), nullable=True)
    note = Column(Text)
    location = relationship("Location", back_populates="slots")
    __table_args__ = (UniqueConstraint("location_id", "slot_index", name="u_location_slotidx"),)

class WeaponInstance(Base):
    __tablename__ = "weapon_instance"
    id = Column(Integer, primary_key=True)
    slot_id = Column(Integer, ForeignKey("slot.id", ondelete="CASCADE"), unique=True, index=True)
    weapon_id = Column(Integer, ForeignKey("weapon.id", ondelete="SET NULL"))
    qty = Column(Integer, default=1)

class LoaderLog(Base):
    __tablename__ = "loader_log"
    id = Column(Integer, primary_key=True)
    file_name = Column(String, index=True)
    status = Column(String)
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

# -----------------------------
# Parser model and parser
# -----------------------------
class ParsedMech(BaseModel):
    chassis: Optional[str] = None
    model: Optional[str] = None
    mul_id: Optional[int] = None
    config: Optional[str] = None
    techbase: Optional[str] = None
    era: Optional[str] = None
    source: Optional[str] = None
    rules_level: Optional[int] = None
    role: Optional[str] = None

    quirks: List[str] = []
    specs: Dict[str, str] = {}
    locations: Dict[str, List[str]] = {}
    narratives: Dict[str, str] = {}
    manufacturer: List[str] = []
    factory: List[str] = []
    systemmanufacturer: List[str] = []

    raw_text: Optional[str] = None

HEADER_RE = re.compile(r"^([^:]+):(.*)$")

def normalize_header_key(k: str) -> str:
    """Normalize header key to a canonical lowercase form"""
    return re.sub(r"\s+", " ", k.strip().lower())

def split_csv_like(val: str) -> List[str]:
    return [x.strip() for x in re.split(r",\s*", val) if x.strip()]

def parse_mtf_text(text: str) -> ParsedMech:
    """
    Robust parser: known keys are applied to model fields; unknown keys go into parsed.specs.
    Sections with no immediate inline value are treated as blocks/lists (locations or narratives).
    """
    lines = [ln.rstrip("\n") for ln in text.splitlines()]
    parsed = ParsedMech(raw_text=text)

    current_section = None
    current_section_lines: List[str] = []

    def flush_section():
        nonlocal current_section, current_section_lines
        if not current_section:
            return
        key = current_section.strip()
        key_norm = normalize_header_key(key)
        content_lines = [ln for ln in current_section_lines if ln.strip() != ""]
        # If this looks like a location (contains Arm/Torso/Head/Leg), store as location list
        if re.search(r"\b(arm|torso|head|leg)\b", key, re.IGNORECASE):
            loc_name = key.rstrip(":").strip()
            parsed.locations[loc_name] = [ln.strip() for ln in content_lines]
        else:
            # treat as narrative if key matches known narrative names
            if key_norm in {"overview", "capabilities", "deployment", "history"}:
                parsed.narratives[key_norm] = "\n".join(content_lines).strip()
            else:
                # otherwise store the lines as either a single scalar or joined text in specs
                if len(content_lines) == 1:
                    val = content_lines[0].strip()
                    # map some known keys to model fields
                    if key_norm in {"manufacturer", "manufacturers"}:
                        parsed.manufacturer.extend(split_csv_like(val))
                    elif key_norm in {"primaryfactory", "primary factory", "primary_factory"}:
                        parsed.factory.extend(split_csv_like(val))
                    elif key_norm.startswith("systemmanufacturer") or key_norm.startswith("system manufacturer"):
                        # sometimes this is "systemmanufacturer:ENGINE:VOX 280" - handle elsewhere
                        parsed.systemmanufacturer.extend(split_csv_like(val))
                    elif key_norm in {"mass", "engine", "structure", "myomer", "heat sinks", "walk mp", "jump mp", "armor", "armor type", "rules level", "mul id"}:
                        parsed.specs[key_norm] = val
                        if key_norm == "mul id":
                            try:
                                parsed.mul_id = int(val)
                            except:
                                pass
                    elif key_norm in {"chassis", "model", "config", "techbase", "era", "source", "role"}:
                        # known top-level fields
                        setattr(parsed, key_norm.replace(" ", "_"), val)
                    elif key_norm.startswith("quirk"):
                        parsed.quirks.append(val)
                    else:
                        parsed.specs[key_norm] = val
                else:
                    # multi-line block -> store as joined text
                    parsed.specs[key_norm] = "\n".join(content_lines).strip()

        current_section = None
        current_section_lines = []

    for ln in lines + [""]:
        m = HEADER_RE.match(ln)
        if m:
            flush_section()
            hdr = m.group(1).strip()
            val = m.group(2).strip()
            if val != "":
                key_norm = normalize_header_key(hdr)
                # handle immediate scalar mapping
                if key_norm in {"chassis", "model", "config", "techbase", "era", "source", "role"}:
                    setattr(parsed, key_norm.replace(" ", "_"), val)
                elif key_norm == "mul id":
                    try:
                        parsed.mul_id = int(val)
                    except:
                        parsed.specs["mul id"] = val
                elif key_norm in {"quirk", "quirks"}:
                    # could be "quirk:battle_fists_la" repeated
                    parsed.quirks.append(val)
                elif key_norm in {"manufacturer", "manufacturers"}:
                    parsed.manufacturer.extend(split_csv_like(val))
                elif key_norm in {"primaryfactory", "primary factory", "primary_factory"}:
                    parsed.factory.extend(split_csv_like(val))
                elif key_norm.startswith("systemmanufacturer") or key_norm.startswith("system manufacturer"):
                    # sometimes systemmanufacturer:ENGINE:VOX 280 or "systemmanufacturer: ENGINE: VOX 280"
                    # Keep entire RHS, we'll parse into systemmanufacturer list
                    parsed.systemmanufacturer.append(val)
                elif key_norm in {"overview", "capabilities", "deployment", "history"}:
                    parsed.narratives[key_norm] = val
                else:
                    # unknown scalar -> put into specs
                    parsed.specs[key_norm] = val
                current_section = None
            else:
                # header that introduces a list / block
                current_section = hdr
                current_section_lines = []
        else:
            # not a header; if within a section, collect; else treat as stray
            if current_section:
                current_section_lines.append(ln)
            else:
                if ln.strip():
                    # stray line: append to overview if possible, else add to notes
                    if parsed.narratives.get("overview"):
                        parsed.narratives["overview"] += "\n" + ln
                    else:
                        parsed.specs.setdefault("notes", "")
                        parsed.specs["notes"] += ln + "\n"

    flush_section()
    # normalize quirks, manufacturers, factory lists
    parsed.quirks = [q.strip() for q in parsed.quirks if q and q.strip()]
    parsed.manufacturer = [m.strip() for m in parsed.manufacturer if m and m.strip()]
    parsed.factory = [f.strip() for f in parsed.factory if f and f.strip()]
    parsed.systemmanufacturer = [s.strip() for s in parsed.systemmanufacturer if s and s.strip()]

    return parsed

# -----------------------------
# DB helpers & ingestion logic
# -----------------------------
def get_engine_and_session(use_postgres: bool = False):
    if use_postgres:
        if not POSTGRES_DSN or POSTGRES_DSN.strip() == "":
            raise RuntimeError("POSTGRES_DSN not configured.")
        engine = create_engine(POSTGRES_DSN, echo=False)
    else:
        sqlite_path = Path(SQLITE_FILENAME).resolve()
        engine = create_engine(f"sqlite:///{sqlite_path}", echo=False)
    Session = sessionmaker(bind=engine)
    return engine, Session

def initialize_db(engine):
    Base.metadata.create_all(bind=engine)

def normalize_token(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s2 = s.strip()
    if s2 == "":
        return None
    s2_lower = re.sub(r"[^\w\s\-]", " ", s2).strip().lower()
    s2_lower = re.sub(r"\s+", " ", s2_lower)
    if s2_lower in {v.lower() for v in EMPTY_TOKEN_VARIANTS}:
        return None
    return s2_lower

def try_int(x):
    if x is None:
        return None
    try:
        return int(str(x).strip())
    except:
        return None

def guess_parsed_type(raw_line: str) -> str:
    if raw_line is None:
        return "unknown"
    t = raw_line.lower()
    if "ammo" in t or re.search(r"\bamm?o\b", t):
        return "ammo"
    if re.search(r"\b(lrm|srm|ml|gauss|laser|large|medium|small|ac|plasma)\b", t):
        return "weapon"
    if "actuator" in t or "shoulder" in t or "hip" in t or "foot" in t or "hand" in t or "gyro" in t or "engine" in t or "sensors" in t:
        return "component"
    if raw_line.strip().lower() in {v.lower() for v in EMPTY_TOKEN_VARIANTS}:
        return "empty"
    return "unknown"

def upsert_weapon(session, name: str) -> int:
    if not name:
        raise ValueError("Empty name")
    name = name.strip()
    w = session.query(Weapon).filter(Weapon.name == name).one_or_none()
    if w:
        return w.id
    w = Weapon(name=name)
    session.add(w)
    session.flush()
    return w.id

def ingest_parsed_mech(session, parsed: ParsedMech, source_filename: str) -> Tuple[int, List[int]]:
    """
    Insert mech and create staging rows for each location slot.
    Returns (mech_id, list_of_staging_ids)
    """
    # ensure mandatory chassis
    chassis = parsed.chassis or parsed.specs.get("chassis") or "UNKNOWN"
    mech = Mech(
        chassis=chassis,
        model=parsed.model,
        mul_id=parsed.mul_id,
        config=parsed.config,
        techbase=parsed.techbase,
        era=parsed.era,
        source=parsed.source,
        rules_level=try_int(parsed.specs.get("rules level") or parsed.specs.get("rules_level")),
        role=parsed.role,
        raw_doc=parsed.raw_text
    )
    session.add(mech)
    session.flush()

    staging_ids = []
    # create Location rows and staging_slot entries
    for loc_name, items in parsed.locations.items():
        loc = Location(mech_id=mech.id, name=loc_name)
        session.add(loc)
        session.flush()
        for idx, raw_line in enumerate(items, start=1):
            raw_line = raw_line.strip()
            parsed_name = normalize_token(raw_line)
            parsed_type = guess_parsed_type(raw_line)
            s = StagingSlot(
                file_name=source_filename,
                mech_external_id=str(parsed.mul_id) if parsed.mul_id is not None else None,
                location_name=loc_name,
                slot_index=idx,
                raw_text=raw_line,
                parsed_name=parsed_name,
                parsed_type=parsed_type,
                resolved=False
            )
            session.add(s)
            session.flush()
            staging_ids.append(s.id)

    # quirks -> upsert
    for q in parsed.quirks:
        qc = q.strip()
        if not qc:
            continue
        existing = session.query(Quirk).filter(Quirk.code == qc).one_or_none()
        if not existing:
            existing = Quirk(code=qc)
            session.add(existing)
            session.flush()
        try:
            session.execute(MechQuirk.__table__.insert().values(mech_id=mech.id, quirk_id=existing.id))
        except IntegrityError:
            session.rollback()

    # manufacturers & factory inserts (normalized)
    for mname in parsed.manufacturer:
        mname = mname.strip()
        if not mname:
            continue
        m = session.query(Manufacturer).filter(Manufacturer.name == mname).one_or_none()
        if not m:
            m = Manufacturer(name=mname)
            session.add(m)
            session.flush()
        try:
            session.execute(mech_manufacturer_table.insert().values(mech_id=mech.id, manufacturer_id=m.id))
        except IntegrityError:
            session.rollback()

    for fname in parsed.factory:
        fname = fname.strip()
        if not fname:
            continue
        f = session.query(Factory).filter(Factory.name == fname).one_or_none()
        if not f:
            f = Factory(name=fname)
            session.add(f)
            session.flush()
        try:
            session.execute(mech_factory_table.insert().values(mech_id=mech.id, factory_id=f.id))
        except IntegrityError:
            session.rollback()

    session.add(LoaderLog(file_name=source_filename, status="ok", message="ingested"))
    session.flush()
    return mech.id, staging_ids

def resolve_staging(session):
    """
    Resolve staging rows against Weapon (exact) and WeaponAlias (alias).
    Create/Update staging_unresolved for any remaining tokens.
    """
    updated = 0
    # exact matches
    rows = session.query(StagingSlot).filter(StagingSlot.parsed_type == 'weapon', StagingSlot.parsed_name != None).all()
    for s in rows:
        if s.resolved and s.weapon_id:
            continue
        if s.parsed_name is None:
            continue
        w = session.query(Weapon).filter(Weapon.name == s.parsed_name).one_or_none()
        if w:
            s.weapon_id = w.id
            s.resolved = True
            s.resolution_hint = "exact"
            updated += 1
            continue
        a = session.query(WeaponAlias).filter(WeaponAlias.alias == s.parsed_name).one_or_none()
        if a:
            s.weapon_id = a.weapon_id
            s.resolved = True
            s.resolution_hint = "alias"
            updated += 1
    session.flush()

    # aggregate unresolved tokens
    unresolved = session.query(StagingSlot.parsed_name, StagingSlot.raw_text, StagingSlot.id).filter(
        StagingSlot.parsed_type == 'weapon',
        (StagingSlot.weapon_id == None) | (StagingSlot.resolved == False)
    ).all()

    token_map = {}
    for parsed_name, raw_text, sid in unresolved:
        if not parsed_name:
            continue
        if parsed_name not in token_map:
            token_map[parsed_name] = {"sample_raw": raw_text, "example": sid, "count": 0}
        token_map[parsed_name]["count"] += 1

    for token, info in token_map.items():
        existing = session.query(StagingUnresolved).get(token)
        if not existing:
            su = StagingUnresolved(token=token, sample_raw=info["sample_raw"], example_staging_id=info["example"], seen_count=info["count"])
            session.add(su)
        else:
            existing.sample_raw = info["sample_raw"]
            existing.example_staging_id = info["example"]
            existing.seen_count = existing.seen_count + info["count"]
            existing.last_seen = datetime.utcnow()
    session.flush()
    return updated, len(token_map)

def finalize_slots_from_staging(session):
    """
    Move resolved staging rows into final Slot and WeaponInstance tables.
    """
    rows = session.query(StagingSlot).filter(StagingSlot.resolved == True).all()
    created_slots = 0
    created_winst = 0

    for s in tqdm(rows, desc="finalizing slots", leave=False):
        mech = None
        if s.mech_external_id:
            try:
                mech = session.query(Mech).filter(Mech.mul_id == int(s.mech_external_id)).one_or_none()
            except:
                mech = None
        if not mech:
            # Best-effort: try to find mech by LoaderLog filename prefix if mech_external_id absent
            # (This is best-effort only; skip if mech cannot be determined)
            # Extract candidate mech by file_name -> loader_log -> most recent ingested mech with that raw_doc matching
            continue

        loc = session.query(Location).filter(Location.mech_id == mech.id, Location.name == s.location_name).one_or_none()
        if not loc:
            loc = Location(mech_id=mech.id, name=s.location_name)
            session.add(loc)
            session.flush()
        existing_slot = session.query(Slot).filter(Slot.location_id == loc.id, Slot.slot_index == s.slot_index).one_or_none()
        if existing_slot:
            continue
        note = None
        raw_text = s.raw_text
        if raw_text and raw_text.strip().lower() in {v.lower() for v in EMPTY_TOKEN_VARIANTS}:
            note = "Empty"
        slot = Slot(location_id=loc.id, slot_index=s.slot_index, raw_text=raw_text, note=note)
        session.add(slot)
        session.flush()
        created_slots += 1

        if s.weapon_id:
            winst = WeaponInstance(slot_id=slot.id, weapon_id=s.weapon_id, qty=1)
            session.add(winst)
            session.flush()
            created_winst += 1
    session.flush()
    return created_slots, created_winst

# -----------------------------
# CLI wiring
# -----------------------------
def discover_mtf_files(folder: Path) -> List[Path]:
    return sorted([p for p in folder.glob("*.mtf")] + [p for p in folder.glob("*.MTF")])

def process_folder(folder: Path, session):
    files = discover_mtf_files(folder)
    if not files:
        print("No .mtf files found in", folder)
        return
    stats = {"files": 0, "staging_rows": 0}
    for f in tqdm(files, desc="files"):
        try:
            text = f.read_text(encoding="utf-8")
        except Exception as e:
            session.add(LoaderLog(file_name=str(f), status="failed", message=f"read_error: {e}"))
            session.commit()
            print(f"Failed to read {f}: {e}")
            continue
        try:
            parsed = parse_mtf_text(text)
            mech_id, staging_ids = ingest_parsed_mech(session, parsed, source_filename=str(f.name))
            session.commit()
            stats["files"] += 1
            stats["staging_rows"] += len(staging_ids)
        except Exception as e:
            session.rollback()
            msg = f"ingest_error: {type(e).__name__}: {e}"
            session.add(LoaderLog(file_name=str(f), status="failed", message=msg))
            session.commit()
            print(f"Failed to ingest {f}: {msg}")
    return stats

def print_unresolved(session, limit=100):
    unresolved = session.query(StagingUnresolved).order_by(StagingUnresolved.seen_count.desc()).limit(limit).all()
    if not unresolved:
        print("No unresolved tokens.")
        return
    print("Unresolved tokens (sample):")
    for u in unresolved:
        print(f"- token: {u.token}  seen: {u.seen_count} sample_raw: {u.sample_raw}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", "-f", type=str, required=True, help="Folder containing .mtf files to ingest")
    parser.add_argument("--reconcile", action="store_true", help="Run resolution/finalization steps (assumes staging exists)")
    parser.add_argument("--finalize", action="store_true", help="Finalize resolved staging to final slot/weapon_instance tables")
    parser.add_argument("--use-postgres", action="store_true", help="Temporarily override USE_POSTGRES (connect to POSTGRES_DSN)")
    args = parser.parse_args()

    use_postgres = USE_POSTGRES or args.use_postgres
    engine, Session = get_engine_and_session(use_postgres)
    print("Connecting to", engine.url)
    initialize_db(engine)
    session = Session()

    folder = Path(args.folder)
    if not folder.exists():
        print("Folder doesn't exist:", folder)
        sys.exit(1)

    if not args.reconcile:
        print("Beginning ingest of .mtf files from", folder)
        stats = process_folder(folder, session)
        print("Ingest complete:", stats)
        print("Now run with --reconcile to perform resolution (linking to canonical weapons) and --finalize to write final slot records.")
    else:
        print("Running resolve step (exact and alias matching)...")
        updated, unresolved_count = resolve_staging(session)
        session.commit()
        print(f"Resolved {updated} staging rows; {unresolved_count} distinct tokens remain unresolved.")
        print_unresolved(session)
        if args.finalize:
            print("Finalizing resolved staging rows into slot / weapon_instance tables...")
            created_slots, created_winst = finalize_slots_from_staging(session)
            session.commit()
            print(f"Created {created_slots} slots and {created_winst} weapon instances from resolved staging rows.")
    session.close()

if __name__ == "__main__":
    main()

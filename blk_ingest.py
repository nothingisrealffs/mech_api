#!/usr/bin/env python3
"""
blk_ingest.py

Ingests BattleTech .blk (block) files for vehicles, aerospace, etc.
Similar to mtf_ingest_fixed.py but handles the BLK format with XML-like tags.
Creates staging tables and resolves to existing canonical weapons/manufacturers.
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
    ForeignKey, UniqueConstraint, Table, Float
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.exc import IntegrityError

# Import shared components from mtf_ingest_fixed
from mtf_ingest import (
    Base, Weapon, WeaponAlias, ComponentType, Manufacturer, Factory,
    get_engine_and_session, normalize_token,
    USE_POSTGRES, POSTGRES_DSN, EMPTY_TOKEN_VARIANTS
)

# -----------------------------
# BLK-specific ORM Models
# -----------------------------

class Vehicle(Base):
    """Vehicles, tanks, aerospace units, etc. from BLK files"""
    __tablename__ = "vehicle"
    id = Column(Integer, primary_key=True)
    name = Column(String, index=True, nullable=False)
    model = Column(String, index=True)
    mul_id = Column(Integer, unique=True, index=True, nullable=True)
    unit_type = Column(String, index=True)  # Tank, VTOL, Aerospace, etc.
    year = Column(Integer)
    original_build_year = Column(Integer)
    type_classification = Column(String)  # "IS Level 1", "Clan Level 2", etc.
    role = Column(String)
    motion_type = Column(String)  # Wheeled, Tracked, Hover, etc.
    cruise_mp = Column(Integer)
    engine_type = Column(Integer)
    tonnage = Column(Float)
    fuel_type = Column(String)
    source = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    raw_doc = Column(Text)
    
    locations = relationship("VehicleLocation", back_populates="vehicle", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint("name", "model", "mul_id", name="u_vehicle_name_model_mul"),
    )

vehicle_manufacturer_table = Table(
    "vehicle_manufacturer", Base.metadata,
    Column("vehicle_id", ForeignKey("vehicle.id", ondelete="CASCADE"), primary_key=True),
    Column("manufacturer_id", ForeignKey("manufacturer.id"), primary_key=True)
)

vehicle_factory_table = Table(
    "vehicle_factory", Base.metadata,
    Column("vehicle_id", ForeignKey("vehicle.id", ondelete="CASCADE"), primary_key=True),
    Column("factory_id", ForeignKey("factory.id"), primary_key=True)
)

class VehicleLocation(Base):
    """Equipment locations for vehicles (Body, Turret, Front, etc.)"""
    __tablename__ = "vehicle_location"
    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicle.id", ondelete="CASCADE"), index=True)
    name = Column(String, nullable=False)  # Body, Turret, Front, Rear, etc.
    position_order = Column(Integer, nullable=True)
    vehicle = relationship("Vehicle", back_populates="locations")
    slots = relationship("VehicleSlot", back_populates="location", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("vehicle_id", "name", name="u_vehicle_location"),)

class VehicleSlot(Base):
    """Final equipment slot for vehicles"""
    __tablename__ = "vehicle_slot"
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey("vehicle_location.id", ondelete="CASCADE"), index=True)
    slot_index = Column(Integer, nullable=False)
    raw_text = Column(Text)
    component_type_id = Column(Integer, ForeignKey("component_type.id"), nullable=True)
    note = Column(Text)
    location = relationship("VehicleLocation", back_populates="slots")
    __table_args__ = (UniqueConstraint("location_id", "slot_index", name="u_vehicle_location_slotidx"),)

class VehicleWeaponInstance(Base):
    """Weapons mounted on vehicles"""
    __tablename__ = "vehicle_weapon_instance"
    id = Column(Integer, primary_key=True)
    slot_id = Column(Integer, ForeignKey("vehicle_slot.id", ondelete="CASCADE"), unique=True, index=True)
    weapon_id = Column(Integer, ForeignKey("weapon.id", ondelete="SET NULL"))
    qty = Column(Integer, default=1)

class StagingVehicleSlot(Base):
    """Staging table for vehicle equipment before resolution"""
    __tablename__ = "staging_vehicle_slot"
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String)
    vehicle_external_id = Column(String, index=True)  # mul_id or name+model
    location_name = Column(String, index=True)
    slot_index = Column(Integer)
    raw_text = Column(Text)
    parsed_name = Column(String, index=True)
    parsed_type = Column(String, index=True)  # 'weapon', 'ammo', 'component'
    weapon_id = Column(Integer, ForeignKey("weapon.id"), nullable=True, index=True)
    resolved = Column(Boolean, default=False)
    resolution_hint = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class VehicleSystemManufacturer(Base):
    """System manufacturer info for vehicles (chassis, engine, armor, etc.)"""
    __tablename__ = "vehicle_system_manufacturer"
    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicle.id", ondelete="CASCADE"), index=True)
    system_type = Column(String)  # CHASSIS, ENGINE, ARMOR, etc.
    manufacturer_name = Column(String)

class VehicleArmor(Base):
    """Armor points by location for vehicles"""
    __tablename__ = "vehicle_armor"
    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicle.id", ondelete="CASCADE"), index=True)
    location = Column(String)  # front, rear, left, right, turret, etc.
    points = Column(Integer)

# -----------------------------
# BLK Parser
# -----------------------------

class ParsedVehicle(BaseModel):
    """Parsed BLK file data"""
    name: Optional[str] = None
    model: Optional[str] = None
    mul_id: Optional[int] = None
    unit_type: Optional[str] = None
    year: Optional[int] = None
    original_build_year: Optional[int] = None
    type_classification: Optional[str] = None
    role: Optional[str] = None
    motion_type: Optional[str] = None
    cruise_mp: Optional[int] = None
    engine_type: Optional[int] = None
    tonnage: Optional[float] = None
    fuel_type: Optional[str] = None
    source: Optional[str] = None
    
    armor: List[int] = []  # armor values in order
    equipment: Dict[str, List[str]] = {}  # location -> equipment list
    system_manufacturers: Dict[str, str] = {}  # system_type -> manufacturer
    
    manufacturer: List[str] = []
    factory: List[str] = []
    
    overview: Optional[str] = None
    capabilities: Optional[str] = None
    deployment: Optional[str] = None
    history: Optional[str] = None
    
    raw_text: Optional[str] = None

# BLK format uses XML-like tags: <TagName>\nvalue\n</TagName>
TAG_RE = re.compile(r"<([^>]+)>\s*", re.IGNORECASE)
CLOSE_TAG_RE = re.compile(r"</([^>]+)>\s*", re.IGNORECASE)

def parse_blk_text(text: str) -> ParsedVehicle:
    """
    Parse BLK file format with XML-like tags.
    Tags can contain spaces and special characters (e.g., "mul id:", "Body Equipment").
    """
    lines = text.splitlines()
    parsed = ParsedVehicle(raw_text=text)
    
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        
        # Try to match opening tag
        tag_match = TAG_RE.match(line)
        if not tag_match:
            i += 1
            continue
        
        tag_name = tag_match.group(1).strip()
        tag_lower = tag_name.lower()
        
        # Collect content until closing tag
        content_lines = []
        i += 1
        
        # Look for closing tag
        while i < len(lines):
            close_match = CLOSE_TAG_RE.match(lines[i])
            if close_match and close_match.group(1).strip().lower() == tag_lower:
                # Found closing tag
                i += 1
                break
            content_lines.append(lines[i].rstrip())
            i += 1
        
        # Join content (strip empty lines)
        content = "\n".join(content_lines).strip()
        
        # Map tags to model fields
        if tag_lower == "name":
            parsed.name = content
        elif tag_lower == "model":
            parsed.model = content
        elif tag_lower == "mul id:":
            try:
                parsed.mul_id = int(content)
            except:
                pass
        elif tag_lower == "unittype":
            parsed.unit_type = content
        elif tag_lower == "year":
            try:
                parsed.year = int(content)
            except:
                pass
        elif tag_lower == "originalbuildyear":
            try:
                parsed.original_build_year = int(content)
            except:
                pass
        elif tag_lower == "type":
            parsed.type_classification = content
        elif tag_lower == "role":
            parsed.role = content
        elif tag_lower == "motion_type":
            parsed.motion_type = content
        elif tag_lower == "cruisemp":
            try:
                parsed.cruise_mp = int(content)
            except:
                pass
        elif tag_lower == "engine_type":
            try:
                parsed.engine_type = int(content)
            except:
                pass
        elif tag_lower == "tonnage":
            try:
                parsed.tonnage = float(content)
            except:
                pass
        elif tag_lower == "fueltype":
            parsed.fuel_type = content
        elif tag_lower == "source":
            parsed.source = content
        elif tag_lower == "armor":
            # Armor is a list of numbers, one per line
            armor_values = []
            for aline in content_lines:
                aline = aline.strip()
                if aline:
                    try:
                        armor_values.append(int(aline))
                    except:
                        pass
            parsed.armor = armor_values
        elif "equipment" in tag_lower:
            # e.g., "Body Equipment", "Turret Equipment", etc.
            location_name = tag_name.replace("Equipment", "").strip()
            if not location_name:
                location_name = "Body"
            equipment_items = [line.strip() for line in content_lines if line.strip()]
            parsed.equipment[location_name] = equipment_items
        elif tag_lower == "systemmanufacturers":
            # Parse system manufacturers
            # Format: SYSTEM:Manufacturer Name
            for line in content_lines:
                if ':' in line:
                    parts = line.split(':', 1)
                    sys_type = parts[0].strip()
                    mfg = parts[1].strip()
                    parsed.system_manufacturers[sys_type] = mfg
        elif tag_lower == "manufacturer":
            # Can be comma-separated
            parsed.manufacturer = [m.strip() for m in content.split(',') if m.strip()]
        elif tag_lower == "primaryfactory":
            parsed.factory = [f.strip() for f in content.split(',') if f.strip()]
        elif tag_lower == "overview":
            parsed.overview = content
        elif tag_lower == "capabilities":
            parsed.capabilities = content
        elif tag_lower == "deployment":
            parsed.deployment = content
        elif tag_lower == "history":
            parsed.history = content
        elif tag_lower == "blockversion":
            pass  # metadata, ignore
        else:
            # Unknown tag, could store in a generic dict if needed
            pass
    
    return parsed

# -----------------------------
# Ingestion logic
# -----------------------------

def guess_parsed_type(raw_line: str) -> str:
    """Determine if equipment line is weapon, ammo, or component"""
    if raw_line is None:
        return "unknown"
    t = raw_line.lower()
    
    # Ammo detection
    if "ammo" in t or re.search(r"\b(ammo|ammunition)\b", t):
        return "ammo"
    
    # Weapon detection (common patterns)
    weapon_patterns = [
        r"\b(lrm|srm|ac|laser|ppc|gauss|ml|large|medium|small|mg|machine gun)\b",
        r"\b(autocannon|missile|flamer|cannon)\b"
    ]
    for pattern in weapon_patterns:
        if re.search(pattern, t):
            return "weapon"
    
    # Component/equipment
    if any(kw in t for kw in ["engine", "gyro", "sensor", "heat sink", "case", "armor"]):
        return "component"
    
    # Empty slot
    if raw_line.strip().lower() in {v.lower() for v in EMPTY_TOKEN_VARIANTS}:
        return "empty"
    
    return "unknown"

def ingest_parsed_vehicle(session, parsed: ParsedVehicle, source_filename: str) -> Tuple[int, List[int]]:
    """
    Insert vehicle and create staging rows for equipment.
    Returns (vehicle_id, list_of_staging_ids)
    """
    # Ensure name is present
    name = parsed.name or "UNKNOWN"
    
    # Check for existing vehicle
    existing = None
    if parsed.mul_id:
        existing = session.query(Vehicle).filter(Vehicle.mul_id == parsed.mul_id).first()
    
    if existing:
        vehicle = existing
        # Could optionally update fields here
    else:
        vehicle = Vehicle(
            name=name,
            model=parsed.model,
            mul_id=parsed.mul_id,
            unit_type=parsed.unit_type,
            year=parsed.year,
            original_build_year=parsed.original_build_year,
            type_classification=parsed.type_classification,
            role=parsed.role,
            motion_type=parsed.motion_type,
            cruise_mp=parsed.cruise_mp,
            engine_type=parsed.engine_type,
            tonnage=parsed.tonnage,
            fuel_type=parsed.fuel_type,
            source=parsed.source,
            raw_doc=parsed.raw_text
        )
        session.add(vehicle)
        session.flush()
    
    staging_ids = []
    
    # Create VehicleLocation and staging slots for equipment
    for loc_name, items in parsed.equipment.items():
        loc = VehicleLocation(vehicle_id=vehicle.id, name=loc_name)
        session.add(loc)
        session.flush()
        
        for idx, raw_line in enumerate(items, start=1):
            raw_line = raw_line.strip()
            parsed_name = normalize_token(raw_line)
            parsed_type = guess_parsed_type(raw_line)
            
            s = StagingVehicleSlot(
                file_name=source_filename,
                vehicle_external_id=str(parsed.mul_id) if parsed.mul_id else name,
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
    
    # Store armor values
    armor_locations = ["front", "left", "right", "rear", "turret"]
    for i, points in enumerate(parsed.armor):
        if i < len(armor_locations):
            armor = VehicleArmor(
                vehicle_id=vehicle.id,
                location=armor_locations[i],
                points=points
            )
            session.add(armor)
    
    # Store system manufacturers
    for sys_type, mfg_name in parsed.system_manufacturers.items():
        sys_mfg = VehicleSystemManufacturer(
            vehicle_id=vehicle.id,
            system_type=sys_type,
            manufacturer_name=mfg_name
        )
        session.add(sys_mfg)
    
    # Link to manufacturers
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
            session.execute(vehicle_manufacturer_table.insert().values(
                vehicle_id=vehicle.id, manufacturer_id=m.id
            ))
        except IntegrityError:
            session.rollback()
    
    # Link to factories
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
            session.execute(vehicle_factory_table.insert().values(
                vehicle_id=vehicle.id, factory_id=f.id
            ))
        except IntegrityError:
            session.rollback()
    
    session.flush()
    return vehicle.id, staging_ids

def resolve_vehicle_staging(session):
    """
    Resolve staging_vehicle_slot against Weapon and WeaponAlias.
    Similar to resolve_staging in mtf_ingest_fixed.py
    """
    updated = 0
    
    # Exact matches
    rows = session.query(StagingVehicleSlot).filter(
        StagingVehicleSlot.parsed_type == 'weapon',
        StagingVehicleSlot.parsed_name != None
    ).all()
    
    for s in rows:
        if s.resolved and s.weapon_id:
            continue
        if s.parsed_name is None:
            continue
        
        # Try exact match
        w = session.query(Weapon).filter(Weapon.name == s.parsed_name).one_or_none()
        if w:
            s.weapon_id = w.id
            s.resolved = True
            s.resolution_hint = "exact"
            updated += 1
            continue
        
        # Try alias match
        a = session.query(WeaponAlias).filter(WeaponAlias.alias == s.parsed_name).one_or_none()
        if a:
            s.weapon_id = a.weapon_id
            s.resolved = True
            s.resolution_hint = "alias"
            updated += 1
    
    session.flush()
    
    # Count unresolved
    unresolved = session.query(StagingVehicleSlot).filter(
        StagingVehicleSlot.parsed_type == 'weapon',
        (StagingVehicleSlot.weapon_id == None) | (StagingVehicleSlot.resolved == False)
    ).count()
    
    return updated, unresolved

def finalize_vehicle_slots(session):
    """
    Move resolved staging_vehicle_slot to final vehicle_slot and vehicle_weapon_instance.
    """
    rows = session.query(StagingVehicleSlot).filter(
        StagingVehicleSlot.resolved == True
    ).all()
    
    created_slots = 0
    created_winst = 0
    
    for s in tqdm(rows, desc="finalizing vehicle slots", leave=False):
        # Find vehicle
        vehicle = None
        if s.vehicle_external_id:
            try:
                vid = int(s.vehicle_external_id)
                vehicle = session.query(Vehicle).filter(Vehicle.mul_id == vid).one_or_none()
            except:
                # Try by name
                vehicle = session.query(Vehicle).filter(
                    Vehicle.name == s.vehicle_external_id
                ).first()
        
        if not vehicle:
            continue
        
        # Find or create location
        loc = session.query(VehicleLocation).filter(
            VehicleLocation.vehicle_id == vehicle.id,
            VehicleLocation.name == s.location_name
        ).one_or_none()
        
        if not loc:
            loc = VehicleLocation(vehicle_id=vehicle.id, name=s.location_name)
            session.add(loc)
            session.flush()
        
        # Check if slot already exists
        existing_slot = session.query(VehicleSlot).filter(
            VehicleSlot.location_id == loc.id,
            VehicleSlot.slot_index == s.slot_index
        ).one_or_none()
        
        if existing_slot:
            continue
        
        # Create slot
        note = None
        if s.raw_text and s.raw_text.strip().lower() in {v.lower() for v in EMPTY_TOKEN_VARIANTS}:
            note = "Empty"
        
        slot = VehicleSlot(
            location_id=loc.id,
            slot_index=s.slot_index,
            raw_text=s.raw_text,
            note=note
        )
        session.add(slot)
        session.flush()
        created_slots += 1
        
        # Create weapon instance if weapon resolved
        if s.weapon_id:
            winst = VehicleWeaponInstance(
                slot_id=slot.id,
                weapon_id=s.weapon_id,
                qty=1
            )
            session.add(winst)
            session.flush()
            created_winst += 1
    
    session.flush()
    return created_slots, created_winst

# -----------------------------
# CLI
# -----------------------------

def discover_blk_files(folder: Path) -> List[Path]:
    """Find all .blk files in folder"""
    return sorted([p for p in folder.glob("*.blk")] + [p for p in folder.glob("*.BLK")])

def process_folder(folder: Path, session):
    """Process all BLK files in folder"""
    files = discover_blk_files(folder)
    if not files:
        print("No .blk files found in", folder)
        return
    
    stats = {"files": 0, "staging_rows": 0}
    
    for f in tqdm(files, desc="files"):
        try:
            text = f.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Failed to read {f}: {e}")
            continue
        
        try:
            parsed = parse_blk_text(text)
            vehicle_id, staging_ids = ingest_parsed_vehicle(session, parsed, str(f.name))
            session.commit()
            stats["files"] += 1
            stats["staging_rows"] += len(staging_ids)
        except Exception as e:
            session.rollback()
            print(f"Failed to ingest {f}: {type(e).__name__}: {e}")
    
    return stats

def main():
    parser = argparse.ArgumentParser(
        description="Ingest BattleTech .blk files (vehicles, aerospace, etc.)"
    )
    parser.add_argument("--folder", "-f", type=str, required=True, help="Folder containing .blk files")
    parser.add_argument("--reconcile", action="store_true", help="Resolve staging to weapons")
    parser.add_argument("--finalize", action="store_true", help="Finalize staging to production tables")
    parser.add_argument("--use-postgres", action="store_true", help="Use PostgreSQL")
    
    args = parser.parse_args()
    
    use_postgres = USE_POSTGRES or args.use_postgres
    engine, Session = get_engine_and_session(use_postgres)
    print(f"Connecting to: {engine.url}")
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    session = Session()
    
    folder = Path(args.folder)
    if not folder.exists():
        print("Folder doesn't exist:", folder)
        sys.exit(1)
    
    if not args.reconcile:
        print("Beginning ingest of .blk files from", folder)
        stats = process_folder(folder, session)
        print("Ingest complete:", stats)
        print("Run with --reconcile to resolve weapons, then --finalize to create final slots.")
    else:
        print("Running resolve step...")
        updated, unresolved = resolve_vehicle_staging(session)
        session.commit()
        print(f"Resolved {updated} staging rows; {unresolved} remain unresolved.")
        
        if args.finalize:
            print("Finalizing resolved staging rows...")
            created_slots, created_winst = finalize_vehicle_slots(session)
            session.commit()
            print(f"Created {created_slots} vehicle slots and {created_winst} weapon instances.")
    
    session.close()

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
load_equipment_csv.py

Loads canonical weapons and equipment from CSV files into the database.
Handles normalization and creates aliases to match MTF parser tokens.
"""

import re
import csv
import argparse
from pathlib import Path
from typing import List, Dict, Set
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

# Import from your existing mtf_ingest_fixed.py
from mtf_ingest import (
    Base, Weapon, WeaponAlias, ComponentType, 
    get_engine_and_session, normalize_token,
    SQLITE_FILENAME, USE_POSTGRES, POSTGRES_DSN
)


def normalize_weapon_name(name: str) -> str:
    """
    Normalize weapon name to match parser's normalize_token logic.
    Lowercase, remove punctuation, normalize spaces.
    """
    if not name:
        return ""
    # Remove punctuation except hyphens and spaces
    normalized = re.sub(r"[^\w\s\-]", " ", name)
    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized)
    # Lowercase and strip
    normalized = normalized.strip().lower()
    return normalized


def generate_weapon_aliases(canonical_name: str) -> Set[str]:
    """
    Generate common aliases for a weapon name.
    Examples:
    - "AC 10" -> ["ac 10", "ac10", "autocannon 10"]
    - "LRM 20" -> ["lrm 20", "lrm20", "long range missile 20"]
    - "Laser Large" -> ["laser large", "large laser", "l laser", "ll"]
    """
    aliases = set()
    normalized = normalize_weapon_name(canonical_name)
    aliases.add(normalized)
    
    # Remove all spaces (e.g., "ac 10" -> "ac10")
    no_space = normalized.replace(" ", "")
    if no_space != normalized:
        aliases.add(no_space)
    
    # Common abbreviations and expansions
    expansions = {
        r'\bac\b': ['autocannon', 'ac'],
        r'\blrm\b': ['long range missile', 'lrm'],
        r'\bsrm\b': ['short range missile', 'srm'],
        r'\bppc\b': ['particle projection cannon', 'ppc'],
        r'\ber\b': ['extended range', 'er'],
        r'\blaser\b': ['laser', 'las'],
        r'\blg\b': ['large', 'lg', 'l'],
        r'\bmed\b': ['medium', 'med', 'm'],
        r'\bsm\b': ['small', 'sm', 's'],
        r'\bpulse\b': ['pulse', 'p'],
        r'\bultra\b': ['ultra', 'u'],
        r'\bgauss\b': ['gauss rifle', 'gauss'],
        r'\bmg\b': ['machine gun', 'mg'],
        r'\bflamer\b': ['flamer', 'flame'],
    }
    
    # Generate expansions
    for pattern, replacements in expansions.items():
        for replacement in replacements:
            expanded = re.sub(pattern, replacement, normalized)
            if expanded != normalized:
                aliases.add(expanded)
                # Also try without spaces
                aliases.add(expanded.replace(" ", ""))
    
    # Handle "X-Y" vs "X Y" patterns (e.g., "ac-10" vs "ac 10")
    if '-' in canonical_name:
        aliases.add(normalized.replace('-', ' '))
        aliases.add(normalized.replace('-', ''))
    
    # Handle number patterns
    # "ac 10" -> "ac10", "ac/10", "ac-10"
    num_match = re.search(r'(\D+)\s*(\d+)', normalized)
    if num_match:
        prefix, number = num_match.groups()
        prefix = prefix.strip()
        aliases.add(f"{prefix}{number}")
        aliases.add(f"{prefix} {number}")
        aliases.add(f"{prefix}-{number}")
        aliases.add(f"{prefix}/{number}")
    
    return aliases


def load_is_equipment(session, csv_path: Path) -> Dict[str, int]:
    """
    Load Inner Sphere equipment from battletech_equipment.txt
    Returns mapping of canonical_name -> weapon_id
    """
    weapon_map = {}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            weapon_name = row.get('type', '').strip()
            if not weapon_name:
                continue
            
            # Normalize the canonical name
            canonical_name = normalize_weapon_name(weapon_name)
            
            # Check if weapon already exists
            existing = session.query(Weapon).filter(Weapon.name == canonical_name).first()
            if existing:
                weapon_map[canonical_name] = existing.id
                print(f"  Found existing: {canonical_name}")
                continue
            
            # Create new weapon
            weapon = Weapon(
                name=canonical_name,
                category='IS',  # Inner Sphere
                damage=_parse_int(row.get('dam')),
            )
            session.add(weapon)
            session.flush()
            weapon_map[canonical_name] = weapon.id
            print(f"  Created weapon: {canonical_name} (ID: {weapon.id})")
            
            # Generate and add aliases
            aliases = generate_weapon_aliases(weapon_name)
            for alias in aliases:
                if alias == canonical_name:
                    continue  # Skip the canonical name itself
                
                # Check if alias already exists
                existing_alias = session.query(WeaponAlias).filter(
                    WeaponAlias.alias == alias
                ).first()
                if existing_alias:
                    continue
                
                try:
                    wa = WeaponAlias(alias=alias, weapon_id=weapon.id)
                    session.add(wa)
                    session.flush()
                    print(f"    Added alias: {alias}")
                except IntegrityError:
                    session.rollback()
    
    session.commit()
    return weapon_map


def load_clan_equipment(session, csv_path: Path) -> Dict[str, int]:
    """
    Load Clan equipment from battletech_clan_equipment.txt
    Returns mapping of canonical_name -> weapon_id
    """
    weapon_map = {}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            weapon_name = row.get('cl type', '').strip()
            if not weapon_name:
                continue
            
            # Skip non-weapon items (actuators, legs, etc.)
            if any(skip in weapon_name.lower() for skip in [
                'act', 'leg', 'shoulder', 'case', 'ecm', 'probe', 
                'artemis', 'masc', 'hs', 'heat sink', 'computer'
            ]):
                continue
            
            # Normalize the canonical name
            canonical_name = normalize_weapon_name(weapon_name)
            # Prefix with "cl" to distinguish from IS
            canonical_name = f"cl {canonical_name}"
            
            # Check if weapon already exists
            existing = session.query(Weapon).filter(Weapon.name == canonical_name).first()
            if existing:
                weapon_map[canonical_name] = existing.id
                print(f"  Found existing: {canonical_name}")
                continue
            
            # Create new weapon
            weapon = Weapon(
                name=canonical_name,
                category='Clan',
                damage=_parse_int(row.get('cl dam')),
            )
            session.add(weapon)
            session.flush()
            weapon_map[canonical_name] = weapon.id
            print(f"  Created weapon: {canonical_name} (ID: {weapon.id})")
            
            # Generate and add aliases (including non-prefixed versions)
            aliases = generate_weapon_aliases(weapon_name)
            # Add clan-prefixed versions
            clan_aliases = set()
            for alias in aliases:
                clan_aliases.add(f"cl {alias}")
                clan_aliases.add(f"clan {alias}")
            
            # Also add non-prefixed versions (they might appear in MTF files)
            all_aliases = aliases | clan_aliases
            
            for alias in all_aliases:
                if alias == canonical_name:
                    continue
                
                existing_alias = session.query(WeaponAlias).filter(
                    WeaponAlias.alias == alias
                ).first()
                if existing_alias:
                    continue
                
                try:
                    wa = WeaponAlias(alias=alias, weapon_id=weapon.id)
                    session.add(wa)
                    session.flush()
                    print(f"    Added alias: {alias}")
                except IntegrityError:
                    session.rollback()
    
    session.commit()
    return weapon_map


def load_ammo(session, csv_path: Path) -> Dict[str, int]:
    """
    Load ammunition as component types (not weapons)
    Returns mapping of canonical_name -> component_type_id
    """
    ammo_map = {}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            ammo_name = row.get('ammo type', '').strip()
            if not ammo_name:
                continue
            
            canonical_name = normalize_weapon_name(ammo_name)
            
            # Check if component type already exists
            existing = session.query(ComponentType).filter(
                ComponentType.name == canonical_name
            ).first()
            if existing:
                ammo_map[canonical_name] = existing.id
                print(f"  Found existing ammo: {canonical_name}")
                continue
            
            # Create new component type
            component = ComponentType(
                name=canonical_name,
                category='ammo'
            )
            session.add(component)
            session.flush()
            ammo_map[canonical_name] = component.id
            print(f"  Created ammo: {canonical_name} (ID: {component.id})")
    
    session.commit()
    return ammo_map


def load_engine_tonnage(session, csv_path: Path) -> None:
    """
    Load engine tonnage reference data.
    This could go into a separate table if needed.
    For now, just validate it loads correctly.
    """
    engine_data = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            engine_no = _parse_int(row.get('engine no'))
            eng_tons = _parse_float(row.get('eng tons'))
            if engine_no and eng_tons:
                engine_data.append((engine_no, eng_tons))
    
    print(f"  Loaded {len(engine_data)} engine tonnage entries")


def _parse_int(value) -> int:
    """Parse integer from string, handling various formats"""
    if not value:
        return None
    try:
        # Remove common non-numeric characters
        cleaned = re.sub(r'[^\d\-]', '', str(value))
        if cleaned:
            return int(cleaned)
    except:
        pass
    return None


def _parse_float(value) -> float:
    """Parse float from string"""
    if not value:
        return None
    try:
        return float(str(value).strip())
    except:
        return None


def create_common_aliases(session):
    """
    Create additional common aliases that might not be auto-generated.
    These are based on common MTF file variations.
    """
    common_mappings = {
        # Autocannons
        'autocannon 2': ['ac2', 'ac 2', 'ac/2'],
        'autocannon 5': ['ac5', 'ac 5', 'ac/5'],
        'autocannon 10': ['ac10', 'ac 10', 'ac/10'],
        'autocannon 20': ['ac20', 'ac 20', 'ac/20'],
        'ultra autocannon 5': ['uac5', 'uac 5', 'ultra ac 5'],
        'ultra autocannon 10': ['uac10', 'uac 10', 'ultra ac 10'],
        'ultra autocannon 20': ['uac20', 'uac 20', 'ultra ac 20'],
        
        # Lasers
        'large laser': ['ll', 'l laser', 'large las'],
        'medium laser': ['ml', 'm laser', 'med laser'],
        'small laser': ['sl', 's laser', 'small las'],
        'large pulse laser': ['lpl', 'l pulse', 'large pulse'],
        'medium pulse laser': ['mpl', 'm pulse', 'med pulse'],
        'small pulse laser': ['spl', 's pulse', 'small pulse'],
        
        # Missiles
        'lrm 5': ['lrm5', 'lrm-5'],
        'lrm 10': ['lrm10', 'lrm-10'],
        'lrm 15': ['lrm15', 'lrm-15'],
        'lrm 20': ['lrm20', 'lrm-20'],
        'srm 2': ['srm2', 'srm-2'],
        'srm 4': ['srm4', 'srm-4'],
        'srm 6': ['srm6', 'srm-6'],
        
        # Other
        'gauss rifle': ['gauss', 'g rifle'],
        'machine gun': ['mg', 'm gun'],
        'particle projection cannon': ['ppc'],
    }
    
    print("\nCreating common aliases...")
    for canonical, aliases in common_mappings.items():
        # Find weapon by normalized canonical name
        normalized_canonical = normalize_weapon_name(canonical)
        weapon = session.query(Weapon).filter(
            Weapon.name == normalized_canonical
        ).first()
        
        if not weapon:
            print(f"  Warning: Weapon not found: {normalized_canonical}")
            continue
        
        for alias in aliases:
            normalized_alias = normalize_weapon_name(alias)
            if normalized_alias == normalized_canonical:
                continue
            
            existing = session.query(WeaponAlias).filter(
                WeaponAlias.alias == normalized_alias
            ).first()
            if existing:
                continue
            
            try:
                wa = WeaponAlias(alias=normalized_alias, weapon_id=weapon.id)
                session.add(wa)
                print(f"  Added: {normalized_alias} -> {normalized_canonical}")
            except IntegrityError:
                session.rollback()
    
    session.commit()


def main():
    parser = argparse.ArgumentParser(
        description='Load BattleTech equipment from CSV files into database'
    )
    parser.add_argument(
        '--equipment-csv',
        type=str,
        default='battletech_equipment.txt',
        help='Path to IS equipment CSV (default: battletech_equipment.txt)'
    )
    parser.add_argument(
        '--clan-csv',
        type=str,
        default='battletech_clan_equipment.txt',
        help='Path to Clan equipment CSV (default: battletech_clan_equipment.txt)'
    )
    parser.add_argument(
        '--ammo-csv',
        type=str,
        default='battletech_is_ammo.txt',
        help='Path to ammo CSV (default: battletech_is_ammo.txt)'
    )
    parser.add_argument(
        '--engine-csv',
        type=str,
        default='battletech_engine_tonnage.txt',
        help='Path to engine tonnage CSV (default: battletech_engine_tonnage.txt)'
    )
    parser.add_argument(
        '--use-postgres',
        action='store_true',
        help='Use PostgreSQL instead of SQLite'
    )
    
    args = parser.parse_args()
    
    # Get database connection
    use_postgres = USE_POSTGRES or args.use_postgres
    engine, Session = get_engine_and_session(use_postgres)
    print(f"Connecting to: {engine.url}")
    
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    session = Session()
    
    # Load Inner Sphere equipment
    is_csv = Path(args.equipment_csv)
    if is_csv.exists():
        print(f"\nLoading Inner Sphere equipment from {is_csv}...")
        is_weapons = load_is_equipment(session, is_csv)
        print(f"Loaded {len(is_weapons)} IS weapons")
    else:
        print(f"Warning: {is_csv} not found, skipping IS equipment")
    
    # Load Clan equipment
    clan_csv = Path(args.clan_csv)
    if clan_csv.exists():
        print(f"\nLoading Clan equipment from {clan_csv}...")
        clan_weapons = load_clan_equipment(session, clan_csv)
        print(f"Loaded {len(clan_weapons)} Clan weapons")
    else:
        print(f"Warning: {clan_csv} not found, skipping Clan equipment")
    
    # Load ammunition
    ammo_csv = Path(args.ammo_csv)
    if ammo_csv.exists():
        print(f"\nLoading ammunition from {ammo_csv}...")
        ammo_types = load_ammo(session, ammo_csv)
        print(f"Loaded {len(ammo_types)} ammo types")
    else:
        print(f"Warning: {ammo_csv} not found, skipping ammo")
    
    # Load engine tonnage reference
    engine_csv = Path(args.engine_csv)
    if engine_csv.exists():
        print(f"\nLoading engine tonnage from {engine_csv}...")
        load_engine_tonnage(session, engine_csv)
    else:
        print(f"Warning: {engine_csv} not found, skipping engine data")
    
    # Create additional common aliases
    create_common_aliases(session)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    total_weapons = session.query(Weapon).count()
    total_aliases = session.query(WeaponAlias).count()
    total_components = session.query(ComponentType).count()
    
    print(f"Total weapons: {total_weapons}")
    print(f"Total weapon aliases: {total_aliases}")
    print(f"Total component types: {total_components}")
    print("\nNext steps:")
    print("1. Run mtf_ingest_fixed.py to ingest MTF files")
    print("2. Run with --reconcile to match staging rows to weapons")
    print("3. Run with --finalize to create final slot records")
    
    session.close()


if __name__ == '__main__':
    main()
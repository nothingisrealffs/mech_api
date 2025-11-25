#!/usr/bin/env python3
"""
api.py

FastAPI REST API for BattleTech database.
Provides endpoints for querying mechs, weapons, loadouts, and statistics.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session, joinedload

from mtf_ingest_fixed import (
    get_engine_and_session,
    Mech, Location, Slot, Weapon, WeaponInstance, WeaponAlias,
    ComponentType, Quirk, Manufacturer, Factory,
    StagingSlot, StagingUnresolved,
    USE_POSTGRES, POSTGRES_DSN
)

# Import vehicle models
from blk_ingest import (
    Vehicle, VehicleLocation, VehicleSlot, VehicleWeaponInstance,
    VehicleArmor, VehicleSystemManufacturer, StagingVehicleSlot
)

# Initialize FastAPI
app = FastAPI(
    title="BattleTech Mech Database API",
    description="REST API for querying BattleTech mech data, weapons, and loadouts",
    version="1.0.0"
)

# CORS middleware for web frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database session dependency
engine, SessionLocal = get_engine_and_session(USE_POSTGRES)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================================================
# Response Models (Pydantic schemas for API responses)
# ============================================================================

class WeaponResponse(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    damage: Optional[int] = None
    
    class Config:
        from_attributes = True

class WeaponAliasResponse(BaseModel):
    alias: str
    weapon_name: str
    
    class Config:
        from_attributes = True

class SlotResponse(BaseModel):
    slot_index: int
    raw_text: Optional[str] = None
    weapon: Optional[WeaponResponse] = None
    component_type: Optional[str] = None
    note: Optional[str] = None

class LocationResponse(BaseModel):
    name: str
    slots: List[SlotResponse] = []
    
    class Config:
        from_attributes = True

class QuirkResponse(BaseModel):
    code: str
    description: Optional[str] = None
    
    class Config:
        from_attributes = True

class MechSummary(BaseModel):
    id: int
    chassis: str
    model: Optional[str] = None
    mul_id: Optional[int] = None
    config: Optional[str] = None
    techbase: Optional[str] = None
    era: Optional[str] = None
    role: Optional[str] = None
    
    class Config:
        from_attributes = True

class MechDetail(MechSummary):
    source: Optional[str] = None
    rules_level: Optional[int] = None
    created_at: Optional[datetime] = None
    locations: List[LocationResponse] = []
    quirks: List[QuirkResponse] = []
    manufacturers: List[str] = []
    factories: List[str] = []

class WeaponStatistics(BaseModel):
    weapon_name: str
    total_instances: int
    mech_count: int
    avg_per_mech: float

class MechStatistics(BaseModel):
    total_mechs: int
    total_vehicles: int
    total_weapons: int
    total_locations: int
    total_slots: int
    by_techbase: Dict[str, int]
    by_era: Dict[str, int]
    by_role: Dict[str, int]

class StagingStatus(BaseModel):
    total_staging_slots: int
    resolved: int
    unresolved: int
    resolution_rate: float
    total_vehicle_staging_slots: int
    vehicle_resolved: int
    vehicle_unresolved: int
    vehicle_resolution_rate: float
    top_unresolved: List[Dict[str, Any]]

# ============================================================================
# Health Check
# ============================================================================

@app.get("/")
def root():
    """API root - health check"""
    return {
        "status": "online",
        "api": "BattleTech Mech Database",
        "version": "1.0.0",
        "database": "connected"
    }

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Detailed health check with database statistics"""
    try:
        mech_count = db.query(Mech).count()
        weapon_count = db.query(Weapon).count()
        vehicle_count = db.query(Vehicle).count()
        
        return {
            "status": "healthy",
            "database": "connected",
            "mechs": mech_count,
            "vehicles": vehicle_count,
            "weapons": weapon_count,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# ============================================================================
# Mech Endpoints
# ============================================================================

@app.get("/mechs", response_model=List[MechSummary])
def list_mechs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    chassis: Optional[str] = None,
    techbase: Optional[str] = None,
    era: Optional[str] = None,
    role: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List mechs with optional filtering.
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **chassis**: Filter by chassis name (partial match)
    - **techbase**: Filter by techbase (IS, Clan, Mixed)
    - **era**: Filter by era
    - **role**: Filter by role
    - **search**: Search across chassis and model
    """
    query = db.query(Mech)
    
    # Apply filters
    if chassis:
        query = query.filter(Mech.chassis.ilike(f"%{chassis}%"))
    if techbase:
        query = query.filter(Mech.techbase.ilike(f"%{techbase}%"))
    if era:
        query = query.filter(Mech.era.ilike(f"%{era}%"))
    if role:
        query = query.filter(Mech.role.ilike(f"%{role}%"))
    if search:
        query = query.filter(
            or_(
                Mech.chassis.ilike(f"%{search}%"),
                Mech.model.ilike(f"%{search}%")
            )
        )
    
    # Order and paginate
    mechs = query.order_by(Mech.chassis, Mech.model).offset(skip).limit(limit).all()
    return mechs

@app.get("/mechs/{mech_id}", response_model=MechDetail)
def get_mech(mech_id: int, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific mech including:
    - Full specifications
    - All locations and equipment slots
    - Weapons and components
    - Quirks
    - Manufacturers
    """
    mech = db.query(Mech).options(
        joinedload(Mech.locations).joinedload(Location.slots),
        joinedload(Mech.quirks)
    ).filter(Mech.id == mech_id).first()
    
    if not mech:
        raise HTTPException(status_code=404, detail=f"Mech {mech_id} not found")
    
    # Build detailed response
    locations_data = []
    for loc in sorted(mech.locations, key=lambda l: l.position_order or 0):
        slots_data = []
        for slot in sorted(loc.slots, key=lambda s: s.slot_index):
            # Get weapon if exists
            weapon_inst = db.query(WeaponInstance).filter(
                WeaponInstance.slot_id == slot.id
            ).first()
            
            weapon_data = None
            if weapon_inst and weapon_inst.weapon_id:
                weapon = db.query(Weapon).get(weapon_inst.weapon_id)
                if weapon:
                    weapon_data = WeaponResponse.from_orm(weapon)
            
            # Get component type if exists
            component_name = None
            if slot.component_type_id:
                comp = db.query(ComponentType).get(slot.component_type_id)
                if comp:
                    component_name = comp.name
            
            slots_data.append(SlotResponse(
                slot_index=slot.slot_index,
                raw_text=slot.raw_text,
                weapon=weapon_data,
                component_type=component_name,
                note=slot.note
            ))
        
        locations_data.append(LocationResponse(
            name=loc.name,
            slots=slots_data
        ))
    
    # Get manufacturers
    manufacturers = [m.name for m in db.query(Manufacturer).join(
        Mech.manufacturers
    ).filter(Mech.id == mech_id).all()]
    
    # Get factories
    factories = [f.name for f in db.query(Factory).join(
        Mech.factories
    ).filter(Mech.id == mech_id).all()]
    
    # Get quirks
    quirks_data = [QuirkResponse.from_orm(q) for q in mech.quirks]
    
    return MechDetail(
        id=mech.id,
        chassis=mech.chassis,
        model=mech.model,
        mul_id=mech.mul_id,
        config=mech.config,
        techbase=mech.techbase,
        era=mech.era,
        source=mech.source,
        role=mech.role,
        rules_level=mech.rules_level,
        created_at=mech.created_at,
        locations=locations_data,
        quirks=quirks_data,
        manufacturers=manufacturers,
        factories=factories
    )

@app.get("/mechs/by-mul-id/{mul_id}", response_model=MechDetail)
def get_mech_by_mul_id(mul_id: int, db: Session = Depends(get_db)):
    """Get mech by Master Unit List ID"""
    mech = db.query(Mech).filter(Mech.mul_id == mul_id).first()
    if not mech:
        raise HTTPException(status_code=404, detail=f"Mech with MUL ID {mul_id} not found")
    return get_mech(mech.id, db)

# ============================================================================
# Vehicle Endpoints
# ============================================================================

class VehicleSummary(BaseModel):
    id: int
    name: str
    model: Optional[str] = None
    mul_id: Optional[int] = None
    unit_type: Optional[str] = None
    year: Optional[int] = None
    role: Optional[str] = None
    tonnage: Optional[float] = None
    
    class Config:
        from_attributes = True

class VehicleDetail(VehicleSummary):
    type_classification: Optional[str] = None
    motion_type: Optional[str] = None
    cruise_mp: Optional[int] = None
    engine_type: Optional[int] = None
    fuel_type: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[datetime] = None
    locations: List[LocationResponse] = []
    armor: Dict[str, int] = {}
    manufacturers: List[str] = []
    factories: List[str] = []
    system_manufacturers: Dict[str, str] = {}

@app.get("/vehicles", response_model=List[VehicleSummary])
def list_vehicles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    name: Optional[str] = None,
    unit_type: Optional[str] = None,
    role: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List vehicles with optional filtering.
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **name**: Filter by name (partial match)
    - **unit_type**: Filter by unit type (Tank, VTOL, Aerospace, etc.)
    - **role**: Filter by role
    - **search**: Search across name and model
    """
    query = db.query(Vehicle)
    
    if name:
        query = query.filter(Vehicle.name.ilike(f"%{name}%"))
    if unit_type:
        query = query.filter(Vehicle.unit_type.ilike(f"%{unit_type}%"))
    if role:
        query = query.filter(Vehicle.role.ilike(f"%{role}%"))
    if search:
        query = query.filter(
            or_(
                Vehicle.name.ilike(f"%{search}%"),
                Vehicle.model.ilike(f"%{search}%")
            )
        )
    
    vehicles = query.order_by(Vehicle.name, Vehicle.model).offset(skip).limit(limit).all()
    return vehicles

@app.get("/vehicles/{vehicle_id}", response_model=VehicleDetail)
def get_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific vehicle including:
    - Full specifications
    - All locations and equipment
    - Armor values
    - Manufacturers and factories
    """
    vehicle = db.query(Vehicle).options(
        joinedload(Vehicle.locations).joinedload(VehicleLocation.slots)
    ).filter(Vehicle.id == vehicle_id).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail=f"Vehicle {vehicle_id} not found")
    
    # Build locations
    locations_data = []
    for loc in vehicle.locations:
        slots_data = []
        for slot in sorted(loc.slots, key=lambda s: s.slot_index):
            weapon_inst = db.query(VehicleWeaponInstance).filter(
                VehicleWeaponInstance.slot_id == slot.id
            ).first()
            
            weapon_data = None
            if weapon_inst and weapon_inst.weapon_id:
                weapon = db.query(Weapon).get(weapon_inst.weapon_id)
                if weapon:
                    weapon_data = WeaponResponse.from_orm(weapon)
            
            component_name = None
            if slot.component_type_id:
                comp = db.query(ComponentType).get(slot.component_type_id)
                if comp:
                    component_name = comp.name
            
            slots_data.append(SlotResponse(
                slot_index=slot.slot_index,
                raw_text=slot.raw_text,
                weapon=weapon_data,
                component_type=component_name,
                note=slot.note
            ))
        
        locations_data.append(LocationResponse(
            name=loc.name,
            slots=slots_data
        ))
    
    # Get armor
    armor_dict = {}
    armor_records = db.query(VehicleArmor).filter(
        VehicleArmor.vehicle_id == vehicle_id
    ).all()
    for ar in armor_records:
        armor_dict[ar.location] = ar.points
    
    # Get manufacturers
    manufacturers = [m.name for m in db.query(Manufacturer).join(
        vehicle_manufacturer_table
    ).filter(vehicle_manufacturer_table.c.vehicle_id == vehicle_id).all()]
    
    # Get factories
    factories = [f.name for f in db.query(Factory).join(
        vehicle_factory_table
    ).filter(vehicle_factory_table.c.vehicle_id == vehicle_id).all()]
    
    # Get system manufacturers
    sys_mfg_dict = {}
    sys_mfgs = db.query(VehicleSystemManufacturer).filter(
        VehicleSystemManufacturer.vehicle_id == vehicle_id
    ).all()
    for sm in sys_mfgs:
        sys_mfg_dict[sm.system_type] = sm.manufacturer_name
    
    return VehicleDetail(
        id=vehicle.id,
        name=vehicle.name,
        model=vehicle.model,
        mul_id=vehicle.mul_id,
        unit_type=vehicle.unit_type,
        year=vehicle.year,
        type_classification=vehicle.type_classification,
        role=vehicle.role,
        tonnage=vehicle.tonnage,
        motion_type=vehicle.motion_type,
        cruise_mp=vehicle.cruise_mp,
        engine_type=vehicle.engine_type,
        fuel_type=vehicle.fuel_type,
        source=vehicle.source,
        created_at=vehicle.created_at,
        locations=locations_data,
        armor=armor_dict,
        manufacturers=manufacturers,
        factories=factories,
        system_manufacturers=sys_mfg_dict
    )

@app.get("/vehicles/by-mul-id/{mul_id}", response_model=VehicleDetail)
def get_vehicle_by_mul_id(mul_id: int, db: Session = Depends(get_db)):
    """Get vehicle by Master Unit List ID"""
    vehicle = db.query(Vehicle).filter(Vehicle.mul_id == mul_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail=f"Vehicle with MUL ID {mul_id} not found")
    return get_vehicle(vehicle.id, db)

# ============================================================================
# Weapon Endpoints
# ============================================================================

@app.get("/weapons", response_model=List[WeaponResponse])
def list_weapons(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List all weapons with optional filtering.
    
    - **category**: Filter by category (IS, Clan, etc.)
    - **search**: Search weapon names
    """
    query = db.query(Weapon)
    
    if category:
        query = query.filter(Weapon.category.ilike(f"%{category}%"))
    if search:
        query = query.filter(Weapon.name.ilike(f"%{search}%"))
    
    weapons = query.order_by(Weapon.name).offset(skip).limit(limit).all()
    return weapons

@app.get("/weapons/{weapon_id}", response_model=WeaponResponse)
def get_weapon(weapon_id: int, db: Session = Depends(get_db)):
    """Get detailed weapon information"""
    weapon = db.query(Weapon).filter(Weapon.id == weapon_id).first()
    if not weapon:
        raise HTTPException(status_code=404, detail=f"Weapon {weapon_id} not found")
    return weapon

@app.get("/weapons/{weapon_id}/aliases", response_model=List[str])
def get_weapon_aliases(weapon_id: int, db: Session = Depends(get_db)):
    """Get all aliases for a weapon"""
    weapon = db.query(Weapon).filter(Weapon.id == weapon_id).first()
    if not weapon:
        raise HTTPException(status_code=404, detail=f"Weapon {weapon_id} not found")
    
    aliases = db.query(WeaponAlias.alias).filter(
        WeaponAlias.weapon_id == weapon_id
    ).all()
    return [a[0] for a in aliases]

@app.get("/weapons/{weapon_id}/mechs", response_model=List[MechSummary])
def get_mechs_with_weapon(
    weapon_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get all mechs that mount a specific weapon"""
    weapon = db.query(Weapon).filter(Weapon.id == weapon_id).first()
    if not weapon:
        raise HTTPException(status_code=404, detail=f"Weapon {weapon_id} not found")
    
    mechs = db.query(Mech).join(Location).join(Slot).join(
        WeaponInstance
    ).filter(
        WeaponInstance.weapon_id == weapon_id
    ).distinct().offset(skip).limit(limit).all()
    
    return mechs

@app.get("/weapons/search/{query_text}")
def search_weapons(query_text: str, db: Session = Depends(get_db)):
    """
    Search weapons by name or alias.
    Returns both exact matches and fuzzy matches.
    """
    # Normalize query
    normalized_query = query_text.strip().lower()
    
    # Find by exact name
    exact = db.query(Weapon).filter(
        Weapon.name == normalized_query
    ).first()
    
    # Find by alias
    alias_match = db.query(Weapon).join(WeaponAlias).filter(
        WeaponAlias.alias == normalized_query
    ).first()
    
    # Find by partial match
    partial_matches = db.query(Weapon).filter(
        Weapon.name.ilike(f"%{normalized_query}%")
    ).limit(10).all()
    
    return {
        "query": query_text,
        "normalized": normalized_query,
        "exact_match": WeaponResponse.from_orm(exact) if exact else None,
        "alias_match": WeaponResponse.from_orm(alias_match) if alias_match else None,
        "partial_matches": [WeaponResponse.from_orm(w) for w in partial_matches]
    }

# ============================================================================
# Statistics Endpoints
# ============================================================================

@app.get("/stats/overview", response_model=MechStatistics)
def get_statistics(db: Session = Depends(get_db)):
    """Get overall database statistics"""
    total_mechs = db.query(Mech).count()
    total_vehicles = db.query(Vehicle).count()
    total_weapons = db.query(Weapon).count()
    total_locations = db.query(Location).count() + db.query(VehicleLocation).count()
    total_slots = db.query(Slot).count() + db.query(VehicleSlot).count()
    
    # Breakdown by techbase (mechs only)
    by_techbase = {}
    techbase_counts = db.query(
        Mech.techbase,
        func.count(Mech.id)
    ).group_by(Mech.techbase).all()
    for tb, count in techbase_counts:
        by_techbase[tb or "Unknown"] = count
    
    # Breakdown by era
    by_era = {}
    era_counts = db.query(
        Mech.era,
        func.count(Mech.id)
    ).group_by(Mech.era).all()
    for era, count in era_counts:
        by_era[era or "Unknown"] = count
    
    # Breakdown by role
    by_role = {}
    role_counts = db.query(
        Mech.role,
        func.count(Mech.id)
    ).group_by(Mech.role).all()
    for role, count in role_counts:
        by_role[role or "Unknown"] = count
    
    return MechStatistics(
        total_mechs=total_mechs,
        total_vehicles=total_vehicles,
        total_weapons=total_weapons,
        total_locations=total_locations,
        total_slots=total_slots,
        by_techbase=by_techbase,
        by_era=by_era,
        by_role=by_role
    )

@app.get("/stats/weapons", response_model=List[WeaponStatistics])
def get_weapon_statistics(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get weapon usage statistics.
    Shows most commonly used weapons across all mechs.
    """
    stats = db.query(
        Weapon.name,
        func.count(WeaponInstance.id).label('total_instances'),
        func.count(func.distinct(Mech.id)).label('mech_count')
    ).join(
        WeaponInstance, Weapon.id == WeaponInstance.weapon_id
    ).join(
        Slot, WeaponInstance.slot_id == Slot.id
    ).join(
        Location, Slot.location_id == Location.id
    ).join(
        Mech, Location.mech_id == Mech.id
    ).group_by(
        Weapon.name
    ).order_by(
        func.count(WeaponInstance.id).desc()
    ).limit(limit).all()
    
    results = []
    for name, total, mech_count in stats:
        results.append(WeaponStatistics(
            weapon_name=name,
            total_instances=total,
            mech_count=mech_count,
            avg_per_mech=round(total / mech_count, 2) if mech_count > 0 else 0
        ))
    
    return results

@app.get("/stats/staging", response_model=StagingStatus)
def get_staging_status(db: Session = Depends(get_db)):
    """
    Get staging resolution statistics.
    Shows how well the ingestion/resolution process is working.
    """
    # Mech staging
    total = db.query(StagingSlot).count()
    resolved = db.query(StagingSlot).filter(StagingSlot.resolved == True).count()
    unresolved = total - resolved
    
    # Vehicle staging
    v_total = db.query(StagingVehicleSlot).count()
    v_resolved = db.query(StagingVehicleSlot).filter(StagingVehicleSlot.resolved == True).count()
    v_unresolved = v_total - v_resolved
    
    # Get top unresolved tokens
    top_unresolved = db.query(
        StagingUnresolved.token,
        StagingUnresolved.seen_count,
        StagingUnresolved.sample_raw
    ).order_by(
        StagingUnresolved.seen_count.desc()
    ).limit(20).all()
    
    unresolved_list = [
        {
            "token": token,
            "count": count,
            "sample": sample
        }
        for token, count, sample in top_unresolved
    ]
    
    return StagingStatus(
        total_staging_slots=total,
        resolved=resolved,
        unresolved=unresolved,
        resolution_rate=round(100 * resolved / total, 2) if total > 0 else 0,
        total_vehicle_staging_slots=v_total,
        vehicle_resolved=v_resolved,
        vehicle_unresolved=v_unresolved,
        vehicle_resolution_rate=round(100 * v_resolved / v_total, 2) if v_total > 0 else 0,
        top_unresolved=unresolved_list
    )

# ============================================================================
# Search & Query Endpoints
# ============================================================================

@app.get("/search")
def global_search(
    q: str = Query(..., min_length=2),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Global search across mechs, vehicles, and weapons.
    Returns combined results.
    """
    # Search mechs
    mechs = db.query(Mech).filter(
        or_(
            Mech.chassis.ilike(f"%{q}%"),
            Mech.model.ilike(f"%{q}%")
        )
    ).limit(limit // 3).all()
    
    # Search vehicles
    vehicles = db.query(Vehicle).filter(
        or_(
            Vehicle.name.ilike(f"%{q}%"),
            Vehicle.model.ilike(f"%{q}%")
        )
    ).limit(limit // 3).all()
    
    # Search weapons
    weapons = db.query(Weapon).filter(
        Weapon.name.ilike(f"%{q}%")
    ).limit(limit // 3).all()
    
    return {
        "query": q,
        "mechs": [MechSummary.from_orm(m) for m in mechs],
        "vehicles": [VehicleSummary.from_orm(v) for v in vehicles],
        "weapons": [WeaponResponse.from_orm(w) for w in weapons],
        "total_results": len(mechs) + len(vehicles) + len(weapons)
    }

@app.get("/compare/mechs")
def compare_mechs(
    mech_ids: List[int] = Query(..., description="List of mech IDs to compare"),
    db: Session = Depends(get_db)
):
    """
    Compare multiple mechs side-by-side.
    Returns detailed comparison of specs and loadouts.
    """
    if len(mech_ids) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 mechs for comparison")
    
    mechs_data = []
    for mech_id in mech_ids:
        mech = db.query(Mech).filter(Mech.id == mech_id).first()
        if mech:
            # Get weapon summary
            weapons = db.query(
                Weapon.name,
                func.count(WeaponInstance.id)
            ).join(
                WeaponInstance
            ).join(
                Slot
            ).join(
                Location
            ).filter(
                Location.mech_id == mech_id
            ).group_by(Weapon.name).all()
            
            mechs_data.append({
                "mech": MechSummary.from_orm(mech),
                "weapons": {name: count for name, count in weapons}
            })
    
    return {
        "comparison": mechs_data
    }

# ============================================================================
# Run the API
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

#!/usr/bin/env python3
"""
battletech_manager.py

Main TUI for managing BattleTech database ingestion.
Handles mechs, vehicles, aerospace, battle armor, infantry, and weapons.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box
from rich.text import Text

from sqlalchemy import func
from sqlalchemy.orm import Session

# Import from existing modules
from mtf_ingest_fixed import (
    get_engine_and_session, Mech, Location, Slot, WeaponInstance,
    StagingSlot, StagingUnresolved, Weapon, WeaponAlias, Manufacturer, Factory,
    parse_mtf_text, ingest_parsed_mech, resolve_staging, finalize_slots_from_staging,
    USE_POSTGRES, POSTGRES_DSN
)

from blk_ingest import (
    Vehicle, VehicleLocation, VehicleSlot, VehicleWeaponInstance,
    StagingVehicleSlot, VehicleArmor,
    parse_blk_text, ingest_parsed_vehicle, resolve_vehicle_staging, finalize_vehicle_slots
)

from load_equipment_csv import (
    load_is_equipment, load_clan_equipment, load_ammo, 
    load_engine_tonnage, create_common_aliases
)

console = Console()

# Configuration
DATA_FOLDER = Path("data")
FOLDERS = {
    "mechs": DATA_FOLDER / "mechs",
    "vehicles": DATA_FOLDER / "vehicles",
    "aerospace": DATA_FOLDER / "aerospace",
    "battlearmor": DATA_FOLDER / "battlearmor",
    "infantry": DATA_FOLDER / "infantry",
    "weapons": DATA_FOLDER / "weapons"
}

# ============================================================================
# Database Status Functions
# ============================================================================

def get_database_status(session: Session) -> Dict:
    """Get comprehensive database statistics"""
    status = {
        "mechs": {
            "total": session.query(Mech).count(),
            "staging": session.query(StagingSlot).count(),
            "staging_resolved": session.query(StagingSlot).filter(
                StagingSlot.resolved == True
            ).count(),
            "finalized_slots": session.query(Slot).count(),
            "weapon_instances": session.query(WeaponInstance).count(),
        },
        "vehicles": {
            "total": session.query(Vehicle).count(),
            "staging": session.query(StagingVehicleSlot).count(),
            "staging_resolved": session.query(StagingVehicleSlot).filter(
                StagingVehicleSlot.resolved == True
            ).count(),
            "finalized_slots": session.query(VehicleSlot).count(),
            "weapon_instances": session.query(VehicleWeaponInstance).count(),
        },
        "weapons": {
            "total": session.query(Weapon).count(),
            "aliases": session.query(WeaponAlias).count(),
        },
        "shared": {
            "manufacturers": session.query(Manufacturer).count(),
            "factories": session.query(Factory).count(),
            "unresolved_tokens": session.query(StagingUnresolved).count(),
        }
    }
    
    # Calculate pending transactions
    status["mechs"]["pending"] = (
        status["mechs"]["staging_resolved"] - status["mechs"]["finalized_slots"]
    )
    status["vehicles"]["pending"] = (
        status["vehicles"]["staging_resolved"] - status["vehicles"]["finalized_slots"]
    )
    
    # Calculate resolution rates
    if status["mechs"]["staging"] > 0:
        status["mechs"]["resolution_rate"] = (
            100 * status["mechs"]["staging_resolved"] / status["mechs"]["staging"]
        )
    else:
        status["mechs"]["resolution_rate"] = 0
    
    if status["vehicles"]["staging"] > 0:
        status["vehicles"]["resolution_rate"] = (
            100 * status["vehicles"]["staging_resolved"] / status["vehicles"]["staging"]
        )
    else:
        status["vehicles"]["resolution_rate"] = 0
    
    return status

def get_top_unresolved(session: Session, limit: int = 10) -> List[Tuple]:
    """Get most common unresolved tokens"""
    return session.query(
        StagingUnresolved.token,
        StagingUnresolved.seen_count,
        StagingUnresolved.sample_raw
    ).order_by(
        StagingUnresolved.seen_count.desc()
    ).limit(limit).all()

def get_pending_files(folder: Path, extension: str) -> List[Path]:
    """Get list of files ready for ingestion"""
    if not folder.exists():
        return []
    return sorted(folder.glob(f"*.{extension}"))

# ============================================================================
# Display Functions
# ============================================================================

def display_header():
    """Display application header"""
    console.clear()
    header = Panel(
        "[bold cyan]⚔️  BattleTech Database Manager[/bold cyan]\n"
        "[dim]Unified management for mechs, vehicles, and equipment[/dim]",
        box=box.DOUBLE,
        border_style="cyan"
    )
    console.print(header)
    console.print()

def display_status(status: Dict):
    """Display database status overview"""
    # Mechs table
    mech_table = Table(title="[bold cyan]Mechs (MTF)[/bold cyan]", box=box.ROUNDED)
    mech_table.add_column("Metric", style="yellow")
    mech_table.add_column("Count", justify="right", style="green")
    
    mech_table.add_row("Total Mechs", str(status["mechs"]["total"]))
    mech_table.add_row("Staging Slots", str(status["mechs"]["staging"]))
    mech_table.add_row(
        "Resolved",
        f"{status['mechs']['staging_resolved']} ({status['mechs']['resolution_rate']:.1f}%)"
    )
    mech_table.add_row("Finalized Slots", str(status["mechs"]["finalized_slots"]))
    mech_table.add_row("Weapon Instances", str(status["mechs"]["weapon_instances"]))
    
    if status["mechs"]["pending"] > 0:
        mech_table.add_row(
            "[bold red]⚠ Pending Finalization[/bold red]",
            f"[bold red]{status['mechs']['pending']}[/bold red]"
        )
    
    # Vehicles table
    vehicle_table = Table(title="[bold cyan]Vehicles/Aerospace (BLK)[/bold cyan]", box=box.ROUNDED)
    vehicle_table.add_column("Metric", style="yellow")
    vehicle_table.add_column("Count", justify="right", style="green")
    
    vehicle_table.add_row("Total Vehicles", str(status["vehicles"]["total"]))
    vehicle_table.add_row("Staging Slots", str(status["vehicles"]["staging"]))
    vehicle_table.add_row(
        "Resolved",
        f"{status['vehicles']['staging_resolved']} ({status['vehicles']['resolution_rate']:.1f}%)"
    )
    vehicle_table.add_row("Finalized Slots", str(status["vehicles"]["finalized_slots"]))
    vehicle_table.add_row("Weapon Instances", str(status["vehicles"]["weapon_instances"]))
    
    if status["vehicles"]["pending"] > 0:
        vehicle_table.add_row(
            "[bold red]⚠ Pending Finalization[/bold red]",
            f"[bold red]{status['vehicles']['pending']}[/bold red]"
        )
    
    # Shared resources table
    shared_table = Table(title="[bold cyan]Shared Resources[/bold cyan]", box=box.ROUNDED)
    shared_table.add_column("Resource", style="yellow")
    shared_table.add_column("Count", justify="right", style="green")
    
    shared_table.add_row("Canonical Weapons", str(status["weapons"]["total"]))
    shared_table.add_row("Weapon Aliases", str(status["weapons"]["aliases"]))
    shared_table.add_row("Manufacturers", str(status["shared"]["manufacturers"]))
    shared_table.add_row("Factories", str(status["shared"]["factories"]))
    
    if status["shared"]["unresolved_tokens"] > 0:
        shared_table.add_row(
            "[bold yellow]⚠ Unresolved Tokens[/bold yellow]",
            f"[bold yellow]{status['shared']['unresolved_tokens']}[/bold yellow]"
        )
    
    # Display tables side by side
    console.print(mech_table)
    console.print()
    console.print(vehicle_table)
    console.print()
    console.print(shared_table)
    console.print()

def display_main_menu():
    """Display main menu options"""
    menu = Panel(
        "[bold]Main Menu[/bold]\n\n"
        "[cyan]1.[/cyan] Ingest Data\n"
        "[cyan]2.[/cyan] Resolve Staging (Match Weapons)\n"
        "[cyan]3.[/cyan] Finalize Pending Transactions\n"
        "[cyan]4.[/cyan] View Unresolved Weapons\n"
        "[cyan]5.[/cyan] Load Weapons/Equipment CSVs\n"
        "[cyan]6.[/cyan] Database Status\n"
        "[cyan]7.[/cyan] Start API Server\n"
        "[cyan]0.[/cyan] Exit",
        box=box.ROUNDED,
        border_style="cyan"
    )
    console.print(menu)

def display_ingest_menu():
    """Display ingestion submenu"""
    menu = Panel(
        "[bold]Select Data Type to Ingest[/bold]\n\n"
        "[cyan]1.[/cyan] Mechs (MTF files)\n"
        "[cyan]2.[/cyan] Vehicles (BLK files)\n"
        "[cyan]3.[/cyan] Aerospace (BLK files)\n"
        "[cyan]4.[/cyan] Battle Armor (BLK files)\n"
        "[cyan]5.[/cyan] Infantry (BLK files)\n"
        "[cyan]6.[/cyan] All BLK files (vehicles + aerospace + battle armor + infantry)\n"
        "[cyan]0.[/cyan] Back to Main Menu",
        box=box.ROUNDED,
        border_style="cyan"
    )
    console.print(menu)

def display_unresolved(session: Session, limit: int = 20):
    """Display unresolved weapon tokens"""
    unresolved = get_top_unresolved(session, limit)
    
    if not unresolved:
        console.print("[green]✓ No unresolved tokens![/green]")
        return
    
    table = Table(
        title=f"[bold red]Top {len(unresolved)} Unresolved Weapon Tokens[/bold red]",
        box=box.ROUNDED
    )
    table.add_column("Token", style="yellow", overflow="fold")
    table.add_column("Count", justify="right", style="red")
    table.add_column("Sample", style="dim", overflow="fold")
    
    for token, count, sample in unresolved:
        table.add_row(
            token or "(empty)",
            str(count),
            (sample[:50] + "...") if sample and len(sample) > 50 else (sample or "")
        )
    
    console.print(table)
    console.print()
    console.print(
        "[yellow]💡 Tip:[/yellow] Add weapon aliases to resolve these tokens\n"
        "    Use the API or directly insert into weapon_alias table"
    )

# ============================================================================
# Action Functions
# ============================================================================

def ingest_mtf_files(session: Session, folder: Path) -> Tuple[int, int]:
    """Ingest MTF files from folder"""
    if not folder.exists():
        console.print(f"[red]✗ Folder not found: {folder}[/red]")
        return 0, 0
    
    files = get_pending_files(folder, "mtf") + get_pending_files(folder, "MTF")
    
    if not files:
        console.print(f"[yellow]⚠ No MTF files found in {folder}[/yellow]")
        return 0, 0
    
    console.print(f"[cyan]Found {len(files)} MTF files[/cyan]")
    
    ingested = 0
    staging_created = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Ingesting MTF files...", total=len(files))
        
        for file_path in files:
            try:
                text = file_path.read_text(encoding="utf-8")
                parsed = parse_mtf_text(text)
                mech_id, staging_ids = ingest_parsed_mech(session, parsed, str(file_path.name))
                session.commit()
                ingested += 1
                staging_created += len(staging_ids)
                progress.update(task, advance=1)
            except Exception as e:
                session.rollback()
                console.print(f"[red]✗ Failed to ingest {file_path.name}: {e}[/red]")
    
    console.print(f"[green]✓ Ingested {ingested} mechs, created {staging_created} staging slots[/green]")
    return ingested, staging_created

def ingest_blk_files(session: Session, folder: Path, unit_type: str = None) -> Tuple[int, int]:
    """Ingest BLK files from folder"""
    if not folder.exists():
        console.print(f"[red]✗ Folder not found: {folder}[/red]")
        return 0, 0
    
    files = get_pending_files(folder, "blk") + get_pending_files(folder, "BLK")
    
    if not files:
        console.print(f"[yellow]⚠ No BLK files found in {folder}[/yellow]")
        return 0, 0
    
    console.print(f"[cyan]Found {len(files)} BLK files[/cyan]")
    
    ingested = 0
    staging_created = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task(f"Ingesting {unit_type or 'BLK'} files...", total=len(files))
        
        for file_path in files:
            try:
                text = file_path.read_text(encoding="utf-8")
                parsed = parse_blk_text(text)
                vehicle_id, staging_ids = ingest_parsed_vehicle(session, parsed, str(file_path.name))
                session.commit()
                ingested += 1
                staging_created += len(staging_ids)
                progress.update(task, advance=1)
            except Exception as e:
                session.rollback()
                console.print(f"[red]✗ Failed to ingest {file_path.name}: {e}[/red]")
    
    console.print(f"[green]✓ Ingested {ingested} units, created {staging_created} staging slots[/green]")
    return ingested, staging_created

def resolve_all_staging(session: Session):
    """Resolve both mech and vehicle staging"""
    console.print("[cyan]Resolving mech staging...[/cyan]")
    mech_resolved, mech_unresolved = resolve_staging(session)
    session.commit()
    console.print(
        f"[green]✓ Mechs: Resolved {mech_resolved} slots, "
        f"{mech_unresolved} remain unresolved[/green]"
    )
    
    console.print("[cyan]Resolving vehicle staging...[/cyan]")
    vehicle_resolved, vehicle_unresolved = resolve_vehicle_staging(session)
    session.commit()
    console.print(
        f"[green]✓ Vehicles: Resolved {vehicle_resolved} slots, "
        f"{vehicle_unresolved} remain unresolved[/green]"
    )
    
    total_resolved = mech_resolved + vehicle_resolved
    total_unresolved = mech_unresolved + vehicle_unresolved
    
    console.print()
    console.print(
        f"[bold green]Total: {total_resolved} resolved, "
        f"{total_unresolved} unresolved[/bold green]"
    )

def finalize_all_pending(session: Session):
    """Finalize all pending transactions"""
    console.print("[cyan]Finalizing mech slots...[/cyan]")
    mech_slots, mech_weapons = finalize_slots_from_staging(session)
    session.commit()
    console.print(
        f"[green]✓ Mechs: Created {mech_slots} slots, "
        f"{mech_weapons} weapon instances[/green]"
    )
    
    console.print("[cyan]Finalizing vehicle slots...[/cyan]")
    vehicle_slots, vehicle_weapons = finalize_vehicle_slots(session)
    session.commit()
    console.print(
        f"[green]✓ Vehicles: Created {vehicle_slots} slots, "
        f"{vehicle_weapons} weapon instances[/green]"
    )
    
    total_slots = mech_slots + vehicle_slots
    total_weapons = mech_weapons + vehicle_weapons
    
    console.print()
    console.print(
        f"[bold green]Total: {total_slots} slots finalized, "
        f"{total_weapons} weapon instances created[/bold green]"
    )

def load_all_weapons(session: Session):
    """Load weapons and equipment from CSVs"""
    weapons_folder = FOLDERS["weapons"]
    
    if not weapons_folder.exists():
        console.print(f"[red]✗ Weapons folder not found: {weapons_folder}[/red]")
        console.print("[yellow]Creating weapons folder...[/yellow]")
        weapons_folder.mkdir(parents=True, exist_ok=True)
        console.print(
            f"[yellow]Place CSV files in {weapons_folder}:[/yellow]\n"
            "  - battletech_equipment.txt (IS weapons)\n"
            "  - battletech_clan_equipment.txt (Clan weapons)\n"
            "  - battletech_is_ammo.txt (Ammo types)\n"
            "  - battletech_engine_tonnage.txt (Engine data)"
        )
        return
    
    csv_files = {
        "is_equipment": weapons_folder / "battletech_equipment.txt",
        "clan_equipment": weapons_folder / "battletech_clan_equipment.txt",
        "ammo": weapons_folder / "battletech_is_ammo.txt",
        "engine": weapons_folder / "battletech_engine_tonnage.txt"
    }
    
    found_files = {k: v for k, v in csv_files.items() if v.exists()}
    
    if not found_files:
        console.print(f"[yellow]⚠ No CSV files found in {weapons_folder}[/yellow]")
        return
    
    console.print(f"[cyan]Found {len(found_files)} CSV files[/cyan]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Loading weapons...", total=len(found_files))
        
        if "is_equipment" in found_files:
            console.print("[cyan]Loading Inner Sphere equipment...[/cyan]")
            weapons = load_is_equipment(session, found_files["is_equipment"])
            console.print(f"[green]✓ Loaded {len(weapons)} IS weapons[/green]")
            progress.update(task, advance=1)
        
        if "clan_equipment" in found_files:
            console.print("[cyan]Loading Clan equipment...[/cyan]")
            weapons = load_clan_equipment(session, found_files["clan_equipment"])
            console.print(f"[green]✓ Loaded {len(weapons)} Clan weapons[/green]")
            progress.update(task, advance=1)
        
        if "ammo" in found_files:
            console.print("[cyan]Loading ammunition types...[/cyan]")
            ammo = load_ammo(session, found_files["ammo"])
            console.print(f"[green]✓ Loaded {len(ammo)} ammo types[/green]")
            progress.update(task, advance=1)
        
        if "engine" in found_files:
            console.print("[cyan]Loading engine tonnage data...[/cyan]")
            load_engine_tonnage(session, found_files["engine"])
            console.print("[green]✓ Loaded engine data[/green]")
            progress.update(task, advance=1)
    
    console.print("[cyan]Creating common weapon aliases...[/cyan]")
    create_common_aliases(session)
    console.print("[green]✓ Created common aliases[/green]")
    
    console.print()
    console.print("[bold green]✓ All weapons and equipment loaded successfully[/bold green]")

def start_api_server():
    """Start the FastAPI server"""
    console.print("[cyan]Starting API server...[/cyan]")
    console.print("[yellow]Press Ctrl+C to stop the server[/yellow]")
    console.print()
    
    try:
        import uvicorn
        uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
    except ImportError:
        console.print("[red]✗ uvicorn not installed. Install with: pip install uvicorn[/red]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")

# ============================================================================
# Main Menu Handlers
# ============================================================================

def handle_ingest_menu(session: Session):
    """Handle ingestion submenu"""
    while True:
        display_header()
        display_ingest_menu()
        
        choice = Prompt.ask(
            "\nSelect option",
            choices=["0", "1", "2", "3", "4", "5", "6"],
            default="0"
        )
        
        if choice == "0":
            break
        elif choice == "1":
            console.print("\n[bold cyan]Ingesting Mechs (MTF)[/bold cyan]")
            ingest_mtf_files(session, FOLDERS["mechs"])
            Prompt.ask("\nPress Enter to continue")
        elif choice == "2":
            console.print("\n[bold cyan]Ingesting Vehicles (BLK)[/bold cyan]")
            ingest_blk_files(session, FOLDERS["vehicles"], "vehicles")
            Prompt.ask("\nPress Enter to continue")
        elif choice == "3":
            console.print("\n[bold cyan]Ingesting Aerospace (BLK)[/bold cyan]")
            ingest_blk_files(session, FOLDERS["aerospace"], "aerospace")
            Prompt.ask("\nPress Enter to continue")
        elif choice == "4":
            console.print("\n[bold cyan]Ingesting Battle Armor (BLK)[/bold cyan]")
            ingest_blk_files(session, FOLDERS["battlearmor"], "battle armor")
            Prompt.ask("\nPress Enter to continue")
        elif choice == "5":
            console.print("\n[bold cyan]Ingesting Infantry (BLK)[/bold cyan]")
            ingest_blk_files(session, FOLDERS["infantry"], "infantry")
            Prompt.ask("\nPress Enter to continue")
        elif choice == "6":
            console.print("\n[bold cyan]Ingesting All BLK Files[/bold cyan]")
            for folder_name, folder_path in FOLDERS.items():
                if folder_name in ["vehicles", "aerospace", "battlearmor", "infantry"]:
                    console.print(f"\n[cyan]Processing {folder_name}...[/cyan]")
                    ingest_blk_files(session, folder_path, folder_name)
            Prompt.ask("\nPress Enter to continue")

def main():
    """Main application loop"""
    # Ensure folders exist
    for folder_name, folder_path in FOLDERS.items():
        if not folder_path.exists():
            console.print(f"[yellow]Creating folder: {folder_path}[/yellow]")
            folder_path.mkdir(parents=True, exist_ok=True)
    
    # Connect to database
    try:
        engine, Session = get_engine_and_session(USE_POSTGRES)
        console.print(f"[green]✓ Connected to: {engine.url}[/green]")
        
        # Ensure tables exist
        from mtf_ingest_fixed import Base
        Base.metadata.create_all(bind=engine)
        
    except Exception as e:
        console.print(f"[red]✗ Database connection failed: {e}[/red]")
        sys.exit(1)
    
    session = Session()
    
    # Main loop
    while True:
        try:
            display_header()
            
            # Show status
            status = get_database_status(session)
            display_status(status)
            
            # Show warnings
            warnings = []
            if status["mechs"]["pending"] > 0:
                warnings.append(
                    f"[yellow]⚠ {status['mechs']['pending']} mech slots pending finalization[/yellow]"
                )
            if status["vehicles"]["pending"] > 0:
                warnings.append(
                    f"[yellow]⚠ {status['vehicles']['pending']} vehicle slots pending finalization[/yellow]"
                )
            if status["shared"]["unresolved_tokens"] > 0:
                warnings.append(
                    f"[yellow]⚠ {status['shared']['unresolved_tokens']} unresolved weapon tokens[/yellow]"
                )
            
            if warnings:
                console.print(Panel("\n".join(warnings), title="Warnings", border_style="yellow"))
                console.print()
            
            display_main_menu()
            
            choice = Prompt.ask(
                "\nSelect option",
                choices=["0", "1", "2", "3", "4", "5", "6", "7"],
                default="0"
            )
            
            if choice == "0":
                if Confirm.ask("\n[yellow]Exit application?[/yellow]"):
                    console.print("[cyan]Goodbye![/cyan]")
                    break
            elif choice == "1":
                handle_ingest_menu(session)
            elif choice == "2":
                console.print("\n[bold cyan]Resolving Staging[/bold cyan]")
                resolve_all_staging(session)
                Prompt.ask("\nPress Enter to continue")
            elif choice == "3":
                console.print("\n[bold cyan]Finalizing Pending Transactions[/bold cyan]")
                if status["mechs"]["pending"] == 0 and status["vehicles"]["pending"] == 0:
                    console.print("[yellow]No pending transactions to finalize[/yellow]")
                elif Confirm.ask("\nFinalize all pending transactions?"):
                    finalize_all_pending(session)
                Prompt.ask("\nPress Enter to continue")
            elif choice == "4":
                console.print("\n[bold cyan]Unresolved Weapons[/bold cyan]")
                display_unresolved(session)
                Prompt.ask("\nPress Enter to continue")
            elif choice == "5":
                console.print("\n[bold cyan]Loading Weapons/Equipment[/bold cyan]")
                if Confirm.ask("\nLoad weapons and equipment from CSVs?"):
                    load_all_weapons(session)
                Prompt.ask("\nPress Enter to continue")
            elif choice == "6":
                # Just refresh (status already shown at top of loop)
                pass
            elif choice == "7":
                start_api_server()
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")
            if Confirm.ask("Exit application?"):
                break
        except Exception as e:
            console.print(f"\n[red]✗ Error: {e}[/red]")
            console.print("[yellow]Press Enter to continue[/yellow]")
            input()
    
    session.close()

if __name__ == "__main__":
    main()

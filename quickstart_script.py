#!/usr/bin/env python3
"""
setup.py

Quick setup script for BattleTech Database Manager.
Creates folder structure and provides setup guidance.
"""

import os
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich import box

console = Console()

FOLDERS = [
    "data/mechs",
    "data/vehicles",
    "data/aerospace",
    "data/battlearmor",
    "data/infantry",
    "data/weapons"
]

REQUIRED_FILES = [
    "mtf_ingest_fixed.py",
    "blk_ingest.py",
    "load_equipment_csv.py",
    "api.py",
    "battletech_manager.py",
    "requirements.txt"
]

def check_python_version():
    """Ensure Python 3.8+"""
    if sys.version_info < (3, 8):
        console.print("[red]✗ Python 3.8 or higher is required[/red]")
        console.print(f"[yellow]Current version: {sys.version}[/yellow]")
        return False
    console.print(f"[green]✓ Python {sys.version_info.major}.{sys.version_info.minor} detected[/green]")
    return True

def check_required_files():
    """Check if all required files exist"""
    missing = []
    for file in REQUIRED_FILES:
        if not Path(file).exists():
            missing.append(file)
    
    if missing:
        console.print("[yellow]⚠ Missing files:[/yellow]")
        for f in missing:
            console.print(f"  - {f}")
        return False
    
    console.print("[green]✓ All required files present[/green]")
    return True

def create_folder_structure():
    """Create data folder structure"""
    console.print("\n[cyan]Creating folder structure...[/cyan]")
    
    for folder in FOLDERS:
        path = Path(folder)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            console.print(f"[green]✓ Created: {folder}[/green]")
        else:
            console.print(f"[dim]  Exists: {folder}[/dim]")
    
    console.print("[green]✓ Folder structure ready[/green]")

def check_dependencies():
    """Check if dependencies are installed"""
    console.print("\n[cyan]Checking dependencies...[/cyan]")
    
    required_packages = [
        "sqlalchemy",
        "pydantic",
        "rich",
        "tqdm",
        "fastapi",
        "uvicorn"
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package)
            console.print(f"[green]✓ {package}[/green]")
        except ImportError:
            missing.append(package)
            console.print(f"[red]✗ {package}[/red]")
    
    if missing:
        console.print("\n[yellow]⚠ Missing packages detected[/yellow]")
        if Confirm.ask("Install missing packages now?"):
            install_dependencies()
        else:
            console.print("\n[yellow]Install manually with:[/yellow]")
            console.print("[cyan]pip install -r requirements.txt[/cyan]")
            return False
    else:
        console.print("[green]✓ All dependencies installed[/green]")
    
    return True

def install_dependencies():
    """Install dependencies from requirements.txt"""
    import subprocess
    
    console.print("\n[cyan]Installing dependencies...[/cyan]")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
            capture_output=True,
            text=True
        )
        console.print("[green]✓ Dependencies installed successfully[/green]")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]✗ Installation failed: {e}[/red]")
        console.print(e.stderr)
        return False

def create_sample_readme():
    """Create a quick reference README in data folder"""
    readme_path = Path("data/README.txt")
    
    if readme_path.exists():
        return
    
    content = """BattleTech Database Manager - Data Folder Guide
================================================

Place your files in the appropriate folders:

data/mechs/
  → Place .mtf files here
  → Example: atlas_as7-d.mtf

data/vehicles/
  → Place vehicle .blk files here
  → Example: striker_srm.blk

data/aerospace/
  → Place aerospace .blk files here

data/battlearmor/
  → Place battle armor .blk files here

data/infantry/
  → Place infantry .blk files here

data/weapons/
  → Place weapon/equipment CSV files here
  → Required files:
    - battletech_equipment.txt (Inner Sphere weapons)
    - battletech_clan_equipment.txt (Clan weapons)
    - battletech_is_ammo.txt (Ammunition types)
    - battletech_engine_tonnage.txt (Engine data)

Workflow:
1. Place CSV files in data/weapons/
2. Place MTF/BLK files in appropriate folders
3. Run: python battletech_manager.py
4. Follow the TUI menu to ingest and process data

For detailed instructions, see the main README.md
"""
    
    readme_path.write_text(content)
    console.print(f"[green]✓ Created quick reference: {readme_path}[/green]")

def display_next_steps():
    """Display next steps for user"""
    next_steps = Panel(
        "[bold cyan]Next Steps:[/bold cyan]\n\n"
        "[yellow]1.[/yellow] Place weapon CSV files in [cyan]data/weapons/[/cyan]\n"
        "   Required files:\n"
        "   • battletech_equipment.txt\n"
        "   • battletech_clan_equipment.txt\n"
        "   • battletech_is_ammo.txt\n"
        "   • battletech_engine_tonnage.txt\n\n"
        "[yellow]2.[/yellow] Place MTF files in [cyan]data/mechs/[/cyan]\n\n"
        "[yellow]3.[/yellow] Place BLK files in appropriate folders:\n"
        "   • data/vehicles/\n"
        "   • data/aerospace/\n"
        "   • data/battlearmor/\n"
        "   • data/infantry/\n\n"
        "[yellow]4.[/yellow] Run the main application:\n"
        "   [cyan]python battletech_manager.py[/cyan]\n\n"
        "[yellow]5.[/yellow] In the TUI menu:\n"
        "   • Load Weapons/Equipment (option 5)\n"
        "   • Ingest Data (option 1)\n"
        "   • Resolve Staging (option 2)\n"
        "   • Finalize Transactions (option 3)\n"
        "   • Start API Server (option 7)\n\n"
        "[green]For detailed instructions, see README.md[/green]",
        title="Setup Complete! ⚔️",
        border_style="green",
        box=box.DOUBLE
    )
    
    console.print("\n")
    console.print(next_steps)

def main():
    """Main setup flow"""
    console.print("\n")
    header = Panel(
        "[bold cyan]⚔️  BattleTech Database Manager - Setup[/bold cyan]\n"
        "[dim]Preparing your environment...[/dim]",
        box=box.DOUBLE,
        border_style="cyan"
    )
    console.print(header)
    console.print()
    
    # Check Python version
    if not check_python_version():
        console.print("\n[red]Setup cannot continue[/red]")
        sys.exit(1)
    
    # Check required files
    if not check_required_files():
        console.print("\n[yellow]⚠ Some files are missing[/yellow]")
        console.print("[yellow]Ensure all Python scripts are in the current directory[/yellow]")
        if not Confirm.ask("Continue anyway?"):
            sys.exit(1)
    
    # Check dependencies
    check_dependencies()
    
    # Create folders
    create_folder_structure()
    
    # Create quick reference
    create_sample_readme()
    
    # Display next steps
    display_next_steps()
    
    # Ask if user wants to launch now
    console.print()
    if Confirm.ask("\n[cyan]Launch BattleTech Manager now?[/cyan]"):
        console.print("\n[cyan]Launching...[/cyan]\n")
        try:
            import battletech_manager
            battletech_manager.main()
        except Exception as e:
            console.print(f"[red]✗ Failed to launch: {e}[/red]")
            console.print("[yellow]You can start it manually with:[/yellow]")
            console.print("[cyan]python battletech_manager.py[/cyan]")
    else:
        console.print("\n[cyan]You can start the manager anytime with:[/cyan]")
        console.print("[cyan]python battletech_manager.py[/cyan]")

if __name__ == "__main__":
    main()

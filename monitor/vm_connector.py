"""
Stage 1: Connect to Azure & Read VM State
------------------------------------------
GitHub Copilot Workshop — Building Self-Healing Cloud Systems
"""

import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from rich.console import Console
from rich.table import Table
from rich import print as rprint

# Load environment variables from .env
load_dotenv()

console = Console()

# ------------------------------------------------------------------
# 1. AUTHENTICATE — DefaultAzureCredential picks up `az login` automatically
# ------------------------------------------------------------------
def get_compute_client() -> ComputeManagementClient:
    credential = DefaultAzureCredential()
    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    return ComputeManagementClient(credential, subscription_id)


# ------------------------------------------------------------------
# 2. GET VM POWER STATE — the foundation of self-healing
# ------------------------------------------------------------------
def get_vm_power_state(client: ComputeManagementClient, resource_group: str, vm_name: str) -> str:
    """
    Fetches the current power state of an Azure VM.
    Returns a string like: 'running', 'stopped', 'deallocated'
    """
    instance_view = client.virtual_machines.instance_view(resource_group, vm_name)

    for status in instance_view.statuses:
        # Power state codes look like: "PowerState/running", "PowerState/stopped"
        if status.code.startswith("PowerState/"):
            return status.code.split("/")[1]  # e.g. "running"

    return "unknown"


# ------------------------------------------------------------------
# 3. LIST ALL VMs IN THE RESOURCE GROUP
# ------------------------------------------------------------------
def list_vms(client: ComputeManagementClient, resource_group: str):
    """Lists all VMs and their power states in a resource group."""
    vms = client.virtual_machines.list(resource_group)

    table = Table(title=f"🖥️  Virtual Machines in [{resource_group}]")
    table.add_column("VM Name", style="cyan", no_wrap=True)
    table.add_column("Location", style="magenta")
    table.add_column("Power State", style="bold")

    for vm in vms:
        state = get_vm_power_state(client, resource_group, vm.name)

        # Color-code the power state
        state_display = {
            "running":     f"[green]✅ {state}[/green]",
            "stopped":     f"[yellow]⚠️  {state}[/yellow]",
            "deallocated": f"[red]❌ {state}[/red]",
        }.get(state, f"[white]{state}[/white]")

        table.add_row(vm.name, vm.location, state_display)

    console.print(table)


# ------------------------------------------------------------------
# MAIN — Entry point for Stage 1 demo
# ------------------------------------------------------------------
if __name__ == "__main__":
    resource_group = os.getenv("AZURE_RESOURCE_GROUP")
    vm_name = os.getenv("AZURE_VM_NAME")

    rprint("\n[bold blue]🔌 Connecting to Azure via DefaultAzureCredential...[/bold blue]")
    client = get_compute_client()
    rprint("[green]✅ Connected![/green]\n")

    # Show all VMs in the resource group
    list_vms(client, resource_group)

    # Show detailed state for the target VM
    rprint(f"\n[bold]🔍 Checking power state for VM:[/bold] [cyan]{vm_name}[/cyan]")
    state = get_vm_power_state(client, resource_group, vm_name)
    rprint(f"   Power State → [bold yellow]{state}[/bold yellow]\n")

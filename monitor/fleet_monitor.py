"""
Stage 3: Multi-VM Health Monitor with Auto-Healing
----------------------------------------------------
GitHub Copilot Workshop — Building Self-Healing Cloud Systems

Monitors ALL Virtual Machines in a resource group simultaneously.
Detects failures across any VM and automatically heals them.
"""

import os
import time
import signal
import sys
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from rich.console import Console
from rich.table import Table
from rich import print as rprint

load_dotenv()

console = Console()

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
POLL_INTERVAL   = 30
UNHEALTHY_STATES = {"stopped", "deallocated", "stopping", "unknown"}
RESOURCE_GROUP  = os.getenv("AZURE_RESOURCE_GROUP")
SUBSCRIPTION_ID = os.getenv("AZURE_SUBSCRIPTION_ID")


# ------------------------------------------------------------------
# 1. AUTHENTICATE
# ------------------------------------------------------------------
def get_compute_client() -> ComputeManagementClient:
    credential = DefaultAzureCredential()
    return ComputeManagementClient(credential, SUBSCRIPTION_ID)


# ------------------------------------------------------------------
# 2. LIST ALL VMs IN THE RESOURCE GROUP
# ------------------------------------------------------------------
def list_all_vms(client: ComputeManagementClient) -> list[str]:
    """Returns a list of all VM names in the resource group."""
    vms = client.virtual_machines.list(RESOURCE_GROUP)
    return [vm.name for vm in vms]


# ------------------------------------------------------------------
# 3. CHECK HEALTH OF A SINGLE VM
# ------------------------------------------------------------------
def get_vm_power_state(client: ComputeManagementClient, vm_name: str) -> str:
    """Returns the power state string for a single VM."""
    try:
        instance_view = client.virtual_machines.instance_view(RESOURCE_GROUP, vm_name)
        for status in instance_view.statuses:
            if status.code.startswith("PowerState/"):
                return status.code.split("/")[1]
        return "unknown"
    except Exception as e:
        return "unknown"


# ------------------------------------------------------------------
# 4. HEAL A SINGLE VM
# ------------------------------------------------------------------
def heal_vm(client: ComputeManagementClient, vm_name: str, state: str) -> str:
    """
    Starts a VM that is in an unhealthy state.
    Returns a result message string.
    """
    try:
        poller = client.virtual_machines.begin_start(RESOURCE_GROUP, vm_name)
        poller.result(timeout=120)
        return f"[green]✅ {vm_name} healed successfully[/green]"
    except Exception as e:
        return f"[red]❌ Failed to heal {vm_name}: {e}[/red]"


# ------------------------------------------------------------------
# 5. CHECK AND HEAL ALL VMs IN PARALLEL
# ------------------------------------------------------------------
def check_and_heal_all(client: ComputeManagementClient, vm_names: list[str]) -> dict:
    """
    Checks health of all VMs concurrently using ThreadPoolExecutor.
    Heals any unhealthy VMs in parallel.
    Returns a dict of {vm_name: state}
    """
    states = {}

    # --- parallel health checks ---
    with ThreadPoolExecutor(max_workers=len(vm_names)) as executor:
        future_to_vm = {
            executor.submit(get_vm_power_state, client, vm): vm
            for vm in vm_names
        }
        for future in as_completed(future_to_vm):
            vm_name = future_to_vm[future]
            states[vm_name] = future.result()

    # --- fire heals in background daemon threads (non-blocking) ---
    # We don't wait for them — next poll cycle will confirm recovery
    unhealthy = [vm for vm, state in states.items() if state in UNHEALTHY_STATES]

    for vm in unhealthy:
        t = threading.Thread(
            target=lambda v=vm: rprint(heal_vm(client, v, states[v])),
            daemon=True
        )
        t.start()

    return states


# ------------------------------------------------------------------
# 6. PRINT FLEET STATUS TABLE
# ------------------------------------------------------------------
def print_fleet_status(vm_states: dict, heal_count: int) -> None:
    """Renders a rich table showing the health of all VMs."""
    timestamp = datetime.now().strftime("%H:%M:%S")

    table = Table(title=f"🖥️  Fleet Status  [{timestamp}]  |  Heals: {heal_count}")
    table.add_column("VM Name", style="cyan", no_wrap=True)
    table.add_column("Power State", style="bold")
    table.add_column("Health", justify="center")

    for vm_name, state in sorted(vm_states.items()):
        if state == "running":
            state_display = f"[green]{state}[/green]"
            health = "✅"
        elif state in UNHEALTHY_STATES:
            state_display = f"[red]{state}[/red]"
            health = "❌"
        else:
            state_display = f"[yellow]{state}[/yellow]"
            health = "⚠️"

        table.add_row(vm_name, state_display, health)

    console.print(table)


# ------------------------------------------------------------------
# 7. MONITOR LOOP — watches the entire fleet
# ------------------------------------------------------------------
def run_fleet_monitor(client: ComputeManagementClient) -> None:
    """
    Discovers all VMs in the resource group, then monitors
    and heals the entire fleet every POLL_INTERVAL seconds.
    """
    rprint(f"\n[bold blue]🔍 Discovering VMs in resource group:[/bold blue] [cyan]{RESOURCE_GROUP}[/cyan]")
    vm_names = list_all_vms(client)

    if not vm_names:
        rprint("[red]No VMs found in resource group. Exiting.[/red]")
        return

    rprint(f"[green]Found {len(vm_names)} VM(s):[/green] {', '.join(vm_names)}\n")
    rprint(f"[dim]Polling every {POLL_INTERVAL}s | Unhealthy states: {UNHEALTHY_STATES}[/dim]\n")

    heal_count = 0

    while True:
        vm_states = check_and_heal_all(client, vm_names)

        # count how many were unhealthy this round
        unhealthy_this_round = sum(1 for s in vm_states.values() if s in UNHEALTHY_STATES)
        heal_count += unhealthy_this_round

        print_fleet_status(vm_states, heal_count)

        if unhealthy_this_round > 0:
            rprint(f"[bold yellow]⚡ Auto-healed {unhealthy_this_round} VM(s) this cycle[/bold yellow]\n")

        time.sleep(POLL_INTERVAL)


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
if __name__ == "__main__":
    # Silence noisy ThreadPoolExecutor traceback on Ctrl+C
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    rprint("\n[bold blue]🔌 Connecting to Azure...[/bold blue]")
    client = get_compute_client()
    rprint("[green]✅ Connected![/green]")

    try:
        run_fleet_monitor(client)
    except KeyboardInterrupt:
        rprint("\n\n[bold yellow]🛑 Fleet monitor stopped by user.[/bold yellow]\n")

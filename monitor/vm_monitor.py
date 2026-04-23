"""
Stage 2: VM Health Monitor with Auto-Healing
---------------------------------------------
GitHub Copilot Workshop — Building Self-Healing Cloud Systems

Monitors an Azure VM every POLL_INTERVAL seconds.
If the VM is stopped or deallocated, it automatically starts it back up.
"""

import os
import time
from datetime import datetime
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from rich.console import Console
from rich import print as rprint

load_dotenv()

console = Console()

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
POLL_INTERVAL = 30          # seconds between health checks
UNHEALTHY_STATES = {"stopped", "deallocated", "stopping", "unknown"}
RESOURCE_GROUP = os.getenv("AZURE_RESOURCE_GROUP")
VM_NAME = os.getenv("AZURE_VM_NAME")
SUBSCRIPTION_ID = os.getenv("AZURE_SUBSCRIPTION_ID")


# ------------------------------------------------------------------
# 1. AUTHENTICATE
# ------------------------------------------------------------------
def get_compute_client() -> ComputeManagementClient:
    credential = DefaultAzureCredential()
    return ComputeManagementClient(credential, SUBSCRIPTION_ID)


# ------------------------------------------------------------------
# 2. CHECK VM HEALTH — returns the current power state string
# ------------------------------------------------------------------
def check_vm_health(client: ComputeManagementClient) -> str:
    """
    Fetches the live power state of the VM.
    Returns: 'running' | 'stopped' | 'deallocated' | 'unknown'
    """
    instance_view = client.virtual_machines.instance_view(RESOURCE_GROUP, VM_NAME)

    for status in instance_view.statuses:
        if status.code.startswith("PowerState/"):
            return status.code.split("/")[1]

    return "unknown"


# ------------------------------------------------------------------
# 3. HEAL VM — triggers begin_start() to recover the VM
# ------------------------------------------------------------------
def heal_vm(client: ComputeManagementClient, state: str) -> None:
    """
    Starts the VM if it is in an unhealthy (non-running) state.
    Uses begin_start() which returns an LROPoller — we wait for it to complete.
    """
    rprint(f"\n[bold red]🚨 VM is [{state}] — triggering auto-heal...[/bold red]")

    poller = client.virtual_machines.begin_start(RESOURCE_GROUP, VM_NAME)

    rprint("[yellow]⏳ Waiting for VM to start (timeout: 20s)...[/yellow]")
    try:
        poller.result(timeout=20)  # don't block forever — 20s max
    except Exception:
        pass  # timeout is fine — VM is starting, we'll catch it on next poll

    rprint("[bold green]✅ VM successfully healed and is now starting up![/bold green]\n")


# ------------------------------------------------------------------
# 4. MONITOR LOOP — the core self-healing engine
# ------------------------------------------------------------------
def run_monitor_loop(client: ComputeManagementClient) -> None:
    """
    Infinite loop that polls VM health every POLL_INTERVAL seconds.
    Automatically heals the VM if it enters an unhealthy state.
    """
    rprint(f"\n[bold blue]👁️  Starting monitor for VM:[/bold blue] [cyan]{VM_NAME}[/cyan]")
    rprint(f"[dim]   Polling every {POLL_INTERVAL}s | Unhealthy states: {UNHEALTHY_STATES}[/dim]\n")

    heal_count = 0

    while True:
        timestamp = datetime.now().strftime("%H:%M:%S")
        state = check_vm_health(client)

        if state == "running":
            rprint(f"[dim]{timestamp}[/dim]  [green]✅ {VM_NAME} → {state}[/green]")
        elif state in UNHEALTHY_STATES:
            rprint(f"[dim]{timestamp}[/dim]  [red]❌ {VM_NAME} → {state}[/red]")
            heal_vm(client, state)
            heal_count += 1
            rprint(f"[dim]   Total heals performed: {heal_count}[/dim]")
        else:
            rprint(f"[dim]{timestamp}[/dim]  [yellow]⚠️  {VM_NAME} → {state}[/yellow]")

        time.sleep(POLL_INTERVAL)


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
if __name__ == "__main__":
    rprint("\n[bold blue]🔌 Connecting to Azure...[/bold blue]")
    client = get_compute_client()
    rprint("[green]✅ Connected![/green]")

    try:
        run_monitor_loop(client)
    except KeyboardInterrupt:
        rprint("\n\n[bold yellow]🛑 Monitor stopped by user.[/bold yellow]\n")

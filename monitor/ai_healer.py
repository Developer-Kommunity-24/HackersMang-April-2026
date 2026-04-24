"""
Stage 4: AI-Powered Self-Healing Fleet Monitor
------------------------------------------------
GitHub Copilot Workshop — Building Self-Healing Cloud Systems

Extends Stage 3 fleet monitor with AI intelligence:
  - AI diagnoses WHY a VM failed based on its history
  - AI recommends the best recovery action
  - AI generates a natural language incident report after each heal
  
Uses GitHub Models (gpt-4o) via the OpenAI-compatible inference endpoint.
No Azure OpenAI resource needed — just a GitHub PAT token.
"""

import os
import time
import signal
import sys
import threading
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from openai import OpenAI
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

load_dotenv()

console = Console()

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
POLL_INTERVAL    = 30
UNHEALTHY_STATES = {"stopped", "deallocated", "stopping", "unknown"}
RESOURCE_GROUP   = os.getenv("AZURE_RESOURCE_GROUP")
SUBSCRIPTION_ID  = os.getenv("AZURE_SUBSCRIPTION_ID")
GITHUB_TOKEN     = os.getenv("GITHUB_TOKEN")
GITHUB_MODEL     = os.getenv("GITHUB_MODEL", "gpt-4o")

# Track failure history per VM: {vm_name: [(timestamp, state), ...]}
failure_history: dict[str, list] = defaultdict(list)


# ------------------------------------------------------------------
# 1. CLIENTS — Azure SDK + GitHub Models (OpenAI-compatible)
# ------------------------------------------------------------------
def get_compute_client() -> ComputeManagementClient:
    credential = DefaultAzureCredential()
    return ComputeManagementClient(credential, SUBSCRIPTION_ID)


def get_ai_client() -> OpenAI:
    """
    GitHub Models uses the OpenAI SDK with a custom base_url.
    Your GitHub PAT is the API key — no OpenAI account needed.
    """
    return OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=GITHUB_TOKEN,
    )


# ------------------------------------------------------------------
# 2. AI DIAGNOSIS — asks gpt-4o to analyse the failure
# ------------------------------------------------------------------
def ai_diagnose_failure(ai_client: OpenAI, vm_name: str, state: str) -> tuple[str, str]:
    """
    Sends VM failure context to gpt-4o via GitHub Models.
    Returns (diagnosis, recommended_action) as strings.
    """
    history = failure_history[vm_name]
    history_text = "\n".join(
        f"  - {ts}: {s}" for ts, s in history[-5:]  # last 5 events
    ) or "  - No prior failures recorded this session."

    prompt = f"""You are an Azure cloud reliability engineer analyzing a VM failure.

VM Details:
- Name: {vm_name}
- Resource Group: {RESOURCE_GROUP}
- Current State: {state}
- Failure count this session: {len(history)}
- Recent failure history:
{history_text}

In 2-3 sentences:
1. Diagnose the most likely cause of this failure.
2. Recommend ONE specific recovery action (start, restart, or escalate to human).
3. If failure count > 3, recommend escalation instead of auto-heal.

Respond in this exact JSON format:
{{
  "diagnosis": "<your diagnosis here>",
  "action": "start" | "restart" | "escalate",
  "reason": "<one sentence reason for the action>"
}}"""

    try:
        response = ai_client.chat.completions.create(
            model=GITHUB_MODEL,
            messages=[
                {"role": "system", "content": "You are a concise Azure SRE. Respond only with the requested JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=200,
        )
        import json
        content = response.choices[0].message.content.strip()
        # strip markdown code fences if present
        content = content.replace("```json", "").replace("```", "").strip()
        result = json.loads(content)
        return result.get("diagnosis", "Unknown"), result.get("action", "start"), result.get("reason", "")
    except Exception as e:
        return f"AI diagnosis unavailable: {e}", "start", "Defaulting to start"


# ------------------------------------------------------------------
# 3. AI INCIDENT REPORT — generates a summary after healing
# ------------------------------------------------------------------
def ai_incident_report(ai_client: OpenAI, vm_name: str, state: str, heal_duration_secs: float) -> str:
    """
    After a heal, asks gpt-4o to write a short incident report.
    """
    prompt = f"""Write a short IT incident report (3-4 sentences) for this event:

- VM: {vm_name}
- Resource Group: {RESOURCE_GROUP}
- Failure state detected: {state}
- Auto-recovery triggered at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
- Recovery duration: ~{heal_duration_secs:.0f} seconds
- Total failures this session: {len(failure_history[vm_name])}

Include: what happened, what automated action was taken, outcome, and a recommendation."""

    try:
        response = ai_client.chat.completions.create(
            model=GITHUB_MODEL,
            messages=[
                {"role": "system", "content": "You are a concise IT incident reporter."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Incident report unavailable: {e}"


# ------------------------------------------------------------------
# 4. HEAL WITH AI — diagnose first, then act
# ------------------------------------------------------------------
def ai_heal_vm(compute_client: ComputeManagementClient, ai_client: OpenAI, vm_name: str, state: str) -> None:
    """
    Full AI-powered heal flow:
    1. Record failure in history
    2. Ask AI to diagnose + recommend action
    3. Execute the action
    4. Generate incident report
    """
    # Record this failure
    failure_history[vm_name].append((datetime.now().strftime("%H:%M:%S"), state))
    failure_count = len(failure_history[vm_name])

    rprint(f"\n[bold red]🚨 FAILURE DETECTED:[/bold red] [cyan]{vm_name}[/cyan] → [red]{state}[/red]")
    rprint(f"[dim]   Failures this session: {failure_count}[/dim]")

    # --- AI Diagnosis ---
    rprint("[yellow]🤖 Asking AI to diagnose...[/yellow]")
    diagnosis, action, reason = ai_diagnose_failure(ai_client, vm_name, state)

    console.print(Panel(
        f"[bold]Diagnosis:[/bold] {diagnosis}\n"
        f"[bold]Action:[/bold]    [cyan]{action}[/cyan]\n"
        f"[bold]Reason:[/bold]    {reason}",
        title="🧠 AI Analysis",
        border_style="yellow"
    ))

    # --- Execute recommended action ---
    if action == "escalate":
        rprint(f"[bold red]⚠️  AI recommends ESCALATION — skipping auto-heal for {vm_name}[/bold red]")
        rprint("[dim]   → In production: trigger PagerDuty / Teams alert here[/dim]\n")
        return

    heal_start = time.time()
    rprint(f"[yellow]⏳ Executing [{action}] on {vm_name}...[/yellow]")

    try:
        if action == "restart":
            poller = compute_client.virtual_machines.begin_restart(RESOURCE_GROUP, vm_name)
        else:
            poller = compute_client.virtual_machines.begin_start(RESOURCE_GROUP, vm_name)
        poller.result(timeout=120)
    except Exception as e:
        rprint(f"[red]❌ Heal failed: {e}[/red]\n")
        return

    heal_duration = time.time() - heal_start

    rprint(f"[green]✅ {vm_name} healed in {heal_duration:.0f}s[/green]")

    # --- AI Incident Report ---
    rprint("[yellow]📝 Generating AI incident report...[/yellow]")
    report = ai_incident_report(ai_client, vm_name, state, heal_duration)

    console.print(Panel(
        report,
        title="📋 Incident Report",
        border_style="green"
    ))


# ------------------------------------------------------------------
# 5. VM HEALTH CHECK
# ------------------------------------------------------------------
def get_vm_power_state(client: ComputeManagementClient, vm_name: str) -> str:
    try:
        instance_view = client.virtual_machines.instance_view(RESOURCE_GROUP, vm_name)
        for status in instance_view.statuses:
            if status.code.startswith("PowerState/"):
                return status.code.split("/")[1]
        return "unknown"
    except Exception:
        return "unknown"


def list_all_vms(client: ComputeManagementClient) -> list[str]:
    return [vm.name for vm in client.virtual_machines.list(RESOURCE_GROUP)]


# ------------------------------------------------------------------
# 6. FLEET STATUS TABLE
# ------------------------------------------------------------------
def print_fleet_status(vm_states: dict, total_heals: int) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    table = Table(title=f"🖥️  AI Fleet Monitor  [{timestamp}]  |  Heals: {total_heals}")
    table.add_column("VM Name", style="cyan", no_wrap=True)
    table.add_column("Power State", style="bold")
    table.add_column("Health", justify="center")
    table.add_column("Failures", justify="center", style="dim")

    for vm_name, state in sorted(vm_states.items()):
        failures = len(failure_history[vm_name])
        if state == "running":
            state_display, health = f"[green]{state}[/green]", "✅"
        elif state in UNHEALTHY_STATES:
            state_display, health = f"[red]{state}[/red]", "❌"
        else:
            state_display, health = f"[yellow]{state}[/yellow]", "⚠️"

        table.add_row(vm_name, state_display, health, str(failures) if failures else "-")

    console.print(table)


# ------------------------------------------------------------------
# 7. MAIN MONITOR LOOP
# ------------------------------------------------------------------
def run_ai_fleet_monitor(compute_client: ComputeManagementClient, ai_client: OpenAI) -> None:
    rprint(f"\n[bold blue]🔍 Discovering VMs in:[/bold blue] [cyan]{RESOURCE_GROUP}[/cyan]")
    vm_names = list_all_vms(compute_client)

    if not vm_names:
        rprint("[red]No VMs found. Exiting.[/red]")
        return

    rprint(f"[green]Found {len(vm_names)} VM(s):[/green] {', '.join(vm_names)}")
    rprint(f"[green]AI Model:[/green] {GITHUB_MODEL} via GitHub Models")
    rprint(f"[dim]Polling every {POLL_INTERVAL}s[/dim]\n")

    total_heals = 0

    while True:
        # parallel health checks
        vm_states = {}
        threads = [
            threading.Thread(
                target=lambda v=vm: vm_states.update({v: get_vm_power_state(compute_client, v)}),
                daemon=True
            )
            for vm in vm_names
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        print_fleet_status(vm_states, total_heals)

        # AI heal unhealthy VMs in background threads
        unhealthy = [vm for vm, state in vm_states.items() if state in UNHEALTHY_STATES]
        for vm in unhealthy:
            total_heals += 1
            t = threading.Thread(
                target=ai_heal_vm,
                args=(compute_client, ai_client, vm, vm_states[vm]),
                daemon=True
            )
            t.start()

        time.sleep(POLL_INTERVAL)


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    if not GITHUB_TOKEN or GITHUB_TOKEN == "<your-github-pat-here>":
        rprint("[bold red]❌ GITHUB_TOKEN not set in monitor/.env[/bold red]")
        rprint("[dim]   Get one at: https://github.com/settings/tokens[/dim]")
        sys.exit(1)

    rprint("\n[bold blue]🔌 Connecting to Azure...[/bold blue]")
    compute_client = get_compute_client()
    rprint("[green]✅ Azure connected![/green]")

    rprint(f"[bold blue]🤖 Initializing AI ({GITHUB_MODEL} via GitHub Models)...[/bold blue]")
    ai_client = get_ai_client()
    rprint("[green]✅ AI ready![/green]")

    try:
        run_ai_fleet_monitor(compute_client, ai_client)
    except KeyboardInterrupt:
        rprint("\n\n[bold yellow]🛑 AI Fleet Monitor stopped.[/bold yellow]\n")

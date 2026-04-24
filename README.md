# Building Self-Healing Cloud Systems with GitHub Copilot

> **HackersMang April 2026 Workshop**  
> A hands-on workshop demonstrating how GitHub Copilot accelerates the development of self-healing systems on Azure.

---

## 🏗️ Architecture Overview

```
Local App (Python)
    │
    ├── az login  ──────────────► Azure CLI (DefaultAzureCredential)
    │                                   │
    └── Azure SDK (Python) ────────► ComputeManagementClient
                                        │
                            ┌───────────┴───────────┐
                     List all VMs              Poll every 30s
                            │                       │
                     Parallel health          Detect failures
                       checks                      │
                            └───────────┬───────────┘
                                        │
                               🤖 GitHub Models
                               (gpt-4o via OpenAI SDK)
                                        │
                            ┌───────────┴───────────┐
                       AI Diagnose              AI Incident
                        failure                  Report
                            └───────────┬───────────┘
                                        │
                               begin_start() in
                              background threads
```

---

## 📁 Project Structure

```
HackersMang-April-2026/
├── monitor/
│   ├── vm_connector.py     # Stage 1 — Connect & read VM state
│   ├── vm_monitor.py       # Stage 2 — Single VM health monitor + auto-heal
│   ├── fleet_monitor.py    # Stage 3 — Multi-VM fleet monitor (parallel)
│   ├── ai_healer.py        # Stage 4 — AI-powered diagnosis + incident reports
│   ├── requirements.txt    # Python dependencies
│   └── .env                # Azure config (not committed)
└── README.md
```

---

## ⚙️ Prerequisites

- Python 3.10+
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed
- An active Azure subscription

---

## 🚀 Stage 1 — Connect to Azure & Read VM State

Demonstrates how GitHub Copilot generates the Azure SDK integration to authenticate and fetch live VM power states from Azure.

### What it does

- Authenticates using `DefaultAzureCredential` — automatically picks up `az login` session (no API keys needed)
- Lists all Virtual Machines in the resource group with color-coded power states
- Fetches the detailed power state of a target VM (`running`, `stopped`, `deallocated`)

### Setup

**1. Login to Azure**

```bash
az login
```

**2. Clone the repo and create a virtual environment**

```bash
git clone https://github.com/Developer-Kommunity-24/HackersMang-April-2026.git
cd HackersMang-April-2026
python -m venv .venv
source .venv/bin/activate
```

**3. Install dependencies**

```bash
pip install -r monitor/requirements.txt
```

**4. Configure environment variables**

Create a `monitor/.env` file:

```env
AZURE_SUBSCRIPTION_ID=<your-subscription-id>
AZURE_RESOURCE_GROUP=<your-resource-group>
AZURE_VM_NAME=<your-vm-name>

# Stage 4 only
GITHUB_TOKEN=<your-github-pat>
GITHUB_MODEL=gpt-4o
```

**5. Run Stage 1**

```bash
python monitor/vm_connector.py
```

### Expected Output

```
🔌 Connecting to Azure via DefaultAzureCredential...
✅ Connected!

       🖥️  Virtual Machines in [your-resource-group]
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ VM Name          ┃ Location  ┃ Power State  ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ autoheal-test-vm │ centralus │ ✅ running   │
└──────────────────┴───────────┴──────────────┘

🔍 Checking power state for VM: autoheal-test-vm
   Power State → running
```

### Azure Policy Notes (Corporate Subscriptions)

| Policy | Required Setting |
|--------|-----------------|
| No public IPs on NICs | Set **Public IP** to `None` when creating VM |
| No Premium_LRS disks | Set **OS disk type** to `Standard HDD (Standard_LRS)` |

## 🚀 Stage 2 — VM Health Monitor with Auto-Healing

Continuously polls the target VM every 30 seconds. If it enters an unhealthy state (`stopped`, `deallocated`, `stopping`), it automatically triggers `begin_start()` to recover it.

### What it does

- Infinite polling loop with configurable interval
- Color-coded live health status in the terminal
- Detects `stopped` / `deallocated` / `stopping` states
- Triggers `begin_start()` with a 120s timeout — non-blocking, picks up on next poll if Azure is slow
- Tracks total heals performed per session

### Run Stage 2

```bash
python monitor/vm_monitor.py
```

### Simulate a failure (fast demo — no deallocation)

```bash
az vm stop -g <resource-group> -n <vm-name> --skip-shutdown
```

### Expected Output

```
👁️  Starting monitor for VM: autoheal-test-vm
   Polling every 30s | Unhealthy states: {'stopped', 'deallocated', 'stopping', 'unknown'}

21:00:25  ✅ autoheal-test-vm → running
21:00:58  ❌ autoheal-test-vm → stopped

🚨 VM is [stopped] — triggering auto-heal...
⏳ Waiting for VM to start (timeout: 120s)...
✅ VM successfully healed and is now starting up!

   Total heals performed: 1
21:01:30  ✅ autoheal-test-vm → running
```

### Key Learnings

| Concept | Detail |
|---|---|
| `begin_start()` | Returns an `LROPoller` — Azure long-running operation |
| `poller.result(timeout=120)` | Blocks max 120s, then lets next poll verify state |
| `--skip-shutdown` | Stops VM without deallocating — hardware kept, faster recovery |
| Portal "Stop" button | Always deallocates — use CLI for demos |

---

## 🚀 Stage 3 — Multi-VM Fleet Monitor (Parallel Self-Healing)

Upgrades from single-VM monitoring to watching the **entire resource group fleet**. Discovers all VMs automatically and monitors + heals them in parallel using background threads.

### What it does

- Auto-discovers all VMs in the resource group at startup
- Checks health of all VMs **in parallel** (`ThreadPoolExecutor`)
- Fires `begin_start()` heals in **background daemon threads** — polling loop never blocks
- Renders a live fleet status table every 30 seconds
- Tracks cumulative heal count across the session

### Run Stage 3

```bash
python monitor/fleet_monitor.py
```

### Simulate multi-VM failure (the wow moment)

```bash
# Two terminals at once — take down the whole fleet!
az vm stop -g <resource-group> -n autoheal-test-vm --skip-shutdown
az vm stop -g <resource-group> -n Dynatrace123 --skip-shutdown
```

### Expected Output

```
🔍 Discovering VMs in resource group: rg-cp-darshan-dinesh-bhandary
Found 2 VM(s): Dynatrace123, autoheal-test-vm

 🖥️  Fleet Status  [21:27:58]  |  Heals: 5
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┓
┃ VM Name          ┃ Power State ┃ Health ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━┩
│ Dynatrace123     │ stopped     │   ❌   │
│ autoheal-test-vm │ stopped     │   ❌   │
└──────────────────┴─────────────┴────────┘
⚡ Auto-healed 2 VM(s) this cycle

✅ Dynatrace123 healed successfully
✅ autoheal-test-vm healed successfully

 🖥️  Fleet Status  [21:28:28]  |  Heals: 5
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┓
┃ VM Name          ┃ Power State ┃ Health ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━┩
│ Dynatrace123     │ running     │   ✅   │
│ autoheal-test-vm │ running     │   ✅   │
└──────────────────┴─────────────┴────────┘
```

### Key Learnings

| Concept | Detail |
|---|---|
| `virtual_machines.list()` | Auto-discovers all VMs — no hardcoded names |
| `ThreadPoolExecutor` | Parallel health checks across all VMs simultaneously |
| `daemon=True` threads | Heals run in background — poll loop never blocked |
| Non-blocking design | Polling stays on schedule regardless of Azure LRO speed |

---

## 🚀 Stage 4 — AI-Powered Diagnosis & Incident Reports

Upgrades the fleet monitor with **gpt-4o intelligence** via GitHub Models. Instead of blindly restarting VMs, the system now diagnoses failures, recommends actions, and writes incident reports automatically.

### What it does

- Calls `gpt-4o` via GitHub Models (OpenAI-compatible, free with GitHub PAT)
- **AI diagnoses** the failure based on VM name, state, and failure history
- **AI recommends** the action: `start`, `restart`, or `escalate` (if too many failures)
- **Executes** the recommended action automatically
- **AI writes** a natural language incident report after each heal
- Tracks per-VM failure history across the session

### Run Stage 4

```bash
python monitor/ai_healer.py
```

### Get a GitHub PAT (free, no special scopes needed)

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **Generate new token (classic)**
3. No scopes needed — just create and copy it
4. Add to `monitor/.env` as `GITHUB_TOKEN=ghp_xxxx`

### Expected Output

```
🔌 Connecting to Azure...
✅ Azure connected!
🤖 Initializing AI (gpt-4o via GitHub Models)...
✅ AI ready!

🖥️  AI Fleet Monitor  [14:12:23]  |  Heals: 0
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┓
┃ VM Name          ┃ Power State ┃ Health ┃ Failures ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━┩
│ autoheal-test-vm │ stopped     │   ❌   │    -     │
└──────────────────┴─────────────┴────────┴──────────┘

🚨 FAILURE DETECTED: autoheal-test-vm → stopped
🤖 Asking AI to diagnose...

╭─────────────────── 🧠 AI Analysis ───────────────────╮
│ Diagnosis: VM stopped likely due to OS instability.  │
│ Action:    start                                     │
│ Reason:    First failure — safe to auto-recover.     │
╰──────────────────────────────────────────────────────╯

⏳ Executing [start] on autoheal-test-vm...
✅ autoheal-test-vm healed in 34s
📝 Generating AI incident report...

╭──────────────────── 📋 Incident Report ──────────────╮
│ At 14:12 UTC, autoheal-test-vm entered a stopped     │
│ state. Automated recovery via begin_start() was      │
│ triggered and completed in ~34 seconds. Recommend    │
│ investigating OS crash logs to prevent recurrence.   │
╰──────────────────────────────────────────────────────╯
```

### Key Learnings

| Concept | Detail |
|---|---|
| GitHub Models | Free `gpt-4o` inference using your GitHub PAT |
| OpenAI SDK + `base_url` | Point any OpenAI-compatible client at GitHub Models |
| AI escalation logic | After 3+ failures, AI recommends human escalation |
| Failure history context | AI gets richer diagnosis with each subsequent failure |

---

## 🗺️ Workshop Stages

| Stage | Description | Status |
|-------|-------------|--------|
| **Stage 1** | Connect to Azure & read VM power state | ✅ Done |
| **Stage 2** | Monitoring loop — detect VM failures + auto-heal | ✅ Done |
| **Stage 3** | Multi-VM fleet monitor — parallel self-healing | ✅ Done |
| **Stage 4** | AI-powered diagnosis + incident reports (GitHub Models) | ✅ Done |

---

## 🤝 Contributing

This is a workshop repository for **HackersMang April 2026**.  
Presented by [@darshandineshbhandary](https://github.com/darshan45672)
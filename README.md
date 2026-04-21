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
                                 List / Monitor VM Power State
                                        │
                                 Trigger Recovery Actions
```

---

## 📁 Project Structure

```
HackersMang-April-2026/
├── monitor/
│   ├── vm_connector.py     # Stage 1 — Connect & read VM state
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

---

## 🗺️ Workshop Stages

| Stage | Description | Status |
|-------|-------------|--------|
| **Stage 1** | Connect to Azure & read VM power state | ✅ Done |
| **Stage 2** | Monitoring loop — detect VM failures | 🔜 Coming |
| **Stage 3** | Auto-remediation — restart / heal the VM | 🔜 Coming |

---

## 🤝 Contributing

This is a workshop repository for **HackersMang April 2026**.  
Presented by [@darshandineshbhandary](https://github.com/darshan45672)
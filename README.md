# Intune Device Healer MCP Server

**Enterprise-Grade Device Health Automation & Remediation Platform**

A comprehensive Model Context Protocol (MCP) server that provides AI-powered diagnostics, automated remediation, and monitoring for Windows and macOS devices managed through Microsoft Intune.

---

## 🎯 Overview

**Intune Device Healer** is a production-ready MCP server that enables AI assistants to:

- **Diagnose** hardware and software issues across your device fleet
- **Auto-heal** common problems without human intervention
- **Monitor** device health in real-time
- **Execute** safe fixes automatically, risky ones with approval
- **Support** both Windows and macOS platforms
- **Integrate** seamlessly with Microsoft Intune via Graph API
- **Receive Webhooks** from AtomicWork to automatically trigger diagnostics and remediation

---

## ✨ Key Features

### 🔄 **AtomicWork Webhook Integration**

- Built-in FastAPI webhook listener (`/webhook/ticket`)
- Automatically receives AtomicWork incident tickets
- Translates ticket descriptions to device issue types
- Triggers background Intune remediation and posts analysis back to ticket

### 🔍 **Full Diagnostic Suite**

- Hardware health monitoring (CPU temp, disk SMART, RAM status)
- Operating system integrity checks
- Network connectivity diagnostics
- Application health validation
- Security posture assessment
- Performance profiling

### 🤖 **Automated Remediation**

- **50+ automated fix tools** for common issues
- Safe operations execute automatically
- Intelligent rollback on failure
- Platform-specific optimization (Windows/macOS)

### 🛡️ **Safety Framework**

- Three-tier approval system (auto, semi-auto, manual)
- Pre-flight validation before risky operations
- Comprehensive audit logging
- Automatic restore points
- Rollback capabilities

### 📊 **Monitoring Dashboard**

- Real-time device fleet health
- Issue trend analysis
- Remediation success rates
- Performance metrics
- Compliance tracking

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│         AI Client (Claude, Copilot, etc.)           │
└────────────────────┬────────────────────────────────┘
                     │ MCP Protocol
         ┌───────────┴───────────┐
         ▼                       ▼
┌──────────────────┐    ┌──────────────────┐
│ Diagnostic Engine│    │ Remediation Engine│
│ - Hardware Check │    │ - Auto Fixes      │
│ - Software Check │    │ - Script Executor │
│ - Security Scan  │    │ - Rollback System │
└────────┬─────────┘    └─────────┬─────────┘
         │                        │
         └────────┬───────────────┘
                  │
    ┌─────────────┴──────────────┐
    ▼                            ▼
┌──────────────┐         ┌──────────────┐
│ Windows      │         │ macOS        │
│ Remediation  │         │ Remediation  │
│ Library      │         │ Library      │
└──────┬───────┘         └──────┬───────┘
       │                        │
       └──────────┬─────────────┘
                  │
                  ▼
    ┌──────────────────────────┐
    │   Microsoft Graph API     │
    │   - Intune Management    │
    │   - Device Operations    │
    │   - Script Deployment    │
    └──────────────────────────┘
```

---

## 📦 Installation

### Prerequisites

- **Python 3.10+**
- **Microsoft 365 E3/E5** or **Intune Plan 1/2** license
- **Azure subscription** with admin access
- **Intune-managed devices** (Windows 10/11, macOS 11+)

### Quick Start

1. **Clone the repository**

```bash
git clone <repository-url>
cd intune-device-healer
```

1. **Create virtual environment**

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

1. **Install dependencies**

```bash
pip install -r requirements.txt
```

1. **Configure environment**

```bash
cp .env.example .env
# Edit .env with your Azure credentials
```

1. **Run the Server (MCP + Webhook)**

```bash
python src/server.py
```

*Note: The server runs Uvicorn on port 8000. It exposes `/mcp` for FastMCP clients and `/webhook/ticket` for AtomicWork.*

---

## 🔐 Azure App Registration Setup

### Step 1: Create App Registration

1. Go to [Azure Portal](https://portal.azure.com) → **Azure Active Directory** → **App registrations**
2. Click **New registration**
3. Name: `Intune Device Healer MCP`
4. Supported account types: **Single tenant**
5. Click **Register**

### Step 2: Create Client Secret

1. Navigate to **Certificates & secrets**
2. Click **New client secret**
3. Description: `MCP Server Secret`
4. Expiration: **24 months** (recommended)
5. Click **Add** and **copy the secret value immediately**

### Step 3: Configure API Permissions

Add the following **Application permissions** under **Microsoft Graph**:

#### Device Management (Required)

```
✅ DeviceManagementManagedDevices.ReadWrite.All
✅ DeviceManagementConfiguration.ReadWrite.All
✅ DeviceManagementApps.ReadWrite.All
✅ DeviceManagementServiceConfig.ReadWrite.All
✅ DeviceManagementManagedDevices.PrivilegedOperations.All
```

#### Script Execution (Required)

```
✅ DeviceManagementConfiguration.ReadWrite.All
```

#### Monitoring & Reporting (Required)

```
✅ DeviceManagementServiceConfig.Read.All
✅ Directory.Read.All
```

#### Optional (Enhanced Features)

```
⚪ User.Read.All (for user-device mapping)
⚪ Group.Read.All (for group assignments)
```

**After adding permissions**, click **Grant admin consent for [Your Tenant]**

### Step 4: Copy Credentials

From the **Overview** page, copy:

- **Application (client) ID** → `AZURE_CLIENT_ID`
- **Directory (tenant) ID** → `AZURE_TENANT_ID`
- **Client secret** (from Step 2) → `AZURE_CLIENT_SECRET`

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Azure Authentication
AZURE_CLIENT_ID=your-client-id-here
AZURE_TENANT_ID=your-tenant-id-here
AZURE_CLIENT_SECRET=your-client-secret-here

# Server Configuration
LOG_LEVEL=INFO
MAX_CONCURRENT_OPERATIONS=10
OPERATION_TIMEOUT=600

# Safety Settings
AUTO_FIX_ENABLED=true
REQUIRE_APPROVAL_RISKY_OPS=true
ENABLE_ROLLBACK=true

# Monitoring
ENABLE_METRICS=true
METRICS_RETENTION_DAYS=30
```

### MCP Client Configuration

#### For Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "intune-healer": {
      "command": "python",
      "args": ["/path/to/intune-device-healer/src/server.py"],
      "env": {
        "AZURE_CLIENT_ID": "your-client-id",
        "AZURE_TENANT_ID": "your-tenant-id",
        "AZURE_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

#### For VS Code Copilot

Add to VS Code `settings.json`:

```json
{
  "mcp": {
    "server": {
      "intune-healer": {
        "command": "python",
        "args": ["/path/to/intune-device-healer/src/server.py"],
        "env": {
          "AZURE_CLIENT_ID": "your-client-id",
          "AZURE_TENANT_ID": "your-tenant-id",
          "AZURE_CLIENT_SECRET": "your-client-secret"
        }
      }
    }
  }
}
```

---

## 🛠️ Tool Categories (50+ Tools)

### 🔍 Diagnostic Tools (10 tools)

| Tool | Description | Platforms |
|------|-------------|-----------|
| `diagnose_device_comprehensive` | Full hardware + software health check | Windows, macOS |
| `check_hardware_health` | CPU, RAM, disk, temperature sensors | Windows, macOS |
| `check_os_health` | System files, updates, boot config | Windows, macOS |
| `check_network_health` | Connectivity, DNS, VPN status | Windows, macOS |
| `check_security_posture` | AV, firewall, encryption status | Windows, macOS |
| `check_application_health` | Office, LOB apps status | Windows, macOS |
| `check_performance_metrics` | CPU, RAM, disk usage | Windows, macOS |
| `predict_failures` | AI-powered failure prediction | Windows, macOS |
| `get_device_compliance_status` | Intune compliance check | Windows, macOS |
| `scan_for_issues` | Quick issue detection | Windows, macOS |

### 🪟 Windows Remediation (25 tools)

#### System & Updates

- `fix_windows_updates` - Reset Windows Update components
- `repair_system_files` - Run DISM + SFC
- `fix_boot_configuration` - Repair BCD and boot manager
- `reset_windows_activation` - Fix activation issues

#### Drivers & Hardware

- `update_drivers_auto` - Auto-update all drivers
- `rollback_driver` - Rollback problematic driver
- `fix_audio_driver` - Repair audio issues
- `fix_network_driver` - Repair network adapter

#### Disk & Storage

- `repair_disk_errors` - Run CHKDSK /F /R
- `cleanup_disk_space` - Automated cleanup (10GB+)
- `optimize_disk` - Defrag HDD / TRIM SSD
- `check_disk_smart` - SMART status + prediction

#### Network

- `reset_network_stack` - Full TCP/IP reset
- `fix_vpn_configuration` - Repair VPN profiles
- `repair_dns_settings` - Reset DNS cache
- `fix_wifi_connectivity` - WiFi troubleshooter

#### Applications

- `repair_outlook_pst` - Scan and fix PST files
- `rebuild_outlook_profile` - Recreate profile
- `fix_office_installation` - Repair Office apps
- `reinstall_app` - Reinstall broken app via Intune

#### Performance

- `optimize_startup` - Disable unnecessary startup items
- `fix_high_cpu_usage` - Kill runaway processes
- `clear_temp_files` - Remove temp/cache files
- `optimize_memory` - Fix pagefile settings

#### Security

- `enable_bitlocker` - Enable/repair BitLocker
- `fix_windows_defender` - Repair Defender

### 🍎 macOS Remediation (15 tools)

#### System

- `reset_smc` - Reset System Management Controller
- `reset_nvram` - Reset NVRAM/PRAM
- `repair_disk_permissions` - Fix permissions
- `fix_spotlight_index` - Rebuild Spotlight

#### Network

- `reset_network_settings_mac` - Reset network config
- `fix_vpn_profile_mac` - Repair VPN
- `repair_wifi_mac` - Fix WiFi connectivity

#### Applications

- `fix_outlook_mac` - Repair Outlook for Mac
- `repair_app_permissions_mac` - Fix app permissions
- `clear_app_caches_mac` - Clear app caches

#### Performance

- `optimize_storage_mac` - macOS storage optimization
- `fix_memory_pressure_mac` - Fix memory issues
- `disable_login_items_mac` - Optimize startup

#### Updates

- `force_software_update_mac` - Force update check
- `fix_app_store_mac` - Repair App Store

### 🎯 Automation Tools (5 tools)

| Tool | Description |
|------|-------------|
| `auto_heal_device` | Diagnose + fix all issues automatically |
| `deploy_remediation_script` | Deploy custom PowerShell/Shell scripts |
| `schedule_maintenance` | Schedule recurring fixes |
| `bulk_heal_devices` | Fix multiple devices simultaneously |
| `create_healing_policy` | Create auto-healing policy |

### 📊 Monitoring Tools (5 tools)

| Tool | Description |
|------|-------------|
| `get_fleet_health_dashboard` | Real-time fleet health metrics |
| `get_remediation_history` | View fix history |
| `get_device_health_score` | 0-100 health score per device |
| `get_failure_predictions` | AI-powered failure forecasts |
| `export_health_report` | Generate Excel/PDF reports |

---

## 🚀 Usage Examples

### Example 1: Diagnose Single Device

```python
# AI Assistant prompt:
"Check the full health status of device WIN-LAPTOP-001"

# MCP Tool Call:
diagnose_device_comprehensive(
    device_id="WIN-LAPTOP-001"
)

# Response:
{
  "device_name": "WIN-LAPTOP-001",
  "platform": "Windows",
  "health_score": 72,
  "issues_found": [
    {
      "category": "disk",
      "severity": "high",
      "description": "Disk usage at 95%",
      "auto_fixable": true
    },
    {
      "category": "network",
      "severity": "medium",
      "description": "VPN connection failing",
      "auto_fixable": true
    },
    {
      "category": "outlook",
      "severity": "medium",
      "description": "PST file corruption detected",
      "auto_fixable": true
    }
  ],
  "hardware_health": {
    "cpu_temp": "65C (normal)",
    "disk_smart": "PASSED",
    "ram_errors": 0
  }
}
```

### Example 2: Auto-Heal Device

```python
# AI Assistant prompt:
"Fix all issues on device WIN-LAPTOP-001 automatically"

# MCP Tool Call:
auto_heal_device(
    device_id="WIN-LAPTOP-001",
    auto_approve_safe_fixes=true
)

# Execution:
[✓] Cleaning disk space... (reclaimed 12GB)
[✓] Repairing VPN configuration...
[✓] Scanning PST file...
[✓] Repairing Outlook profile...
[!] Requesting approval for disk repair (CHKDSK)...

# User approves manually

[✓] Running CHKDSK... (completed, 0 errors fixed)
[✓] Device sync triggered
[✓] All fixes applied successfully

# Final health score: 72 → 95
```

### Example 3: Fix VPN Issues Across Fleet

```python
# AI Assistant prompt:
"Find all devices with VPN connection issues and fix them"

# MCP Tool Call:
scan_for_issues(issue_type="vpn")
# Returns 15 devices with VPN problems

bulk_heal_devices(
    device_ids=["device1", "device2", ...],
    fix_types=["vpn"]
)

# Result:
{
  "total_devices": 15,
  "successful_fixes": 14,
  "failed_fixes": 1,
  "details": [...]
}
```

### Example 4: Fleet Health Dashboard

```python
# AI Assistant prompt:
"Show me the health status of all devices"

# MCP Tool Call:
get_fleet_health_dashboard()

# Response:
{
  "total_devices": 250,
  "healthy": 198 (79%),
  "warning": 42 (17%),
  "critical": 10 (4%),
  "top_issues": [
    {"issue": "Disk space low", "count": 35},
    {"issue": "Windows updates pending", "count": 28},
    {"issue": "VPN connectivity", "count": 12}
  ],
  "avg_health_score": 84,
  "devices_needing_attention": [...]
}
```

---

## 🛡️ Safety Features

### Three-Tier Approval System

#### **Tier 1: Automatic (No Approval)**

✅ Safe operations that cannot harm the device:

- Clear cache files
- Flush DNS
- Restart services
- Optimize startup items
- Update definitions (AV, malware)

#### **Tier 2: Semi-Automatic (AI Approval)**

⚠️ Moderate risk operations:

- Driver updates
- System file repairs (DISM, SFC)
- Application reinstalls
- Registry safe-key modifications
- Network resets

#### **Tier 3: Manual Approval Required**

🔴 High-risk operations:

- Disk repairs (CHKDSK, disk utility)
- Boot configuration changes
- Partition operations
- Profile rebuilds
- BitLocker operations

### Rollback Capabilities

Every operation creates a rollback plan:

```python
operation_rollback = {
    "operation": "fix_network_stack",
    "rollback_steps": [
        "restore_network_config_backup",
        "restore_dns_settings",
        "restore_proxy_settings"
    ],
    "backup_location": "C:\\IntuneFixes\\Backups\\network_20260215_1430"
}
```

### Audit Logging

All operations are logged:

```json
{
  "timestamp": "2026-02-15T14:30:45Z",
  "device_id": "WIN-LAPTOP-001",
  "operation": "repair_outlook_pst",
  "initiated_by": "AI Assistant (Claude)",
  "approval_status": "auto_approved",
  "result": "success",
  "duration_seconds": 45,
  "changes_made": [
    "Scanned PST: C:\\Users\\john\\Documents\\Outlook.pst",
    "Fixed 3 corruption errors",
    "Recreated search index"
  ]
}
```

---

## 📊 Monitoring & Reporting

### Real-Time Metrics

- Device health scores (0-100)
- Issue detection rates
- Remediation success rates
- Average fix duration
- Devices by health status

### Alerting

Configure alerts for:

- Critical health scores (<50)
- Failed remediations
- Hardware failure predictions
- Security posture degradation

### Reporting

Generate reports:

- Daily health summary
- Weekly remediation report
- Monthly fleet trends
- Compliance reports

---

## 🔧 Advanced Configuration

### Custom Remediation Scripts

Deploy your own PowerShell/Shell scripts:

```python
deploy_remediation_script(
    name="Custom VPN Fix",
    detection_script="""
        # PowerShell detection script
        $vpn = Get-VpnConnection -Name "Corp VPN"
        if ($vpn.ConnectionStatus -ne "Connected") { exit 1 }
        exit 0
    """,
    remediation_script="""
        # PowerShell remediation script
        Remove-VpnConnection -Name "Corp VPN" -Force
        Add-VpnConnection -Name "Corp VPN" -ServerAddress "vpn.company.com"
    """,
    schedule="daily",
    target_devices=["group:All Windows Devices"]
)
```

### Health Score Customization

Adjust health score weights:

```yaml
health_score_weights:
  disk_space: 20
  os_updates: 15
  security: 25
  network: 15
  applications: 10
  performance: 15
```

---

## 🐛 Troubleshooting

### Common Issues

#### Permission Errors (403)

**Error:** `Application is not authorized to perform this operation`

**Solution:**

1. Verify all Graph API permissions are granted
2. Ensure admin consent is granted
3. Wait 10 minutes for permissions to propagate

#### Script Execution Failures

**Error:** `Script execution failed on device`

**Solution:**

1. Check device is online and Intune-synced
2. Verify device platform matches script type
3. Check Intune script execution logs

#### Authentication Errors

**Error:** `AADSTS7000215: Invalid client secret`

**Solution:**

1. Generate new client secret in Azure Portal
2. Update `AZURE_CLIENT_SECRET` in `.env`
3. Restart MCP server

---

## 📚 Documentation

- **[API Reference](docs/API.md)** - Complete tool documentation
- **[Script Library](docs/SCRIPTS.md)** - All remediation scripts
- **[Best Practices](docs/BEST_PRACTICES.md)** - Deployment guide
- **[Troubleshooting Guide](docs/TROUBLESHOOTING.md)** - Common issues

---

## 🤝 Contributing

Contributions welcome! Areas for enhancement:

- Additional platform support (Linux, ChromeOS)
- More remediation scripts
- Enhanced AI-powered diagnostics
- Custom integrations (ServiceNow, Jira)

---

## 📄 License

MIT License - See [LICENSE](LICENSE) file

---

## 🆘 Support

- **GitHub Issues:** [Report issues](https://github.com/yourusername/intune-device-healer/issues)
- **Documentation:** [Full docs](docs/)
- **Community:** [Discussions](https://github.com/yourusername/intune-device-healer/discussions)

---

## ⚠️ Disclaimer

This tool performs automated system modifications. Always:

- Test in non-production environment first
- Maintain device backups
- Review audit logs regularly
- Follow your organization's change management policies

---

**Built with ❤️ for IT Admins and DevOps Engineers**

*Empowering AI to heal devices autonomously*

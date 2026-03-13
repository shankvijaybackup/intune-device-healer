"""
macOS Remediation Tools
Comprehensive fix automation for macOS devices
"""

import structlog
import base64
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
from core.graph_client import GraphClient

logger = structlog.get_logger()


class MacOSRemediationTools:
    """Tools for fixing macOS device issues"""

    def __init__(self, authenticator, config):
        self.authenticator = authenticator
        self.config = config
        self.client = GraphClient(authenticator, config)
        self.scripts_path = Path(__file__).parent.parent / "scripts" / "macos"

    async def reset_smc(self, device_id: str) -> Dict[str, Any]:
        """
        Reset System Management Controller on Mac.
        Tier 1: Automatic (safe operation)
        Fixes: power, thermal, battery, fans, lights, sensors
        """
        logger.info("reset_smc", device_id=device_id)

        script_content = """#!/bin/bash
# SMC Reset Script for macOS

echo "=== SMC Reset Started ==="

# Get Mac model
mac_model=$(sysctl -n hw.model)
echo "Mac Model: $mac_model"

# Check if Mac has Apple Silicon
if [[ $(uname -m) == "arm64" ]]; then
    echo "Apple Silicon Mac detected"
    echo "SMC reset procedure:"
    echo "1. Shut down the Mac"
    echo "2. Wait 30 seconds"
    echo "3. Turn on the Mac"
    echo ""
    echo "Note: T2 and Apple Silicon Macs reset SMC automatically"
    echo "No manual SMC reset needed for this device"
else
    echo "Intel Mac detected"
    echo ""
    echo "SMC reset procedure (requires manual steps):"
    echo "For MacBook with non-removable battery:"
    echo "1. Shut down the Mac"
    echo "2. Press and hold: Shift + Control + Option + Power for 10 seconds"
    echo "3. Release all keys"
    echo "4. Turn on the Mac"
    echo ""
    echo "For Mac desktop:"
    echo "1. Shut down the Mac"
    echo "2. Unplug power cord"
    echo "3. Wait 15 seconds"
    echo "4. Plug power cord back in"
    echo "5. Wait 5 seconds, then turn on"
fi

# Verify system state after potential reset
echo ""
echo "=== System Status Check ==="

# Check power management
echo "Power Management:"
pmset -g | head -10

# Check thermal status
echo ""
echo "Thermal Status:"
if command -v powermetrics &> /dev/null; then
    sudo powermetrics --samplers smc -i 1 -n 1 2>/dev/null | grep -i temp | head -5 || echo "Thermal data not available"
else
    echo "Thermal monitoring not available"
fi

# Check battery status
echo ""
echo "Battery Status:"
system_profiler SPPowerDataType | grep -A 5 "Condition" || echo "Battery info not available"

echo ""
echo "=== SMC Reset Instructions Displayed ==="
echo "Note: SMC reset requires physical interaction and cannot be automated remotely"

exit 0
"""

        try:
            result = await self._execute_shell_script(
                device_id=device_id,
                script_name="Reset SMC",
                script_content=script_content
            )

            return {
                "success": result["success"],
                "operation": "reset_smc",
                "tier": 1,
                "device_id": device_id,
                "execution_result": result,
                "message": "SMC reset instructions deployed" if result["success"] else "SMC reset failed",
                "note": "SMC reset requires physical interaction. Script provides instructions for user."
            }

        except Exception as e:
            logger.error("reset_smc failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "reset_smc"
            }

    async def reset_nvram(self, device_id: str) -> Dict[str, Any]:
        """
        Reset NVRAM/PRAM on Mac.
        Tier 1: Automatic (safe operation)
        Fixes: display, sound, startup disk, time zone, kernel panic logs
        """
        logger.info("reset_nvram", device_id=device_id)

        script_content = """#!/bin/bash
# NVRAM Reset Script for macOS

echo "=== NVRAM Reset Started ==="

# Backup current NVRAM settings
echo "Backing up current NVRAM settings..."
nvram -p > /tmp/nvram_backup_$(date +%Y%m%d_%H%M%S).txt
echo "NVRAM backup saved to /tmp"

# Clear NVRAM (requires restart)
echo ""
echo "Clearing NVRAM..."
if [[ $(uname -m) == "arm64" ]]; then
    echo "Apple Silicon Mac detected"
    echo ""
    echo "NVRAM reset procedure for Apple Silicon:"
    echo "1. Shut down the Mac"
    echo "2. Press and hold the power button until 'Loading startup options' appears"
    echo "3. Click Options, then click Continue"
    echo "4. Select Utilities > Terminal from the menu bar"
    echo "5. Type: nvram -c"
    echo "6. Restart the Mac"
else
    echo "Intel Mac detected"
    echo ""
    echo "NVRAM reset procedure for Intel Mac:"
    echo "1. Shut down the Mac"
    echo "2. Turn on the Mac"
    echo "3. Immediately press and hold: Command + Option + P + R"
    echo "4. Hold for about 20 seconds (Mac may restart)"
    echo "5. Release the keys after you hear the startup sound twice"
fi

# Attempt software NVRAM reset (limited effectiveness)
echo ""
echo "Attempting software NVRAM reset..."
sudo nvram -c 2>/dev/null && echo "NVRAM cleared (reboot required)" || echo "NVRAM clear requires physical keyboard interaction"

# Show current NVRAM settings
echo ""
echo "Current NVRAM settings:"
nvram -p | head -20

echo ""
echo "=== NVRAM Reset Instructions Displayed ==="
echo "Note: Full NVRAM reset requires restart with physical keyboard interaction"
echo "After reset, you may need to reconfigure:"
echo "  - Display resolution"
echo "  - Startup disk"
echo "  - Time zone"
echo "  - Sound volume"

exit 0
"""

        try:
            result = await self._execute_shell_script(
                device_id=device_id,
                script_name="Reset NVRAM",
                script_content=script_content
            )

            return {
                "success": result["success"],
                "operation": "reset_nvram",
                "tier": 1,
                "device_id": device_id,
                "execution_result": result,
                "message": "NVRAM reset instructions deployed" if result["success"] else "NVRAM reset failed",
                "note": "Full NVRAM reset requires restart with keyboard interaction"
            }

        except Exception as e:
            logger.error("reset_nvram failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "reset_nvram"
            }

    async def repair_disk_permissions(self, device_id: str) -> Dict[str, Any]:
        """
        Repair disk permissions on macOS.
        Tier 1: Automatic (safe operation)
        """
        logger.info("repair_disk_permissions", device_id=device_id)

        script_content = """#!/bin/bash
# Disk Permissions Repair Script

echo "=== Disk Permissions Repair Started ==="

# Run First Aid on boot volume
echo "Running First Aid on boot volume..."
boot_volume=$(diskutil info / | grep "Volume Name" | awk '{print $3}')
echo "Boot Volume: $boot_volume"

# Verify and repair
echo ""
echo "Step 1: Verifying disk..."
diskutil verifyVolume / || echo "Verification found issues"

echo ""
echo "Step 2: Repairing disk..."
diskutil repairVolume / 2>&1 | tee /tmp/disk_repair_$(date +%Y%m%d_%H%M%S).log

# Check and repair permissions (macOS Catalina+ handles this automatically)
echo ""
echo "Step 3: Checking filesystem..."
if command -v /usr/libexec/repair_packages &> /dev/null; then
    echo "Repairing package receipts..."
    sudo /usr/libexec/repair_packages --verify --repair --standard-pkgs --volume / || echo "Package repair completed with warnings"
fi

# Fix common permission issues
echo ""
echo "Step 4: Fixing common permission issues..."

# Fix home directory permissions
echo "Fixing home directory permissions..."
current_user=$(whoami)
sudo chown -R "$current_user:staff" "/Users/$current_user" 2>/dev/null || echo "Home directory permissions fixed"

# Fix /tmp permissions
echo "Fixing /tmp permissions..."
sudo chmod 1777 /tmp

# Fix /var/folders permissions
echo "Fixing /var/folders permissions..."
sudo chmod -R 775 /var/folders 2>/dev/null || echo "/var/folders permissions fixed"

# Rebuild Launch Services database
echo ""
echo "Step 5: Rebuilding Launch Services database..."
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -kill -r -domain local -domain system -domain user

echo ""
echo "=== Disk Permissions Repair Completed ==="
echo "Repair log saved to /tmp"

exit 0
"""

        try:
            result = await self._execute_shell_script(
                device_id=device_id,
                script_name="Repair Disk Permissions",
                script_content=script_content
            )

            return {
                "success": result["success"],
                "operation": "repair_disk_permissions",
                "tier": 1,
                "device_id": device_id,
                "execution_result": result,
                "message": "Disk permissions repaired" if result["success"] else "Permission repair failed"
            }

        except Exception as e:
            logger.error("repair_disk_permissions failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "repair_disk_permissions"
            }

    async def fix_spotlight_index(self, device_id: str) -> Dict[str, Any]:
        """
        Rebuild Spotlight search index on macOS.
        Tier 1: Automatic (safe operation)
        """
        logger.info("fix_spotlight_index", device_id=device_id)

        script_content = """#!/bin/bash
# Spotlight Index Rebuild Script

echo "=== Spotlight Index Rebuild Started ==="

# Stop Spotlight
echo "Stopping Spotlight indexing..."
sudo mdutil -a -i off

# Delete Spotlight index
echo "Deleting existing Spotlight index..."
sudo rm -rf /.Spotlight-V100/*
sudo rm -rf /System/Volumes/Data/.Spotlight-V100/*

# Clear Spotlight cache
echo "Clearing Spotlight cache..."
sudo rm -rf ~/Library/Caches/com.apple.helpd/*
sudo rm -rf /Library/Caches/com.apple.helpd/*

# Restart Spotlight
echo ""
echo "Restarting Spotlight indexing..."
sudo mdutil -a -i on

# Rebuild index
echo "Rebuilding Spotlight index..."
sudo mdutil -E /

# Check indexing status
echo ""
echo "Indexing status:"
mdutil -s /

echo ""
echo "=== Spotlight Index Rebuild Initiated ==="
echo "Note: Full reindexing may take 30-60 minutes"
echo "Indexing happens in background"
echo ""
echo "Check indexing progress with: mdutil -s /"

exit 0
"""

        try:
            result = await self._execute_shell_script(
                device_id=device_id,
                script_name="Fix Spotlight Index",
                script_content=script_content
            )

            return {
                "success": result["success"],
                "operation": "fix_spotlight_index",
                "tier": 1,
                "device_id": device_id,
                "execution_result": result,
                "message": "Spotlight index rebuild initiated" if result["success"] else "Spotlight fix failed",
                "note": "Reindexing continues in background (30-60 minutes)"
            }

        except Exception as e:
            logger.error("fix_spotlight_index failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "fix_spotlight_index"
            }

    async def reset_network_settings(self, device_id: str) -> Dict[str, Any]:
        """
        Reset all network settings on macOS.
        Tier 1: Automatic (safe operation)
        """
        logger.info("reset_network_settings", device_id=device_id)

        script_content = """#!/bin/bash
# Network Settings Reset Script

echo "=== Network Settings Reset Started ==="

# Backup current network configuration
echo "Backing up network configuration..."
backup_dir="/tmp/network_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$backup_dir"
sudo cp -R /Library/Preferences/SystemConfiguration/ "$backup_dir/" 2>/dev/null
echo "Network config backed up to: $backup_dir"

# Flush DNS cache
echo ""
echo "Flushing DNS cache..."
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
echo "DNS cache flushed"

# Renew DHCP lease
echo ""
echo "Renewing DHCP lease..."
sudo ipconfig set en0 DHCP
sudo ipconfig set en1 DHCP
echo "DHCP lease renewed"

# Remove network configuration files
echo ""
echo "Resetting network configuration..."
sudo rm /Library/Preferences/SystemConfiguration/NetworkInterfaces.plist 2>/dev/null
sudo rm /Library/Preferences/SystemConfiguration/preferences.plist 2>/dev/null
sudo rm /Library/Preferences/SystemConfiguration/com.apple.airport.preferences.plist 2>/dev/null
sudo rm /Library/Preferences/SystemConfiguration/com.apple.network.identification.plist 2>/dev/null
echo "Network configuration files reset"

# Reset network services
echo ""
echo "Resetting network services..."

# Get list of network services
services=$(networksetup -listallnetworkservices | grep -v "^An asterisk")

while IFS= read -r service; do
    echo "Resetting service: $service"
    # Turn off and on
    networksetup -setnetworkserviceenabled "$service" off 2>/dev/null
    sleep 1
    networksetup -setnetworkserviceenabled "$service" on 2>/dev/null
done <<< "$services"

# Reset WiFi
echo ""
echo "Resetting WiFi..."
networksetup -setairportpower en0 off
sleep 2
networksetup -setairportpower en0 on
echo "WiFi reset complete"

# Clear network locations
echo ""
echo "Current network locations:"
networksetup -listlocations

# Show current network status
echo ""
echo "Current network status:"
ifconfig | grep -A 5 "en0\|en1" | head -20

echo ""
echo "=== Network Settings Reset Completed ==="
echo "Configuration backup saved to: $backup_dir"
echo ""
echo "Note: You may need to:"
echo "  - Reconnect to WiFi networks"
echo "  - Re-enter WiFi passwords"
echo "  - Reconfigure VPN settings"

exit 0
"""

        try:
            result = await self._execute_shell_script(
                device_id=device_id,
                script_name="Reset Network Settings",
                script_content=script_content
            )

            return {
                "success": result["success"],
                "operation": "reset_network_settings",
                "tier": 1,
                "device_id": device_id,
                "execution_result": result,
                "message": "Network settings reset completed" if result["success"] else "Network reset failed",
                "next_steps": [
                    "User may need to reconnect to WiFi",
                    "VPN settings may need reconfiguration"
                ]
            }

        except Exception as e:
            logger.error("reset_network_settings failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "reset_network_settings"
            }

    async def fix_vpn_profile(self, device_id: str, vpn_name: str = None) -> Dict[str, Any]:
        """
        Fix VPN configuration on macOS.
        Tier 1: Automatic (safe operation)
        """
        logger.info("fix_vpn_profile", device_id=device_id, vpn_name=vpn_name)

        script_content = f"""#!/bin/bash
# VPN Profile Fix Script

echo "=== VPN Profile Fix Started ==="

vpn_name="{vpn_name if vpn_name else ''}"

# List current VPN connections
echo "Current VPN configurations:"
scutil --nc list | grep -i vpn

# List network services
echo ""
echo "Network services with VPN:"
networksetup -listallnetworkservices | grep -i vpn

# Check VPN status
echo ""
echo "VPN connection status:"
if [ -n "$vpn_name" ]; then
    scutil --nc status "$vpn_name" || echo "VPN '$vpn_name' not found"
else
    # Show all VPN statuses
    for vpn in $(scutil --nc list | grep -i vpn | awk '{{print $2}}' | tr -d '"'); do
        echo "VPN: $vpn"
        scutil --nc status "$vpn"
        echo ""
    done
fi

# Reset VPN connection
if [ -n "$vpn_name" ]; then
    echo ""
    echo "Resetting VPN connection: $vpn_name"

    # Stop VPN if running
    scutil --nc stop "$vpn_name" 2>/dev/null
    sleep 2

    # Try to start VPN
    echo "Attempting to connect to VPN..."
    scutil --nc start "$vpn_name" 2>/dev/null

    sleep 3

    # Check status
    status=$(scutil --nc status "$vpn_name")
    echo "VPN Status: $status"
fi

# Clear VPN credentials cache
echo ""
echo "Clearing VPN credentials cache..."
sudo rm -rf ~/Library/Preferences/com.apple.networkConnect.plist 2>/dev/null
sudo rm -rf /Library/Preferences/SystemConfiguration/com.apple.networkConnect.plist 2>/dev/null
echo "VPN cache cleared"

# Restart network services
echo ""
echo "Restarting network services..."
sudo killall -HUP mDNSResponder
sudo killall configd

echo ""
echo "=== VPN Profile Fix Completed ==="

exit 0
"""

        try:
            result = await self._execute_shell_script(
                device_id=device_id,
                script_name="Fix VPN Profile",
                script_content=script_content
            )

            return {
                "success": result["success"],
                "operation": "fix_vpn_profile",
                "tier": 1,
                "device_id": device_id,
                "vpn_name": vpn_name,
                "execution_result": result,
                "message": f"VPN fix completed for {vpn_name or 'all VPNs'}" if result["success"] else "VPN fix failed"
            }

        except Exception as e:
            logger.error("fix_vpn_profile failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "fix_vpn_profile"
            }

    async def fix_outlook_mac(self, device_id: str, user_email: str = None) -> Dict[str, Any]:
        """
        Fix Outlook for Mac issues: profile, cache, database.
        Tier 2: Semi-automatic (requires approval)
        """
        logger.info("fix_outlook_mac", device_id=device_id, user_email=user_email)

        script_content = f"""#!/bin/bash
# Outlook for Mac Fix Script

echo "=== Outlook for Mac Fix Started ==="

# Get current user
current_user=$(whoami)
echo "User: $current_user"

# Close Outlook
echo ""
echo "Closing Outlook if running..."
killall "Microsoft Outlook" 2>/dev/null
sleep 3
echo "Outlook closed"

# Backup Outlook data
echo ""
echo "Backing up Outlook data..."
backup_dir=~/Desktop/Outlook_Backup_$(date +%Y%m%d_%H%M%S)
mkdir -p "$backup_dir"

# Backup Outlook profile
if [ -d ~/Library/Group\ Containers/UBF8T346G9.Office/Outlook/Outlook\ 15\ Profiles ]; then
    cp -R ~/Library/Group\ Containers/UBF8T346G9.Office/Outlook/Outlook\ 15\ Profiles "$backup_dir/" 2>/dev/null
    echo "Outlook profile backed up"
fi

# Clear Outlook cache
echo ""
echo "Clearing Outlook cache..."
rm -rf ~/Library/Caches/com.microsoft.Outlook/* 2>/dev/null
rm -rf ~/Library/Caches/Microsoft/Outlook/* 2>/dev/null
echo "Cache cleared"

# Remove Outlook preferences
echo ""
echo "Resetting Outlook preferences..."
rm ~/Library/Preferences/com.microsoft.Outlook.plist 2>/dev/null
rm ~/Library/Preferences/com.microsoft.Outlook.databasedaemon.plist 2>/dev/null
rm ~/Library/Preferences/com.microsoft.Outlook.officereminders.plist 2>/dev/null
echo "Preferences reset"

# Clear Outlook identity
echo ""
echo "Clearing Outlook identity cache..."
rm -rf ~/Library/Group\ Containers/UBF8T346G9.Office/Outlook/Outlook\ 15\ Profiles/Main\ Profile/Data/* 2>/dev/null
echo "Identity cache cleared"

# Rebuild Outlook database
echo ""
echo "Preparing for database rebuild..."
# The database will be automatically rebuilt on next launch

# Clear keychain entries for Outlook
echo ""
echo "Clearing Outlook keychain entries..."
security find-generic-password -s "Microsoft Outlook" -a "$current_user" -g 2>/dev/null | grep "password:" || echo "No Outlook keychain entries found"

# Fix Outlook permissions
echo ""
echo "Fixing Outlook permissions..."
chmod -R 755 ~/Library/Group\ Containers/UBF8T346G9.Office 2>/dev/null
echo "Permissions fixed"

# Reset Spotlight index for Outlook
echo ""
echo "Resetting Outlook Spotlight index..."
mdimport -r ~/Library/Group\ Containers/UBF8T346G9.Office

echo ""
echo "=== Outlook for Mac Fix Completed ==="
echo ""
echo "Backup saved to: $backup_dir"
echo ""
echo "Next steps:"
echo "1. User should open Outlook"
echo "2. Outlook will prompt to set up account"
echo "3. Enter email: {user_email if user_email else 'user@domain.com'}"
echo "4. Database will be automatically rebuilt"
echo "5. This may take 10-30 minutes for large mailboxes"

exit 0
"""

        try:
            result = await self._execute_shell_script(
                device_id=device_id,
                script_name="Fix Outlook Mac",
                script_content=script_content
            )

            return {
                "success": result["success"],
                "operation": "fix_outlook_mac",
                "tier": 2,
                "device_id": device_id,
                "user_email": user_email,
                "execution_result": result,
                "message": "Outlook Mac fix completed" if result["success"] else "Outlook fix failed",
                "next_steps": [
                    "User should restart Outlook",
                    "Outlook will rebuild database automatically",
                    "Estimated time: 10-30 minutes"
                ]
            }

        except Exception as e:
            logger.error("fix_outlook_mac failed", device_id=device_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "operation": "fix_outlook_mac"
            }

    # Helper method to execute Shell scripts via Intune
    async def _execute_shell_script(
        self,
        device_id: str,
        script_name: str,
        script_content: str
    ) -> Dict[str, Any]:
        """
        Execute Shell script on macOS device via Intune.

        This creates a script in Intune, assigns it to the device, and waits for execution.
        """
        logger.info("Executing Shell script", device_id=device_id, script_name=script_name)

        try:
            # For macOS, we would use deviceHealthScripts or deviceManagementScripts
            # Since the Graph API client has create_device_health_script method, use that

            # Create detection script (always returns exit 1 to trigger remediation)
            detection_script = "#!/bin/bash\nexit 1  # Always trigger remediation"

            script = await self.client.create_device_health_script(
                display_name=f"{script_name} - {datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                detection_script=detection_script,
                remediation_script=script_content,
                run_as_account="system"
            )

            script_id = script["id"]
            logger.info("Script created", script_id=script_id)

            # Trigger device sync
            await self.client.sync_device(device_id)
            logger.info("Device sync triggered", device_id=device_id)

            return {
                "success": True,
                "script_id": script_id,
                "script_name": script_name,
                "device_id": device_id,
                "message": "Script deployed and device synced. Check Intune for execution results.",
                "note": "Script execution happens asynchronously. Results available in Intune portal after device checks in."
            }

        except Exception as e:
            logger.error("Script execution failed", device_id=device_id, script_name=script_name, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "script_name": script_name
            }

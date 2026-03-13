"""
Setup and Test Script for Intune Device Healer
Tests authentication and basic functionality
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
from core.config import Config
from core.auth import GraphAuthenticator
from core.graph_client import GraphClient

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_header(text):
    """Print formatted header"""
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}{text:^60}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")


def print_success(text):
    """Print success message"""
    print(f"{GREEN}✓ {text}{RESET}")


def print_error(text):
    """Print error message"""
    print(f"{RED}✗ {text}{RESET}")


def print_warning(text):
    """Print warning message"""
    print(f"{YELLOW}⚠ {text}{RESET}")


def print_info(text):
    """Print info message"""
    print(f"  {text}")


async def test_authentication(config, authenticator):
    """Test Azure AD authentication"""
    print_header("Testing Authentication")

    try:
        print_info("Attempting to authenticate with Azure AD...")
        token = await authenticator.get_access_token()

        if token:
            print_success("Authentication successful!")
            print_info(f"Token length: {len(token)} characters")
            print_info(f"Token cached: {authenticator.is_authenticated()}")
            return True
        else:
            print_error("Authentication failed - no token received")
            return False

    except Exception as e:
        print_error(f"Authentication failed: {str(e)}")
        return False


async def test_graph_api_access(client):
    """Test basic Graph API access"""
    print_header("Testing Microsoft Graph API Access")

    try:
        print_info("Fetching managed devices...")
        devices = await client.list_managed_devices(limit=5)

        if devices:
            print_success(f"Successfully retrieved {len(devices)} device(s)")
            print_info("\nFirst device details:")
            if devices:
                device = devices[0]
                print_info(f"  Device Name: {device.get('deviceName', 'Unknown')}")
                print_info(f"  Platform: {device.get('operatingSystem', 'Unknown')}")
                print_info(f"  Compliance: {device.get('complianceState', 'Unknown')}")
                print_info(f"  Last Sync: {device.get('lastSyncDateTime', 'Unknown')}")
            return True
        else:
            print_warning("No devices found in Intune (this is OK if tenant is empty)")
            return True

    except Exception as e:
        print_error(f"Graph API access failed: {str(e)}")
        return False


async def test_diagnostic_tools():
    """Test diagnostic tools"""
    print_header("Testing Diagnostic Tools")

    try:
        from tools.diagnostic import DiagnosticTools

        print_info("Importing DiagnosticTools...")
        print_success("DiagnosticTools imported successfully")
        return True

    except Exception as e:
        print_error(f"Diagnostic tools import failed: {str(e)}")
        return False


async def test_remediation_tools():
    """Test remediation tools"""
    print_header("Testing Remediation Tools")

    try:
        from tools.windows_remediation import WindowsRemediationTools
        from tools.macos_remediation import MacOSRemediationTools

        print_info("Importing Windows remediation tools...")
        print_success("WindowsRemediationTools imported successfully")

        print_info("Importing macOS remediation tools...")
        print_success("MacOSRemediationTools imported successfully")

        return True

    except Exception as e:
        print_error(f"Remediation tools import failed: {str(e)}")
        return False


async def test_automation_tools():
    """Test automation tools"""
    print_header("Testing Automation Tools")

    try:
        from tools.automation import AutomationTools

        print_info("Importing AutomationTools...")
        print_success("AutomationTools imported successfully")
        return True

    except Exception as e:
        print_error(f"Automation tools import failed: {str(e)}")
        return False


async def test_monitoring_tools():
    """Test monitoring tools"""
    print_header("Testing Monitoring Tools")

    try:
        from tools.monitoring import MonitoringTools

        print_info("Importing MonitoringTools...")
        print_success("MonitoringTools imported successfully")
        return True

    except Exception as e:
        print_error(f"Monitoring tools import failed: {str(e)}")
        return False


async def main():
    """Main test runner"""
    print_header("Intune Device Healer - Setup & Test")
    print_info("This script will verify your setup and test core functionality\n")

    # Load environment
    load_dotenv()

    # Check environment variables
    print_header("Checking Environment Variables")

    required_vars = ["AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_SECRET"]
    all_vars_present = True

    for var in required_vars:
        value = os.getenv(var)
        if value:
            print_success(f"{var}: Set (length: {len(value)})")
        else:
            print_error(f"{var}: Missing!")
            all_vars_present = False

    if not all_vars_present:
        print_error("\nMissing required environment variables!")
        print_info("Please create a .env file with your Azure credentials")
        print_info("See .env.example for reference")
        return False

    # Initialize configuration
    try:
        config = Config()
        config.validate()
        print_success("\nConfiguration validated successfully")
    except Exception as e:
        print_error(f"\nConfiguration validation failed: {str(e)}")
        return False

    # Initialize authenticator
    authenticator = GraphAuthenticator(config)

    # Run tests
    results = []

    # Test 1: Authentication
    results.append(await test_authentication(config, authenticator))

    # Test 2: Graph API Access
    if results[-1]:  # Only if authentication succeeded
        client = GraphClient(authenticator, config)
        results.append(await test_graph_api_access(client))
    else:
        print_warning("Skipping Graph API test (authentication failed)")
        results.append(False)

    # Test 3: Tool Imports
    results.append(await test_diagnostic_tools())
    results.append(await test_remediation_tools())
    results.append(await test_automation_tools())
    results.append(await test_monitoring_tools())

    # Summary
    print_header("Test Summary")

    passed = sum(results)
    total = len(results)

    print_info(f"Tests Passed: {passed}/{total}")

    if passed == total:
        print_success("\n🎉 All tests passed! Your setup is complete!")
        print_info("\nNext steps:")
        print_info("1. Run the MCP server: python src/server.py")
        print_info("2. Configure your MCP client (Claude Desktop, VS Code Copilot)")
        print_info("3. Start using the 50+ tools available!")
        print_info("\nSee QUICKSTART.md for detailed instructions")
        return True
    else:
        print_error(f"\n❌ {total - passed} test(s) failed")
        print_info("\nPlease fix the errors above and run this script again")
        print_info("Check QUICKSTART.md for troubleshooting help")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

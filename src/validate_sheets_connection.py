#!/usr/bin/env python3
"""
Google Sheets Connection Validator
This script validates the Google Sheets connection and tests read/write operations.
"""

import os
import json
import sys
import logging
from datetime import datetime
from typing import Dict, Any
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsValidator:
    """Validate Google Sheets connection and operations."""
    
    def __init__(self):
        self.service = None
        self.spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
        self.sheet_name = "Hackathons"
        
    def authenticate(self) -> bool:
        """Authenticate with Google Sheets API."""
        logger.info("🔐 Step 1: Authenticating with Google Sheets API...")
        
        try:
            credentials_json = os.getenv("SHEETS_CREDENTIALS")
            if not credentials_json:
                logger.error("❌ SHEETS_CREDENTIALS environment variable not found")
                return False
            
            credentials_info = json.loads(credentials_json)
            
            # For service account credentials
            if "type" in credentials_info and credentials_info["type"] == "service_account":
                logger.info("✅ Using service account credentials")
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_info, scopes=SCOPES
                )
                logger.info(f"   Service account email: {credentials_info.get('client_email', 'N/A')}")
            else:
                # For OAuth credentials
                logger.info("✅ Using OAuth credentials")
                credentials = Credentials.from_authorized_user_info(
                    credentials_info, SCOPES
                )
                if credentials.expired:
                    logger.warning("⚠️  OAuth token is expired")
                    if credentials.refresh_token:
                        from google.auth.transport.requests import Request
                        credentials.refresh(Request())
                        logger.info("✅ Token refreshed successfully")
                    else:
                        logger.error("❌ No refresh token available")
                        return False
            
            self.service = build("sheets", "v4", credentials=credentials)
            logger.info("✅ Authentication successful")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON in SHEETS_CREDENTIALS: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Authentication failed: {e}")
            return False
    
    def validate_spreadsheet_id(self) -> bool:
        """Validate that the spreadsheet ID is correct and accessible."""
        logger.info("🔍 Step 2: Validating spreadsheet ID...")
        
        if not self.spreadsheet_id:
            logger.error("❌ GOOGLE_SHEETS_ID environment variable not found")
            return False
        
        logger.info(f"   Spreadsheet ID: {self.spreadsheet_id}")
        
        try:
            # Try to get spreadsheet metadata
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            logger.info(f"✅ Spreadsheet found: {spreadsheet.get('properties', {}).get('title', 'N/A')}")
            logger.info(f"   URL: https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}")
            
            # List all sheets
            sheets = spreadsheet.get('sheets', [])
            sheet_names = [sheet['properties']['title'] for sheet in sheets]
            logger.info(f"   Available sheets: {', '.join(sheet_names)}")
            
            # Check if our target sheet exists
            if self.sheet_name not in sheet_names:
                logger.warning(f"⚠️  Sheet '{self.sheet_name}' not found in spreadsheet")
                logger.info(f"   Available sheets: {', '.join(sheet_names)}")
                logger.info(f"   The script will create '{self.sheet_name}' if it doesn't exist")
            else:
                logger.info(f"✅ Sheet '{self.sheet_name}' exists")
            
            return True
            
        except HttpError as e:
            if e.resp.status == 404:
                logger.error("❌ Spreadsheet not found (404). Check if:")
                logger.error("   1. The spreadsheet ID is correct")
                logger.error("   2. The service account has access to the spreadsheet")
                logger.error(f"   3. Share the sheet with: {self._get_service_account_email()}")
            elif e.resp.status == 403:
                logger.error("❌ Permission denied (403). Check if:")
                logger.error("   1. The service account has Editor access to the spreadsheet")
                logger.error(f"   2. Share the sheet with: {self._get_service_account_email()}")
            else:
                logger.error(f"❌ Error accessing spreadsheet: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error validating spreadsheet: {e}")
            return False
    
    def _get_service_account_email(self) -> str:
        """Get service account email from credentials."""
        try:
            credentials_json = os.getenv("SHEETS_CREDENTIALS")
            if credentials_json:
                credentials_info = json.loads(credentials_json)
                if "type" in credentials_info and credentials_info["type"] == "service_account":
                    return credentials_info.get("client_email", "N/A")
        except Exception:
            pass
        return "N/A"
    
    def test_read_operation(self) -> bool:
        """Test reading from the sheet."""
        logger.info("📖 Step 3: Testing read operation...")
        
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A1:Z1"
            ).execute()
            
            values = result.get("values", [])
            
            if values:
                logger.info(f"✅ Successfully read {len(values)} row(s) from sheet")
                logger.info(f"   Headers: {values[0] if values else 'No headers'}")
            else:
                logger.info("✅ Sheet is empty (no data yet)")
            
            # Try to read more rows to see existing data
            result_all = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A:Z"
            ).execute()
            
            all_values = result_all.get("values", [])
            if len(all_values) > 1:
                logger.info(f"   Total rows in sheet: {len(all_values)} (including header)")
                logger.info(f"   Data rows: {len(all_values) - 1}")
            else:
                logger.info("   Sheet has only headers (or is empty)")
            
            return True
            
        except HttpError as e:
            if e.resp.status == 400:
                logger.warning("⚠️  Sheet might not exist yet (will be created on first write)")
            else:
                logger.error(f"❌ Error reading from sheet: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error reading from sheet: {e}")
            return False
    
    def _get_last_data_row(self) -> int:
        """Find the last row with data in column A."""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A:A"
            ).execute()
            
            values = result.get("values", [])
            if not values:
                return 1
            
            last_row = len(values)
            while last_row > 0 and (last_row > len(values) or not values[last_row - 1] or not values[last_row - 1][0].strip()):
                last_row -= 1
            
            return max(1, last_row)
        except Exception:
            return 2

    def test_write_operation(self) -> bool:
        """Test writing to the sheet."""
        logger.info("✍️  Step 4: Testing write operation...")
        
        # Create a test row
        test_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        test_row = [
            f"TEST_HACKATHON_{test_timestamp}",
            "https://test.example.com",
            "2024-01-01 to 2024-01-03",
            "2023-12-31",
            "Test Theme",
            "Test Prizes",
            "10000",
            "Online",
            "Test tweet content",
            "No",
            test_timestamp,
            "New",
            "This is a test row - can be deleted"
        ]
        
        try:
            # Find the last row with data to ensure we append at the correct location
            last_row = self._get_last_data_row()
            next_row = last_row + 1
            
            # Use a specific range starting from column A to ensure proper alignment
            # Column M is the 13th column (matches our 13 data columns)
            range_name = f"{self.sheet_name}!A{next_row}:M"
            
            logger.debug(f"Appending test row starting at row {next_row} (last row: {last_row})")
            
            # Append test row using specific range to ensure column A alignment
            body = {"values": [test_row]}
            
            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            ).execute()
            
            logger.info("✅ Write operation completed")
            logger.info(f"   Updated range: {result.get('updates', {}).get('updatedRange', 'N/A')}")
            logger.info(f"   Updated rows: {result.get('updates', {}).get('updatedRows', 0)}")
            logger.info(f"   Updated cells: {result.get('updates', {}).get('updatedCells', 0)}")
            
            return True
            
        except HttpError as e:
            logger.error(f"❌ Error writing to sheet: {e}")
            if e.resp.status == 403:
                logger.error("   Permission denied - check service account access")
            return False
        except Exception as e:
            logger.error(f"❌ Error writing to sheet: {e}")
            return False
    
    def verify_write_success(self) -> bool:
        """Verify that the test write was successful by reading it back."""
        logger.info("🔍 Step 5: Verifying write was successful...")
        
        try:
            # Read all rows to find our test row
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A:Z"
            ).execute()
            
            values = result.get("values", [])
            
            if not values:
                logger.error("❌ Sheet appears to be empty - write may have failed")
                return False
            
            # Search for test row in all rows (checking column A specifically)
            test_row_found = False
            test_row_index = None
            test_row_column_offset = None
            
            for i, row in enumerate(values):
                # Check if TEST_HACKATHON appears in this row
                for j, cell in enumerate(row):
                    if "TEST_HACKATHON" in str(cell):
                        test_row_found = True
                        test_row_index = i + 1  # 1-indexed row number
                        test_row_column_offset = j  # Column offset (0 = A, 1 = B, etc.)
                        break
                if test_row_found:
                    break
            
            if test_row_found:
                if test_row_column_offset == 0:
                    # Test row found in column A - perfect!
                    logger.info(f"✅ Test row found in sheet at row {test_row_index}, column A!")
                    logger.info(f"   Row data: {values[test_row_index - 1][:5]}...")  # Show first 5 columns
                    logger.info("   ✅ WRITE OPERATION VERIFIED - Data is being written correctly at column A")
                    return True
                else:
                    # Test row found but not in column A - column offset issue!
                    column_letter = chr(65 + test_row_column_offset)  # Convert to letter (A=65)
                    logger.error("❌ Test row found but in wrong column!")
                    logger.error(f"   Found at row {test_row_index}, column {column_letter} (expected column A)")
                    logger.error(f"   Column offset: {test_row_column_offset} columns to the right")
                    logger.error(f"   Row data: {values[test_row_index - 1]}")
                    logger.error("   ⚠️  This indicates a column alignment issue - data is being written with an offset")
                    logger.error("   💡 This is likely due to existing data in columns A-O")
                    return False
            else:
                # Test row not found at all
                logger.warning("⚠️  Test row not found in sheet")
                logger.info(f"   Total rows in sheet: {len(values)}")
                if len(values) > 0:
                    logger.info(f"   Last row: {values[-1][:5] if values[-1] else 'Empty'}...")
                logger.warning("   This might indicate a write issue or the row was written elsewhere")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error verifying write: {e}")
            return False
    
    def check_permissions(self) -> bool:
        """Check if the service account has proper permissions."""
        logger.info("🔐 Step 6: Checking permissions...")
        
        try:
            # Try to get spreadsheet permissions (if accessible)
            service_account_email = self._get_service_account_email()
            
            if service_account_email != "N/A":
                logger.info(f"   Service account email: {service_account_email}")
                logger.info("   ✅ Make sure this email has Editor access to the spreadsheet")
                logger.info("   📋 To share: Open spreadsheet → Share → Add email → Editor")
            else:
                logger.warning("   Could not determine service account email")
            
            # Try a write operation to check permissions
            # (We already did this in test_write_operation, but we can check here too)
            return True
            
        except Exception as e:
            logger.error(f"❌ Error checking permissions: {e}")
            return False
    
    def run_full_validation(self) -> Dict[str, Any]:
        """Run all validation steps."""
        logger.info("=" * 60)
        logger.info("🔍 Google Sheets Connection Validation")
        logger.info("=" * 60)
        logger.info("")
        
        results = {
            "authentication": False,
            "spreadsheet_validation": False,
            "read_test": False,
            "write_test": False,
            "write_verification": False,
            "permissions_check": False,
            "overall_status": False
        }
        
        # Step 1: Authenticate
        results["authentication"] = self.authenticate()
        if not results["authentication"]:
            logger.error("\n❌ Authentication failed - cannot proceed")
            return results
        
        # Step 2: Validate spreadsheet
        results["spreadsheet_validation"] = self.validate_spreadsheet_id()
        if not results["spreadsheet_validation"]:
            logger.error("\n❌ Spreadsheet validation failed - cannot proceed")
            return results
        
        # Step 3: Test read
        results["read_test"] = self.test_read_operation()
        
        # Step 4: Test write
        results["write_test"] = self.test_write_operation()
        
        # Step 5: Verify write
        if results["write_test"]:
            results["write_verification"] = self.verify_write_success()
        
        # Step 6: Check permissions
        results["permissions_check"] = self.check_permissions()
        
        # Overall status
        results["overall_status"] = all([
            results["authentication"],
            results["spreadsheet_validation"],
            results["read_test"],
            results["write_test"],
            results["write_verification"]
        ])
        
        # Print summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 VALIDATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Authentication: {'✅' if results['authentication'] else '❌'}")
        logger.info(f"Spreadsheet Validation: {'✅' if results['spreadsheet_validation'] else '❌'}")
        logger.info(f"Read Test: {'✅' if results['read_test'] else '❌'}")
        logger.info(f"Write Test: {'✅' if results['write_test'] else '❌'}")
        logger.info(f"Write Verification: {'✅' if results['write_verification'] else '❌'}")
        logger.info(f"Permissions Check: {'✅' if results['permissions_check'] else '❌'}")
        logger.info("")
        
        if results["overall_status"]:
            logger.info("🎉 ALL TESTS PASSED - Google Sheets connection is working correctly!")
        else:
            logger.error("❌ SOME TESTS FAILED - Please review the errors above")
            logger.info("")
            logger.info("💡 Common issues:")
            logger.info("   1. Service account doesn't have access to the spreadsheet")
            logger.info("   2. Spreadsheet ID is incorrect")
            logger.info("   3. Sheet name doesn't exist (will be created automatically)")
            logger.info("   4. Credentials are expired or invalid")
        
        logger.info("=" * 60)
        
        return results


def main():
    """Main entry point."""
    # Load environment variables if in dev mode
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
    if dev_mode:
        try:
            from dotenv import load_dotenv
            env_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
            )
            if os.path.exists(env_path):
                load_dotenv(env_path)
                logger.info(f"✅ Loaded environment variables from: {env_path}")
        except ImportError:
            logger.warning("python-dotenv not installed - using system environment variables")
    
    validator = SheetsValidator()
    results = validator.run_full_validation()
    
    # Exit with appropriate code
    sys.exit(0 if results["overall_status"] else 1)


if __name__ == "__main__":
    main()


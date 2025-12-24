import os
import json
from typing import Dict, List, Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
import logging

# Google Sheets API scopes
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class StorageManager:
    """
    Storage manager for Google Sheets integration.
    
    NEW FLOW (efficiency improvement):
    1. filter_existing_links() - called BEFORE AI analysis to reduce prompt size
    2. add_hackathons_batch() - called AFTER AI analysis (no duplicate checking needed)
    
    This reduces the number of URLs sent to Gemini API by filtering out existing links first.
    """
    def __init__(self, spreadsheet_id: str = None):
        """
        Initialize storage manager for Google Sheets.

        Args:
            spreadsheet_id: Google Sheets ID (can be set via env var GOOGLE_SHEETS_ID)
        """
        self.spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEETS_ID")
        if not self.spreadsheet_id:
            raise ValueError("Google Sheets ID is required (GOOGLE_SHEETS_ID env var)")

        self.service = None
        self.logger = logging.getLogger(__name__)

        # Sheet configuration
        self.sheet_name = "Hackathons"
        self.headers = [
            "Name",
            "Link",
            "Dates",
            "Registration Deadline",
            "Theme",
            "Prizes",
            "Prize Amount (USD)",
            "Mode",
            "Tweet Content",
            "Twitter Posted",
            "Added Date",
            "Status",
            "Notes",
        ]

    def authenticate(self) -> bool:
        """Authenticate with Google Sheets API."""
        try:
            # Try to load credentials from environment variable (for GitHub Actions)
            credentials_json = os.getenv("SHEETS_CREDENTIALS")
            if not credentials_json:
                self.logger.error("SHEETS_CREDENTIALS environment variable not found")
                return False
                
            credentials_info = json.loads(credentials_json)

            # For service account credentials
            if (
                "type" in credentials_info
                and credentials_info["type"] == "service_account"
            ):
                from google.oauth2 import service_account

                credentials = service_account.Credentials.from_service_account_info(
                    credentials_info, scopes=SCOPES
                )
                self.logger.debug(
                    f"Using service account: {credentials_info.get('client_email', 'N/A')}"
                )
            else:
                # For OAuth credentials
                credentials = Credentials.from_authorized_user_info(
                    credentials_info, SCOPES
                )
                # Check if token needs refresh
                if credentials.expired and credentials.refresh_token:
                    try:
                        from google.auth.transport.requests import Request
                        credentials.refresh(Request())
                        self.logger.info("OAuth token refreshed successfully")
                    except Exception as refresh_error:
                        self.logger.error(f"Failed to refresh OAuth token: {refresh_error}")
                        return False

            self.service = build("sheets", "v4", credentials=credentials)
            self.logger.info("Google Sheets authentication successful")
            return True

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in SHEETS_CREDENTIALS: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            return False

    def initialize_sheet(self) -> bool:
        """Initialize the Google Sheet with headers if it doesn't exist."""
        try:
            # Check if sheet exists and has headers
            result = (
                self.service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self.spreadsheet_id, range=f"{self.sheet_name}!A1:Z1"
                )
                .execute()
            )

            values = result.get("values", [])

            # If sheet is empty or doesn't have proper headers, initialize it
            if not values or values[0] != self.headers:
                self._create_headers()
                self.logger.info("Initialized Google Sheet with headers")

            return True

        except HttpError as error:
            if error.resp.status == 400:  # Sheet doesn't exist
                self._create_sheet()
                return True
            else:
                self.logger.error(f"Error initializing sheet: {error}")
                return False

    def _create_sheet(self) -> bool:
        """Create a new sheet in the spreadsheet."""
        try:
            request_body = {
                "requests": [{"addSheet": {"properties": {"title": self.sheet_name}}}]
            }

            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id, body=request_body
            ).execute()

            # Add headers
            self._create_headers()
            self.logger.info(f"Created new sheet: {self.sheet_name}")
            return True

        except HttpError as error:
            self.logger.error(f"Error creating sheet: {error}")
            return False

    def _create_headers(self) -> bool:
        """Create headers in the sheet."""
        try:
            body = {"values": [self.headers]}

            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A1",
                valueInputOption="RAW",
                body=body,
            ).execute()

            return True

        except HttpError as error:
            self.logger.error(f"Error creating headers: {error}")
            return False

    def check_duplicate(self, hackathon: Dict[str, Any]) -> bool:
        """
        Check if a hackathon already exists in the sheet.

        Args:
            hackathon: Hackathon data dictionary

        Returns:
            True if duplicate exists, False otherwise
        """
        try:
            # Get all data from the sheet
            result = (
                self.service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{self.sheet_name}!A:B",  # Name and Link columns
                )
                .execute()
            )

            values = result.get("values", [])
            if len(values) <= 1:  # Only headers or empty
                return False

            hackathon_name = hackathon.get("name", "").strip().lower()
            hackathon_link = hackathon.get("link", "").strip()
            
            self.logger.debug("Checking for duplicates...")
            self.logger.debug(f"Hackathon Name, Link: {hackathon_name}, {hackathon_link}")

            # Check for duplicates based on name or link
            for row in values[1:]:  # Skip header row
                if len(row) >= 2:
                    existing_name = row[0].strip().lower()
                    existing_link = row[1].strip() if len(row) > 1 else ""

                    self.logger.debug(f"Existing Name, Link: {existing_name}, {existing_link}")

                    # Check for exact name match or link match
                    if hackathon_name == existing_name or (
                        hackathon_link and hackathon_link == existing_link
                    ):
                        self.logger.info(
                            f"Duplicate found: {hackathon.get('name', 'Unknown')}"
                        )
                        return True

            return False

        except HttpError as error:
            self.logger.error(f"Error checking duplicates: {error}")
            return False  # Assume no duplicate if error occurs

    def get_existing_links(self) -> List[str]:
        """
        Get all existing hackathon links from the sheet to check for duplicates.

        Returns:
            List of existing links (normalized)
        """
        try:
            # Get all links from the sheet
            result = (
                self.service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{self.sheet_name}!B:B",  # Link column only
                )
                .execute()
            )

            values = result.get("values", [])
            if len(values) <= 1:  # Only headers or empty
                return []

            existing_links = []
            for row in values[1:]:  # Skip header row
                if row and len(row) > 0:
                    link = row[0].strip()
                    if link:
                        # Normalize the link (remove query parameters, etc.)
                        try:
                            from urllib.parse import urlparse, urlunparse
                            parsed = urlparse(link)
                            normalized_link = urlunparse((
                                parsed.scheme,
                                parsed.netloc,
                                parsed.path,
                                parsed.params,
                                '',  # Remove query
                                parsed.fragment
                            ))
                            existing_links.append(normalized_link)
                        except Exception:
                            # If URL parsing fails, use the link as-is
                            existing_links.append(link)

            self.logger.info(f"Found {len(existing_links)} existing links in sheet")
            return existing_links

        except HttpError as error:
            self.logger.error(f"Error getting existing links: {error}")
            return []

    def filter_existing_links(self, links: List[str]) -> List[str]:
        """
        Filter out links that already exist in the sheet.

        Args:
            links: List of links to check

        Returns:
            List of links that don't exist in the sheet
        """
        existing_links = self.get_existing_links()
        if not existing_links:
            return links

        # Convert to set for faster lookup
        existing_set = set(existing_links)
        
        # Filter out existing links
        new_links = []
        for link in links:
            if link not in existing_set:
                new_links.append(link)
            else:
                self.logger.info(f"Filtered out existing link: {link}")

        filtered_count = len(links) - len(new_links)
        if filtered_count > 0:
            self.logger.info(f"Filtered out {filtered_count} existing links, {len(new_links)} new links remain")

        return new_links

    def _get_last_data_row(self) -> int:
        """
        Find the last row with data in column A (where our hackathon data starts).
        
        Returns:
            Row number of the last row with data (1-indexed), or 1 if sheet is empty
        """
        try:
            # Get all values in column A to find the last row with data
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A:A"
            ).execute()
            
            values = result.get("values", [])
            if not values:
                return 1  # Sheet is empty, return header row
            
            # Find the last non-empty row in column A
            last_row = len(values)
            # Skip trailing empty rows
            while last_row > 0 and (last_row > len(values) or not values[last_row - 1] or not values[last_row - 1][0].strip()):
                last_row -= 1
            
            return max(1, last_row)  # At least row 1 (headers)
            
        except HttpError as error:
            self.logger.warning(f"Error finding last row, defaulting to row 2: {error}")
            return 2  # Default to row 2 (after headers)
        except Exception as e:
            self.logger.warning(f"Error finding last row, defaulting to row 2: {e}")
            return 2

    def add_hackathons_batch(self, hackathons: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Add multiple hackathons to the Google Sheet in a single operation.
        Note: Duplicate checking should be done before calling this method using filter_existing_links.

        Args:
            hackathons: List of hackathon data dictionaries (assumed to be pre-filtered)

        Returns:
            Dictionary with count and list of newly added hackathons
        """
        if not hackathons:
            return {"count": 0, "new_hackathons": []}

        try:
            # Prepare row data for all hackathons (no duplicate checking needed)
            rows_to_add = []
            for hackathon in hackathons:
                row_data = self._prepare_row_data(hackathon)
                rows_to_add.append(row_data)

            # Find the last row with data to ensure we append at the correct location
            last_row = self._get_last_data_row()
            next_row = last_row + 1
            
            # Use a specific range starting from column A to ensure proper alignment
            # Column M is the 13th column (matches our 13 headers)
            range_name = f"{self.sheet_name}!A{next_row}:M"
            
            self.logger.debug(f"Appending {len(hackathons)} rows starting at row {next_row} (last row: {last_row})")

            # Batch append to sheet using specific range to ensure column A alignment
            body = {"values": rows_to_add}

            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            ).execute()

            # Log detailed response for debugging
            updates = result.get("updates", {})
            updated_range = updates.get("updatedRange", "N/A")
            updated_rows = updates.get("updatedRows", 0)
            updated_cells = updates.get("updatedCells", 0)
            
            self.logger.info(
                f"Added {len(hackathons)} hackathons to sheet in batch operation"
            )
            self.logger.debug(
                f"API Response - Updated range: {updated_range}, "
                f"Rows: {updated_rows}, Cells: {updated_cells}"
            )
            
            # Verify the write was successful
            if updated_rows == 0:
                self.logger.warning(
                    "⚠️  API returned 0 updated rows - data may not have been written!"
                )
                self.logger.warning(
                    "   Check: 1) Service account permissions, 2) Spreadsheet ID, 3) Sheet name"
                )
            elif updated_rows != len(hackathons):
                self.logger.warning(
                    f"⚠️  Expected {len(hackathons)} rows but only {updated_rows} were updated"
                )

            return {"count": len(hackathons), "new_hackathons": hackathons}

        except HttpError as error:
            error_details = error.error_details if hasattr(error, 'error_details') else str(error)
            self.logger.error(f"Error batch adding hackathons: {error}")
            self.logger.error(f"Error details: {error_details}")
            self.logger.error(f"Spreadsheet ID: {self.spreadsheet_id}, Sheet: {self.sheet_name}")
            
            if error.resp.status == 403:
                self.logger.error(
                    "Permission denied - ensure service account has Editor access to the spreadsheet"
                )
            elif error.resp.status == 404:
                self.logger.error(
                    "Spreadsheet not found - check GOOGLE_SHEETS_ID environment variable"
                )
            
            return {"count": 0, "new_hackathons": []}
        except Exception as e:
            self.logger.error(f"Unexpected error batch adding hackathons: {e}")
            self.logger.error(f"Spreadsheet ID: {self.spreadsheet_id}, Sheet: {self.sheet_name}")
            return {"count": 0, "new_hackathons": []}

    def add_hackathon(self, hackathon: Dict[str, Any]) -> bool:
        """
        Add a single hackathon to the Google Sheet (legacy method).
        For batch operations, use add_hackathons_batch instead.
        """
        result = self.add_hackathons_batch([hackathon])
        return result["count"] > 0

    def _prepare_row_data(self, hackathon: Dict[str, Any]) -> List[str]:
        """Prepare hackathon data for insertion into Google Sheet."""

        row_data = [
            hackathon.get("name", ""),  # Name
            hackathon.get("link", ""),  # Link
            hackathon.get("dates", ""),  # Dates
            hackathon.get("registration_deadline", ""),  # Registration Deadline
            hackathon.get("theme", ""),  # Theme
            hackathon.get("prizes", ""),  # Prizes
            str(hackathon.get("prize_amount_usd", 0)),  # Prize Amount (USD)
            hackathon.get("mode", ""),  # Mode
            hackathon.get("tweet", ""),  # Tweet Content
            "No",  # Twitter Posted
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Added Date
            "New",  # Status
            "",  # Notes
        ]

        return row_data

    def update_twitter_status(self, hackathon_title: str, posted: bool = True) -> bool:
        """
        Update the Twitter posted status for a hackathon.

        Args:
            hackathon_title: Title of the hackathon to update
            posted: Whether it was posted to Twitter

        Returns:
            True if successfully updated, False otherwise
        """
        try:
            # Find the row with matching title
            result = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=f"{self.sheet_name}!A:A")
                .execute()
            )

            values = result.get("values", [])
            row_index = None

            for i, row in enumerate(
                values[1:], start=2
            ):  # Start from row 2 (skip header)
                if row and row[0].strip().lower() == hackathon_title.strip().lower():
                    row_index = i
                    break

            if row_index:
                # Update the Twitter Posted column (column P, index 15)
                status = "Yes" if posted else "No"
                range_name = f"{self.sheet_name}!P{row_index}"

                body = {"values": [[status]]}

                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                    valueInputOption="RAW",
                    body=body,
                ).execute()

                self.logger.info(f"Updated Twitter status for: {hackathon_title}")
                return True
            else:
                self.logger.warning(
                    f"Hackathon not found for Twitter status update: {hackathon_title}"
                )
                return False

        except HttpError as error:
            self.logger.error(f"Error updating Twitter status: {error}")
            return False

    def get_recent_hackathons(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get hackathons added in the last N days.

        Args:
            days: Number of days to look back

        Returns:
            List of recent hackathon data
        """
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=f"{self.sheet_name}!A:Z")
                .execute()
            )

            values = result.get("values", [])
            if len(values) <= 1:
                return []

            recent_hackathons = []
            cutoff_date = datetime.now() - timedelta(days=days)

            for row in values[1:]:  # Skip header
                if len(row) >= 17:  # Ensure we have the added date column
                    try:
                        added_date_str = row[16]  # Added Date column
                        added_date = datetime.strptime(
                            added_date_str, "%Y-%m-%d %H:%M:%S"
                        )

                        if added_date >= cutoff_date:
                            hackathon_data = {
                                "title": row[0] if len(row) > 0 else "",
                                "url": row[1] if len(row) > 1 else "",
                                "twitter_posted": row[15] if len(row) > 15 else "No",
                                "added_date": added_date_str,
                                "status": row[17] if len(row) > 17 else "New",
                            }
                            recent_hackathons.append(hackathon_data)
                    except (ValueError, IndexError):
                        continue  # Skip rows with invalid date format

            return recent_hackathons

        except HttpError as error:
            self.logger.error(f"Error getting recent hackathons: {error}")
            return []

    def get_pending_twitter_posts(self) -> List[Dict[str, Any]]:
        """Get hackathons that haven't been posted to Twitter yet."""
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=f"{self.sheet_name}!A:Z")
                .execute()
            )

            values = result.get("values", [])
            if len(values) <= 1:
                return []

            pending_posts = []

            for row in values[1:]:  # Skip header
                if len(row) >= 16:
                    twitter_posted = row[15] if len(row) > 15 else "No"
                    status = row[17] if len(row) > 17 else "New"

                    if twitter_posted.lower() == "no" and status.lower() == "new":
                        hackathon_data = {
                            "title": row[0] if len(row) > 0 else "",
                            "url": row[1] if len(row) > 1 else "",
                            "description": row[2] if len(row) > 2 else "",
                            "prize_info": row[6] if len(row) > 6 else "",
                            "ai_analysis": row[14] if len(row) > 14 else "{}",
                        }
                        pending_posts.append(hackathon_data)

            return pending_posts

        except HttpError as error:
            self.logger.error(f"Error getting pending Twitter posts: {error}")
            return []

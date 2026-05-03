#!/usr/bin/env python3
"""
AI Hackathon Curation Agent
Main orchestrator script that coordinates all components.
"""

import asyncio
import logging
import os
import re
import sys
from typing import List, Dict, Any
from datetime import datetime

from email_processor import EmailProcessor
from hackathon_analyzer import HackathonAnalyzer
from storage_manager import StorageManager
from twitter_poster import (
    TwitterPoster,
    get_twitter_weighted_length,
    TWITTER_TWEET_MAX_LENGTH,
    TWITTER_URL_LENGTH,
)


# Load environment variables based on DEV_MODE flag
def load_environment():
    """Load environment variables from .env file if DEV_MODE is set, otherwise use system env."""
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"

    if dev_mode:
        # Local development - load from .env file
        try:
            from dotenv import load_dotenv

            # Load .env file from the project root (parent of src directory)
            env_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
            )

            if os.path.exists(env_path):
                load_dotenv(env_path)
                print(f"✅ DEV_MODE: Loaded environment variables from: {env_path}")
            else:
                print(f"⚠️  DEV_MODE: .env file not found at: {env_path}")
                print(
                    "   Please create a .env file in the project root with your API keys"
                )
        except ImportError:
            print("❌ DEV_MODE: python-dotenv not installed")
            print("   Install with: pip install python-dotenv")
    else:
        # Production/CI mode - use system environment variables
        print("🔄 Production mode: Using system environment variables")


# Load environment variables
load_environment()

# Setup logging early, after environment variables are loaded
def setup_logging():
    """Setup logging configuration."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Force reconfigure logging
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("hackathon_agent.log")
            if not os.getenv("GITHUB_ACTIONS")
            else logging.StreamHandler(),
        ],
        force=True  # This ensures logging is reconfigured even if already set up
    )
    
    # Also set the root logger level explicitly
    logging.getLogger().setLevel(getattr(logging, log_level))
    
    print(f"🔧 Logging configured with level: {log_level}")

# Setup logging before importing other modules
setup_logging()

# Add src directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class HackathonCurationAgent:
    def __init__(self):
        """Initialize the hackathon curation agent."""

        # Initialize components
        self.email_processor = EmailProcessor()
        self.hackathon_analyzer = HackathonAnalyzer()
        self.storage_manager = StorageManager()
        self.twitter_poster = TwitterPoster()

        # Configuration
        self.max_emails_per_run = int(os.getenv("MAX_EMAILS_PER_RUN", "10"))
        self.max_twitter_posts = int(os.getenv("MAX_TWITTER_POSTS", "3"))
        self.dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

        # Summary email configuration
        # To enable: Set SEND_SUMMARY_EMAIL=true and SUMMARY_EMAIL_RECIPIENTS=email1@example.com,email2@example.com
        self.send_summary_email = (
            os.getenv("SEND_SUMMARY_EMAIL", "false").lower() == "true"
        )
        self.summary_email_recipients = self._parse_email_recipients()

        self.logger = logging.getLogger(__name__)
        
        gemini_api_works = self.hackathon_analyzer.test_gemini_api()
        if not gemini_api_works:
            self.logger.error("Gemini API test failed")
            raise Exception("Gemini API test failed")

    def _parse_email_recipients(self) -> List[str]:
        """Parse summary email recipients from environment variable."""
        recipients_env = os.getenv("SUMMARY_EMAIL_RECIPIENTS", "")
        if not recipients_env:
            return []

        # Split by comma and strip whitespace
        recipients = [
            email.strip() for email in recipients_env.split(",") if email.strip()
        ]
        return recipients

    def _clean_tweet_body(self, tweet_text: str) -> str:
        """Normalize AI-generated tweet body by removing links and enforcing lowercase."""
        if not tweet_text:
            return ""

        # Remove links from model output so only canonical link is posted.
        without_links = re.sub(r"https?://\S+", "", tweet_text)
        # Keep intentional blank lines for readability while normalizing whitespace.
        lines = [line.strip() for line in without_links.strip().splitlines()]
        compact = "\n".join(lines)
        return compact.lower().strip()

    def _compose_tweet_text(self, hackathon: Dict[str, Any]) -> str:
        """Build final tweet text and append canonical link only if it fits."""
        canonical_link = str(hackathon.get("link") or "").strip()

        draft = self._clean_tweet_body(str(hackathon.get("tweet") or ""))
        body = draft
        if not body:
            name = str(hackathon.get("name") or "hackathon").strip().lower()
            prizes = str(hackathon.get("prizes") or "").strip().lower()
            dates = str(hackathon.get("dates") or "").strip().lower()
            fallback_parts = [name]
            if prizes:
                fallback_parts.append(f"prize: {prizes}")
            if dates:
                fallback_parts.append(f"dates: {dates}")
            body = "\n".join(fallback_parts).strip()

        if not canonical_link:
            self.logger.warning(
                f"Missing canonical link for tweet: {hackathon.get('name', 'Unknown')}"
            )
            return body

        with_link = f"{body}\n\napply: {canonical_link}"
        if get_twitter_weighted_length(with_link) <= TWITTER_TWEET_MAX_LENGTH:
            return with_link

        # Twitter counts URLs with fixed weighted length.
        # If the link cannot fit, post body-only and add link manually if needed.
        self.logger.warning(
            f"Tweet too long to include link: {hackathon.get('name', 'Unknown')}"
        )
        link_prefix_length = len("\n\napply: ")
        self.logger.info(
            f"Weighted length details: body={get_twitter_weighted_length(body)}, "
            f"suffix={link_prefix_length + TWITTER_URL_LENGTH}, max={TWITTER_TWEET_MAX_LENGTH}"
        )
        return body

    def check_required_env_vars(self):
        """Check if all required environment variables are set."""
        required_vars = {
            "GEMINI_API_KEY": "Required for AI analysis of hackathons",
            # Add other required variables here as needed
        }

        missing_vars = []
        for var, description in required_vars.items():
            if not os.getenv(var):
                missing_vars.append(f"{var}: {description}")

        if missing_vars:
            print("❌ Missing required environment variables:")
            for var in missing_vars:
                print(f"   {var}")

            dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
            if dev_mode:
                print("\n💡 DEV_MODE: Add these to your .env file")
                print(
                    f"   Create: {os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')}"
                )
            else:
                print("\n💡 Production mode: Set these as environment variables")
                print("   For GitHub Actions: Set as repository secrets")
                print("   For other deployments: Set in your environment")

            return False

        print("✅ All required environment variables are set")
        return True



    async def run(self) -> Dict[str, Any]:
        """
        Main execution function.

        Returns:
            Dictionary with execution results and statistics
        """
        start_time = datetime.now()
        results = {
            "execution_time": None,
            "emails_processed": 0,
            "hackathons_found": 0,
            "hackathon_related_links": 0,
            "hackathons_approved": 0,
            "hackathons_stored": 0,
            "twitter_posts": 0,
            "errors": [],
            "summary": "",
        }

        try:
            self.logger.info("🚀 Starting Hackathon Curation Agent")

            # Step 0: Check required environment variables
            if not self.check_required_env_vars():
                raise Exception("Missing required environment variables")

            # Step 1: Authenticate all services
            if not await self.authenticate_services():
                raise Exception("Service authentication failed")

            # Step 2: Process emails and extract hackathon links
            emails = await self.process_emails()
            results["emails_processed"] = len(emails)

            if not emails:
                self.logger.info("No new hackathon emails found")
                results["hackathons_found"] = 0
                results["hackathon_related_links"] = 0
                results["summary"] = "No new emails to process"
                # Still send summary email even if no emails found
                if self.send_summary_email and self.summary_email_recipients:
                    await self.send_summary_email_report(results, [])
                return results

            # Step 3: AI analysis in single API call to analyze and filter hackathons
            analysis_result = await self.analyze_hackathons(emails)
            hackathons = analysis_result["hackathons"]
            results["hackathons_found"] = analysis_result["total_links_found"]  # Total links found in emails
            results["hackathon_related_links"] = analysis_result["hackathon_related_links"]  # Links that appear hackathon-related
            results["hackathons_approved"] = len(
                hackathons
            )  # Already filtered by AI criteria evaluation
            
            self.logger.info(f"🔗 Total links found in emails: {analysis_result['total_links_found']}")
            self.logger.info(f"🎯 Hackathon-related links: {analysis_result['hackathon_related_links']}")
            self.logger.info(f"✅ AI-approved hackathons: {len(hackathons)}")

            if not hackathons:
                self.logger.info("No new hackathons found to analyze (all were duplicates or didn't meet criteria)")
                results["summary"] = (
                    f"Processed {len(emails)} emails but found no new hackathons to analyze"
                )
                
                # Mark emails as read even if no hackathons found
                if not self.dry_run:
                    await self.mark_emails_processed(emails)
                
                # Still send summary email even if no hackathons found
                if self.send_summary_email and self.summary_email_recipients:
                    await self.send_summary_email_report(results, [])
                return results

            # Step 4: Store approved hackathons (batch operation)
            self.logger.info(f"💾 Processing {len(hackathons)} AI-approved hackathons for storage...")
            storage_result = await self.check_duplicates_and_store_hackathons(hackathons)
            results["hackathons_stored"] = storage_result["count"]
            results["duplicates_filtered"] = storage_result.get("duplicates_filtered", 0)
            new_hackathons = storage_result["new_hackathons"]
            
            self.logger.info(f"📊 Storage summary: {len(hackathons)} approved → {len(new_hackathons)} stored, {results['duplicates_filtered']} duplicates filtered")

            # Step 5: Post to Twitter (only new hackathons that were actually stored)
            if not self.dry_run and new_hackathons:
                twitter_results = await self.post_to_twitter(new_hackathons)
                results["twitter_posts"] = twitter_results["successful_posts"]
            elif not new_hackathons:
                self.logger.info("No new hackathons to tweet (all were duplicates)")
                results["twitter_posts"] = 0

            # Step 6: Mark emails as read
            if not self.dry_run:
                await self.mark_emails_processed(emails)

            # Step 7: Send summary email (if configured)
            if self.send_summary_email and self.summary_email_recipients:
                self.logger.info(f"📧 Sending summary email with {len(new_hackathons)} new hackathons (filtered from {len(hackathons)} total)")
                await self.send_summary_email_report(results, new_hackathons)

            # Generate summary
            results["summary"] = self.generate_summary(results)

        except Exception as e:
            error_msg = f"Critical error in main execution: {e}"
            self.logger.error(error_msg)
            results["errors"].append(error_msg)
            results["summary"] = f"Execution failed: {str(e)}"

        finally:
            execution_time = datetime.now() - start_time
            results["execution_time"] = str(execution_time)
            self.logger.info(f"⏱️ Total execution time: {execution_time}")
            self.logger.info(f"📊 Final results: {results['summary']}")

        return results

    async def authenticate_services(self) -> bool:
        """Authenticate all required services."""
        self.logger.info("🔐 Authenticating services...")

        # Gmail authentication
        if not self.email_processor.authenticate():
            self.logger.error("Gmail authentication failed")
            return False

        # Google Sheets authentication
        if not self.storage_manager.authenticate():
            self.logger.error("Google Sheets authentication failed")
            return False

        # Initialize Google Sheets
        if not self.storage_manager.initialize_sheet():
            self.logger.error("Google Sheets initialization failed")
            return False

        # Twitter authentication (optional in dry run)
        if not self.dry_run:
            if not self.twitter_poster.authenticate():
                self.logger.warning(
                    "Twitter authentication failed - continuing without Twitter posting"
                )

        self.logger.info("✅ Service authentication completed")
        return True

    async def process_emails(self) -> List[Dict[str, Any]]:
        """Process unread hackathon emails."""
        self.logger.info("📧 Processing hackathon emails...")

        label_name = os.getenv("HACKATHON_EMAIL_LABEL", "Hackathons")
        self.logger.debug(f"Processing emails with label: {label_name}")
        emails = self.email_processor.get_unread_hackathon_emails(label_name)

        # Limit number of emails processed per run
        if len(emails) > self.max_emails_per_run:
            self.logger.info(f"Limiting to {self.max_emails_per_run} emails per run")
            emails = emails[: self.max_emails_per_run]

        self.logger.info(f"📬 Found {len(emails)} unread hackathon emails")

        for email in emails:
            self.logger.info(f"  📮 {email['subject']} - {len(email['links'])} links")

        return emails

    async def analyze_hackathons(
        self, emails: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Analyze hackathon websites from email links using AI.
        
        1. Extract and clean links from emails
        2. Filter for hackathon-related links
        3. Filter out existing links from sheet
        4. Send only new links to AI for analysis
        
        """
        self.logger.info("🤖 AI-analyzing hackathon websites...")

        # Collect all unique links from emails
        all_links = []
        for email in emails:
            all_links.extend(email["links"])

        # Clean, normalize, and remove duplicates
        cleaned_links = self.clean_and_normalize_links(all_links)
        self.logger.info(f"Cleaned Links: {cleaned_links}")

        # Get hackathon indicators from environment
        hackathon_indicators = self.get_hackathon_indicators()
        self.logger.info(f"Hackathon indicators: {hackathon_indicators}")
        filtered_links = self.filter_hackathon_links(cleaned_links, hackathon_indicators)

        self.logger.info(f"Filtered Links: {filtered_links}")

        self.logger.info(
            f"🔗 Found {len(cleaned_links)} total links, {len(filtered_links)} appear to be hackathon-related"
        )
        
        # Filter out links that already exist in the sheet to reduce AI prompt size
        new_links = self.storage_manager.filter_existing_links(filtered_links)
        
        if not new_links:
            self.logger.info("🎯 All links already exist in sheet - no new hackathons to analyze")
            return {
                "hackathons": [],
                "total_links_found": len(cleaned_links),
                "hackathon_related_links": len(filtered_links)
            }

        # Single AI API call to analyze websites and evaluate against criteria
        hackathons = await self.hackathon_analyzer.analyze_hackathon_urls(
            new_links
        )

        self.logger.info(
            f"🎯 AI analysis completed - approved {len(hackathons)} hackathons"
        )

        # Return both hackathons and link counts for proper reporting
        return {
            "hackathons": hackathons,
            "total_links_found": len(cleaned_links),
            "hackathon_related_links": len(filtered_links)
        }

    def clean_and_normalize_links(self, links: List[str]) -> List[str]:
        """Clean and normalize links by removing query parameters to eliminate duplicates.
        
        Exception: For tracking/redirect URLs (e.g., /ls/click, /wf/open), query parameters
        are preserved as they're needed for the redirect to work properly.
        """
        from urllib.parse import urlparse, urlunparse
        
        cleaned_links = []
        
        # Patterns that indicate tracking/redirect URLs that need query parameters
        redirect_patterns = ['/ls/click', '/wf/open', '/track/', '/redirect/', '/r/']
        
        for link in links:
            if not link or not isinstance(link, str):
                continue
                
            # Parse URL and remove query parameters
            try:
                parsed = urlparse(link.strip())
                
                # Check if this is a tracking/redirect URL that needs query parameters
                is_redirect = any(pattern in parsed.path for pattern in redirect_patterns)
                
                if is_redirect:
                    # Keep the full URL with query parameters for redirect URLs
                    clean_url = link.strip()
                    self.logger.debug(f"Preserving query params for redirect URL: {parsed.netloc}{parsed.path}")
                else:
                    # Reconstruct URL without query parameters for regular URLs
                    clean_url = urlunparse((
                        parsed.scheme,
                        parsed.netloc,
                        parsed.path,
                        parsed.params,
                        '',  # Remove query
                        parsed.fragment
                    ))
                
                cleaned_links.append(clean_url)
                
            except Exception as e:
                # If URL parsing fails, use the link as-is
                self.logger.warning(f"Failed to parse URL '{link}': {e}")
                cleaned_links.append(link)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for link in cleaned_links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)
        
        self.logger.info(f"Cleaned {len(links)} links to {len(unique_links)} unique links")
        return unique_links

    def get_hackathon_indicators(self) -> List[str]:
        """Get hackathon indicators from environment variable or use defaults."""
        default_indicators = [
            "devpost.com",
            "hackerearth.com",
            "mlh.io",
            "devfolio.co",
            "dorahacks.io",
            "angelhack.com",
            "ethglobal.com",
        ]

        # Get from environment variable, fallback to defaults
        env_indicators = os.getenv("HACKATHON_INDICATORS")
        if env_indicators:
            # Split by comma and strip whitespace
            return [
                indicator.strip()
                for indicator in env_indicators.split(",")
                if indicator.strip()
            ]

        return default_indicators

    def filter_hackathon_links(
        self, links: List[str], hackathon_indicators: List[str] = None
    ) -> List[str]:
        """Filter links to identify potential hackathon websites."""
        if hackathon_indicators is None:
            hackathon_indicators = self.get_hackathon_indicators()

        filtered_links = []

        for link in links:
            link_lower = link.lower()
            if any(indicator in link_lower for indicator in hackathon_indicators):
                filtered_links.append(link)

        return filtered_links

    async def check_duplicates_and_store_hackathons(
        self, hackathons: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Store approved hackathons in Google Sheets using batch operation.
        Checks for duplicates before storing.
        """
        if not hackathons:
            self.logger.info("💾 No hackathons to store")
            return {"count": 0, "new_hackathons": []}

        self.logger.info(f"💾 Processing {len(hackathons)} hackathons for storage...")

        # Step 1: Bulk duplicate checking
        new_hackathons = []
        duplicate_count = 0
        
        for hackathon in hackathons:
            if self.storage_manager.check_duplicate(hackathon):
                duplicate_count += 1
                self.logger.info(f"Duplicate found: {hackathon.get('name', 'Unknown')}")
            else:
                new_hackathons.append(hackathon)

        self.logger.info(f"🔍 Duplicate check complete: {duplicate_count} duplicates, {len(new_hackathons)} new hackathons")

        if not new_hackathons:
            self.logger.info("💾 No new hackathons to store after duplicate filtering")
            return {"count": 0, "new_hackathons": [], "duplicates_filtered": duplicate_count}

        # Step 2: Store new hackathons in batch
        self.logger.info(f"💾 Storing {len(new_hackathons)} new hackathons in batch...")

        if not self.dry_run:
            result = self.storage_manager.add_hackathons_batch(new_hackathons)
        else:
            self.logger.info(
                f"[DRY RUN] Would store: {', '.join([h.get('name', 'Unknown') for h in new_hackathons])}"
            )
            result = {"count": len(new_hackathons), "new_hackathons": new_hackathons}

        self.logger.info(f"📈 Successfully stored {result['count']} new hackathons")
        
        # Add duplicate count to result for reporting
        result["duplicates_filtered"] = duplicate_count

        return result

    async def post_to_twitter(self, hackathons: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Post hackathons to Twitter using pregenerated content."""
        self.logger.info(
            f"🐦 Posting to Twitter (max {self.max_twitter_posts} posts)..."
        )

        # Limit number of posts
        hackathons_to_post = hackathons[: self.max_twitter_posts]

        successful_posts = 0
        posted_names = []

        for hackathon in hackathons_to_post:
            try:
                tweet_content = self._compose_tweet_text(hackathon)
                if tweet_content:
                    # Post validated tweet with canonical link.
                    if self.twitter_poster.post_tweet(tweet_content):
                        successful_posts += 1
                        posted_names.append(hackathon.get("name", "Unknown"))
                        self.logger.info(
                            f"📱 Posted: {hackathon.get('name', 'Unknown')}"
                        )
                    else:
                        self.logger.warning(
                            f"Failed to post: {hackathon.get('name', 'Unknown')}"
                        )
                else:
                    self.logger.warning(
                        f"No tweet content for: {hackathon.get('name', 'Unknown')}"
                    )
            except Exception as e:
                self.logger.error(
                    f"Error posting {hackathon.get('name', 'Unknown')}: {e}"
                )

        # Update storage with Twitter posting status
        for name in posted_names:
            self.storage_manager.update_twitter_status(name, posted=True)

        self.logger.info(f"📱 Posted {successful_posts} hackathons to Twitter")

        return {"successful_posts": successful_posts, "posted_hackathons": posted_names}

    async def mark_emails_processed(self, emails: List[Dict[str, Any]]) -> int:
        """Mark processed emails as read."""
        self.logger.info("✉️ Marking emails as read...")

        message_ids = [email["id"] for email in emails]
        marked_count = self.email_processor.mark_emails_as_read(message_ids)

        self.logger.info(f"✅ Marked {marked_count} emails as read")
        return marked_count

    async def send_summary_email_report(
        self, results: Dict[str, Any], hackathons: List[Dict[str, Any]] = None
    ) -> bool:
        """Send summary email report to configured recipients."""
        try:
            self.logger.info(
                f"📤 Sending summary email to {len(self.summary_email_recipients)} recipients..."
            )

            # Generate email content with hackathon data
            email_content = self.email_processor.generate_summary_email_content(
                results, hackathons or []
            )

            # Create subject with timestamp and status
            status = "Success" if not results.get("errors") else "With Errors"
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            subject = f"🤖 Hackathon Curation Report - {status} - {timestamp}"

            # Send email (only if not in dry run mode)
            if not self.dry_run:
                success = self.email_processor.send_summary_email(
                    recipient_emails=self.summary_email_recipients,
                    subject=subject,
                    html_content=email_content["html"],
                    text_content=email_content["text"],
                )

                if success:
                    self.logger.info(
                        f"✅ Summary email sent successfully to {', '.join(self.summary_email_recipients)}"
                    )
                else:
                    self.logger.warning("⚠️ Failed to send summary email")

                return success
            else:
                self.logger.info(
                    f"[DRY RUN] Would send summary email to: {', '.join(self.summary_email_recipients)}"
                )
                self.logger.info(f"[DRY RUN] Email subject: {subject}")
                return True

        except Exception as e:
            error_msg = f"Error sending summary email: {e}"
            self.logger.error(error_msg)
            results["errors"].append(error_msg)
            return False

    def generate_summary(self, results: Dict[str, Any]) -> str:
        """Generate execution summary."""
        summary_parts = [
            f"Processed {results['emails_processed']} emails",
            f"Found {results['hackathons_found']} links ({results['hackathon_related_links']} hackathon-related)",
            f"Approved {results['hackathons_approved']} hackathons",
            f"Stored {results['hackathons_stored']} hackathons",
        ]

        # Add duplicate count if available
        if results.get("duplicates_filtered", 0) > 0:
            summary_parts.append(f"Filtered {results['duplicates_filtered']} duplicates")

        if results["twitter_posts"] > 0:
            summary_parts.append(f"Posted {results['twitter_posts']} to Twitter")

        if self.send_summary_email and self.summary_email_recipients:
            summary_parts.append(
                f"Summary emailed to {len(self.summary_email_recipients)} recipients"
            )

        if results["errors"]:
            summary_parts.append(f"{len(results['errors'])} errors occurred")

        return " | ".join(summary_parts)


async def main():
    """Main entry point."""
    agent = HackathonCurationAgent()
    results = await agent.run()

    # Print final summary for GitHub Actions
    print("\n🎯 EXECUTION SUMMARY:")
    print("=" * 50)
    print(f"Execution Time: {results['execution_time']}")
    print(f"Emails Processed: {results['emails_processed']}")
    print(f"Links Found: {results['hackathons_found']} ({results['hackathon_related_links']} hackathon-related)")
    print(f"Hackathons Approved: {results['hackathons_approved']}")
    print(f"Hackathons Stored: {results['hackathons_stored']}")
    if results.get("duplicates_filtered", 0) > 0:
        print(f"Duplicates Filtered: {results['duplicates_filtered']}")
    print(f"Twitter Posts: {results['twitter_posts']}")
    print(f"Summary: {results['summary']}")

    if results["errors"]:
        print("\n❌ ERRORS:")
        for error in results["errors"]:
            print(f"  - {error}")
        sys.exit(1)
    else:
        print("\n✅ Execution completed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())

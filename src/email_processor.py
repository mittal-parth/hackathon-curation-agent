import os
import json
import base64
import re
from typing import List, Dict, Optional
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from bs4 import BeautifulSoup
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.send']

class EmailProcessor:
    def __init__(self):
        self.service = None
        self.logger = logging.getLogger(__name__)
        
    def authenticate(self) -> bool:
        """Authenticate with Gmail API using service account or OAuth credentials."""
        try:
            # Try to load credentials from environment variable (for GitHub Actions)
            credentials_json = os.getenv('GMAIL_CREDENTIALS')
            if credentials_json:
                credentials_info = json.loads(credentials_json)
                
                # For service account credentials
                if 'type' in credentials_info and credentials_info['type'] == 'service_account':
                    from google.oauth2 import service_account
                    credentials = service_account.Credentials.from_service_account_info(
                        credentials_info, scopes=SCOPES
                    )
                else:
                    # For OAuth credentials
                    credentials = Credentials.from_authorized_user_info(credentials_info, SCOPES)
                    
                    # Check if token needs refresh
                    if credentials.expired and credentials.refresh_token:
                        try:
                            from google.auth.transport.requests import Request
                            credentials.refresh(Request())
                            self.logger.info("OAuth token refreshed successfully")
                        except Exception as refresh_error:
                            self.logger.error(f"Failed to refresh OAuth token: {refresh_error}")
                            return False
                
                self.service = build('gmail', 'v1', credentials=credentials)
                return True
                
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            return False
    
    def get_unread_hackathon_emails(self, label_name: str = None) -> List[Dict]:
        """
        Get unread emails with the specified label.
        
        Args:
            label_name: Gmail label name (defaults to env var HACKATHON_EMAIL_LABEL)
        
        Returns:
            List of email data dictionaries
        """
        if not label_name:
            label_name = os.getenv('HACKATHON_EMAIL_LABEL', 'Hackathons')
        
        try:
            # Get label ID
            # labels_result = self.service.users().labels().list(userId='me').execute()
            # labels = labels_result.get('labels', [])
            
            # label_id = None
            # for label in labels:
            #     if label['name'].lower() == label_name.lower():
            #         label_id = label['id']
            #         break
            
            # if not label_id:
            #     self.logger.warning(f"Label '{label_name}' not found")
            #     return []
            
            self.logger.debug(f"Label Name: {label_name}")
            # Search for unread emails with the specified label
            query = f'label:{label_name} is:unread'
            result = self.service.users().messages().list(userId='me', q=query).execute()
            messages = result.get('messages', [])
            self.logger.debug(f"Messages: {messages}")
            
            email_data = []
            for message in messages:
                email_content = self._get_email_content(message['id'])
                if email_content:
                    email_data.append(email_content)
            
            self.logger.info(f"Found {len(email_data)} unread hackathon emails")
            return email_data
            
        except HttpError as error:
            self.logger.error(f"An error occurred: {error}")
            return []
    
    def _get_email_content(self, message_id: str) -> Optional[Dict]:
        """Extract content from a specific email."""
        try:
            message = self.service.users().messages().get(userId='me', id=message_id).execute()
            
            payload = message['payload']
            headers = payload.get('headers', [])
            
            # Extract email metadata
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            # Extract email body
            body = self._extract_body(payload)
            
            # Extract links from email
            links = self._extract_links(body)
            
            return {
                'id': message_id,
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body,
                'links': links
            }
            
        except HttpError as error:
            self.logger.error(f"Error getting email content: {error}")
            return None
    
    def _extract_body(self, payload) -> str:
        """Extract email body from payload."""
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/html':
                    data = part['body']['data']
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
                    break
                elif part['mimeType'] == 'text/plain' and not body:
                    data = part['body']['data']
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
        else:
            if payload['mimeType'] == 'text/html':
                data = payload['body']['data']
                body = base64.urlsafe_b64decode(data).decode('utf-8')
            elif payload['mimeType'] == 'text/plain':
                data = payload['body']['data']
                body = base64.urlsafe_b64decode(data).decode('utf-8')
        
        return body
    
    def _extract_links(self, body: str) -> List[str]:
        """Extract all links from email body."""
        links = []
        
        # Parse HTML content
        soup = BeautifulSoup(body, 'html.parser')
        
        # Extract all anchor tags
        for link in soup.find_all('a', href=True):
            url = link['href']
            if self._is_valid_url(url):
                links.append(url)
        
        # Also extract plain text URLs using regex
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        text_urls = re.findall(url_pattern, body)
        
        for url in text_urls:
            if self._is_valid_url(url) and url not in links:
                links.append(url)
        
        return list(set(links))  # Remove duplicates
    
    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and not a tracking/unsubscribe link."""
        invalid_patterns = [
            'unsubscribe',
            'track',
            'pixel',
            'mailto:',
            'tel:',
            'javascript:',
            'data:',
            '#'
        ]
        
        url_lower = url.lower()
        return not any(pattern in url_lower for pattern in invalid_patterns)
    
    def mark_email_as_read(self, message_id: str) -> bool:
        """Mark an email as read."""
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            
            self.logger.info(f"Marked email {message_id} as read")
            return True
            
        except HttpError as error:
            self.logger.error(f"Error marking email as read: {error}")
            return False
    
    def mark_emails_as_read(self, message_ids: List[str]) -> int:
        """Mark multiple emails as read. Returns count of successfully marked emails."""
        success_count = 0
        for message_id in message_ids:
            if self.mark_email_as_read(message_id):
                success_count += 1
        return success_count
    
    def send_summary_email(self, recipient_emails: List[str], subject: str, html_content: str, text_content: str = None) -> bool:
        """
        Send a summary email to specified recipients.
        
        Args:
            recipient_emails: List of recipient email addresses
            subject: Email subject
            html_content: HTML email content
            text_content: Plain text content (optional, will be derived from HTML if not provided)
        
        Returns:
            bool: True if email was sent successfully
        """
        try:
            # Create message
            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = 'me'
            message['To'] = ', '.join(recipient_emails)
            
            # Create plain text version if not provided
            if not text_content:
                # Simple HTML to text conversion
                soup = BeautifulSoup(html_content, 'html.parser')
                text_content = soup.get_text()
            
            # Attach parts
            text_part = MIMEText(text_content, 'plain')
            html_part = MIMEText(html_content, 'html')
            
            message.attach(text_part)
            message.attach(html_part)
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            # Send email
            send_result = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            self.logger.info(f"Summary email sent successfully to {', '.join(recipient_emails)}")
            self.logger.debug(f"Message ID: {send_result['id']}")
            return True
            
        except HttpError as error:
            self.logger.error(f"Error sending summary email: {error}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error sending summary email: {e}")
            return False
    
    def generate_summary_email_content(self, results: Dict, hackathons: List[Dict] = None) -> Dict[str, str]:
        """
        Generate HTML and text content for summary email.
        
        Args:
            results: Dictionary containing execution results
            hackathons: List of hackathon data objects (optional)
            
        Returns:
            Dictionary with 'html' and 'text' keys
        """
        from datetime import datetime
        
        # Get current timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
        
        # Generate HTML content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; color: #333; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; }}
                .content {{ margin: 20px 0; }}
                .stats {{ display: flex; flex-wrap: wrap; gap: 15px; margin: 20px 0; }}
                .stat-box {{ background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 6px; padding: 15px; min-width: 150px; text-align: center; }}
                .stat-number {{ font-size: 24px; font-weight: bold; color: #495057; }}
                .stat-label {{ font-size: 12px; color: #6c757d; text-transform: uppercase; }}
                .success {{ color: #28a745; }}
                .warning {{ color: #ffc107; }}
                .error {{ color: #dc3545; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e9ecef; font-size: 12px; color: #6c757d; }}
                .execution-details {{ background: #f8f9fa; padding: 15px; border-radius: 6px; margin: 15px 0; }}
                .error-list {{ background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 6px; padding: 15px; margin: 15px 0; }}
                .hackathons-section {{ margin: 20px 0; }}
                .hackathon-card {{ background: #ffffff; border: 1px solid #dee2e6; border-radius: 8px; padding: 20px; margin: 15px 0; border-left: 4px solid #667eea; }}
                .hackathon-title {{ margin: 0 0 10px 0; color: #495057; }}
                .hackathon-link {{ color: #667eea; text-decoration: none; }}
                .tweet-content {{ background: #f8f9fa; padding: 15px; border-radius: 6px; font-family: 'Courier New', monospace; white-space: pre-line; font-size: 14px; line-height: 1.5; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🤖 Hackathon Curation Agent Report</h1>
                <p>Execution completed on {timestamp}</p>
            </div>
            
            <div class="content">
                <div class="stats">
                    <div class="stat-box">
                        <div class="stat-number">{results.get('emails_processed', 0)}</div>
                        <div class="stat-label">Emails Processed</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{results.get('hackathons_found', 0)}</div>
                        <div class="stat-label">Hackathons Found</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{results.get('hackathons_approved', 0)}</div>
                        <div class="stat-label">Hackathons Approved</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{results.get('hackathons_stored', 0)}</div>
                        <div class="stat-label">Hackathons Stored</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{results.get('twitter_posts', 0)}</div>
                        <div class="stat-label">Twitter Posts</div>
                    </div>
                </div>
                
                <div class="execution-details">
                    <h3>📊 Execution Summary</h3>
                    <p><strong>Execution Time:</strong> {results.get('execution_time', 'N/A')}</p>
                    <p><strong>Status:</strong> <span class="{'success' if not results.get('errors') else 'error'}">
                        {'✅ Completed Successfully' if not results.get('errors') else '❌ Completed with Errors'}
                    </span></p>
                    <p><strong>Summary:</strong> {results.get('summary', 'No summary available')}</p>
                </div>
        """
        
        # Add hackathons section
        if hackathons and len(hackathons) > 0:
            html_content += f"""
                <div class="hackathons-section">
                    <h3>🎯 Hackathons Found & Processed</h3>
                    <p style="margin-bottom: 20px;">Here are the {len(hackathons)} hackathons that were discovered and processed in this run:</p>
            """
            
            for i, hackathon in enumerate(hackathons, 1):
                # Get tweet content (already formatted nicely)
                tweet_content = hackathon.get('tweet', '').replace('\n', '<br>')
                hackathon_link = hackathon.get('link', '#')
                hackathon_name = hackathon.get('name', f'Hackathon {i}')
                
                html_content += f"""
                    <div class="hackathon-card">
                        <h4 class="hackathon-title">
                            <a href="{hackathon_link}" target="_blank" class="hackathon-link">
                                {hackathon_name}
                            </a>
                        </h4>
                        <div class="tweet-content">
{tweet_content}
                        </div>
                    </div>
                """
            
            html_content += """
                </div>
            """
        elif hackathons is not None:  # Only show if hackathons list was provided but empty
            html_content += """
                <div class="hackathons-section">
                    <h3>🎯 Hackathons Found & Processed</h3>
                    <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 6px; padding: 15px; margin: 15px 0; color: #856404;">
                        <p style="margin: 0;"><strong>ℹ️ No hackathons were found</strong> that met the criteria in this run.</p>
                    </div>
                </div>
            """
        
        # Add errors section if there are any
        if results.get('errors'):
            html_content += """
                <div class="error-list">
                    <h3>❌ Errors Encountered</h3>
                    <ul>
            """
            for error in results['errors']:
                html_content += f"<li>{error}</li>"
            html_content += """
                    </ul>
                </div>
            """
        
        html_content += """
            </div>
            
            <div class="footer">
                <p>This report was automatically generated by the Hackathon Curation Agent.</p>
                <p>For technical support or questions, please contact your system administrator.</p>
            </div>
        </body>
        </html>
        """
        
        # Generate text content
        text_content = f"""
        HACKATHON CURATION AGENT REPORT
        ================================
        
        Execution completed on {timestamp}
        
        STATISTICS:
        -----------
        • Emails Processed: {results.get('emails_processed', 0)}
        • Hackathons Found: {results.get('hackathons_found', 0)}
        • Hackathons Approved: {results.get('hackathons_approved', 0)}
        • Hackathons Stored: {results.get('hackathons_stored', 0)}
        • Twitter Posts: {results.get('twitter_posts', 0)}
        
        EXECUTION DETAILS:
        ------------------
        • Execution Time: {results.get('execution_time', 'N/A')}
        • Status: {'✅ Completed Successfully' if not results.get('errors') else '❌ Completed with Errors'}
        • Summary: {results.get('summary', 'No summary available')}
        """
        
        # Add hackathons section to text content
        if hackathons and len(hackathons) > 0:
            text_content += f"""
        
        HACKATHONS FOUND & PROCESSED:
        -----------------------------
        Here are the {len(hackathons)} hackathons that were discovered and processed in this run:
        
        """
            
            for i, hackathon in enumerate(hackathons, 1):
                tweet_content = hackathon.get('tweet', 'No tweet content available')
                hackathon_link = hackathon.get('link', 'No link available')
                hackathon_name = hackathon.get('name', f'Hackathon {i}')
                
                text_content += f"""
        {i}. {hackathon_name}
        Link: {hackathon_link}
        
        Tweet Content:
        {tweet_content}
        
        {'─' * 50}
        """
        elif hackathons is not None:  # Only show if hackathons list was provided but empty
            text_content += """
        
        HACKATHONS FOUND & PROCESSED:
        -----------------------------
        ℹ️ No hackathons were found that met the criteria in this run.
        """
        
        if results.get('errors'):
            text_content += """
        
        ERRORS ENCOUNTERED:
        -------------------
        """
            for i, error in enumerate(results['errors'], 1):
                text_content += f"{i}. {error}\n"
        
        text_content += """
        
        ---
        This report was automatically generated by the Hackathon Curation Agent.
        For technical support or questions, please contact your system administrator.
        """
        
        return {
            'html': html_content,
            'text': text_content
        }

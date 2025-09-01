#!/usr/bin/env python3
"""
OAuth Status Checker
This script checks the current status of your OAuth credentials and provides guidance.
"""

import os
import json
import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Gmail API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

def check_oauth_status():
    """Check the current OAuth token status."""
    print("🔍 Checking OAuth Token Status")
    print("=" * 40)
    
    # Check if credentials are available
    credentials_json = os.getenv('GMAIL_CREDENTIALS')
    if not credentials_json:
        print("❌ No GMAIL_CREDENTIALS environment variable found")
        print("\n💡 To fix this:")
        print("1. Run: python3 oauth_setup.py")
        print("2. Or set GMAIL_CREDENTIALS environment variable manually")
        return False
    
    try:
        # Parse credentials
        credentials_info = json.loads(credentials_json)
        
        # Check if it's a service account
        if 'type' in credentials_info and credentials_info['type'] == 'service_account':
            print("✅ Service account credentials found")
            print("   Service accounts don't expire, so this should work indefinitely")
            return True
        
        # Check OAuth credentials
        print("✅ OAuth credentials found")
        
        # Create credentials object
        credentials = Credentials.from_authorized_user_info(credentials_info, SCOPES)
        
        # Check token status
        if credentials.expired:
            print("⚠️  OAuth token is expired")
            
            if credentials.refresh_token:
                print("🔄 Attempting to refresh token...")
                try:
                    credentials.refresh(Request())
                    print("✅ Token refreshed successfully!")
                    return True
                except Exception as e:
                    print(f"❌ Failed to refresh token: {e}")
                    
                    if "invalid_grant" in str(e).lower():
                        print("\n🔧 Your refresh token is invalid or expired!")
                        print("   This commonly happens when:")
                        print("   - Token hasn't been used for 6+ months")
                        print("   - OAuth client was modified in Google Cloud Console")
                        print("   - Access was manually revoked")
                        print("\n💡 To fix this:")
                        print("1. Run: python3 oauth_setup.py")
                        print("2. Generate new OAuth credentials")
                        print("3. Update your GMAIL_CREDENTIALS environment variable")
                    return False
            else:
                print("❌ No refresh token available")
                print("   You need to regenerate OAuth credentials")
                return False
        else:
            # Calculate time until expiration
            import datetime
            now = datetime.datetime.now(datetime.timezone.utc)
            expires_at = credentials.expiry
            
            if expires_at:
                time_until_expiry = expires_at - now
                hours_until_expiry = time_until_expiry.total_seconds() / 3600
                
                if hours_until_expiry > 24:
                    days = hours_until_expiry / 24
                    print(f"✅ Token is valid for {days:.1f} more days")
                else:
                    print(f"⚠️  Token expires in {hours_until_expiry:.1f} hours")
                
                print("   Token will automatically refresh when needed")
                return True
            else:
                print("✅ Token is valid (no expiration time)")
                return True
                
    except json.JSONDecodeError:
        print("❌ Invalid JSON in GMAIL_CREDENTIALS")
        print("   Check your environment variable format")
        return False
    except Exception as e:
        print(f"❌ Error checking credentials: {e}")
        return False

def main():
    """Main function."""
    success = check_oauth_status()
    
    print("\n" + "=" * 40)
    if success:
        print("🎉 Your OAuth credentials are working correctly!")
        print("   You can run the main script now")
    else:
        print("🔧 Your OAuth credentials need attention")
        print("   Follow the guidance above to fix the issue")

if __name__ == "__main__":
    main()





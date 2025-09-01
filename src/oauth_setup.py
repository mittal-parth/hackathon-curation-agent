#!/usr/bin/env python3
"""
OAuth Setup Script for Gmail API
This script helps you generate OAuth credentials for personal Gmail access.
"""

import os
import json
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import logging

# Gmail API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


def setup_oauth_credentials(
    client_secrets_file: str, token_file: str = "token.json"
) -> Credentials:
    """
    Set up OAuth credentials for Gmail API access.

    Args:
        client_secrets_file: Path to your OAuth client ID JSON file
        token_file: Path to save the generated token

    Returns:
        Credentials object for Gmail API access
    """
    creds = None

    # Load existing token if available
    if os.path.exists(token_file):
        with open(token_file, "r") as token:
            creds = Credentials.from_authorized_user_info(json.load(token), SCOPES)

    # If no valid credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing token: {e}")
                creds = None

        if not creds:
            # Run the OAuth flow
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secrets_file, SCOPES
            )
            creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open(token_file, "w") as token:
                token.write(creds.to_json())

            print(f"✅ OAuth credentials saved to {token_file}")

    return creds


def export_credentials_for_github(creds: Credentials) -> str:
    """
    Export credentials in a format suitable for GitHub Secrets.

    Args:
        creds: Credentials object from OAuth flow

    Returns:
        JSON string ready for GMAIL_CREDENTIALS secret
    """
    # Convert credentials to dict format
    creds_dict = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }

    return json.dumps(creds_dict, indent=2)


def main():
    """Main function to set up OAuth credentials."""
    print("🔐 Gmail API OAuth Setup")
    print("=" * 40)
    print("This script will help you generate OAuth credentials for Gmail API access.")
    print("Use this when:")
    print("  - Setting up for the first time")
    print("  - Your OAuth token has expired")
    print("  - You get 'invalid_grant' errors")
    print()

    # Check if client secrets file exists
    client_secrets_file = input(
        "Enter path to your OAuth client ID JSON file: "
    ).strip()

    if not os.path.exists(client_secrets_file):
        print(f"❌ File not found: {client_secrets_file}")
        print("\n💡 To get this file:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Select your project")
        print("3. Go to APIs & Services → Credentials")
        print("4. Create or download OAuth 2.0 Client ID (Desktop application)")
        return

    try:
        # Set up OAuth credentials
        print("\n🔄 Setting up OAuth credentials...")
        print("This will open your browser for authentication.")
        print("Please authorize the application to access your Gmail.")
        print("⚠️  Make sure to grant access to the requested scopes.")

        creds = setup_oauth_credentials(client_secrets_file)

        if creds and creds.valid:
            print("✅ OAuth credentials generated successfully!")

            # Export for GitHub
            github_creds = export_credentials_for_github(creds)

            print(
                "\n📋 Copy the following JSON to your GitHub Secret 'GMAIL_CREDENTIALS':"
            )
            print("-" * 60)
            print(github_creds)
            print("-" * 60)

            # Save to file for easy copying
            output_file = "github_credentials.json"
            with open(output_file, "w") as f:
                f.write(github_creds)

            print(f"\n💾 Credentials also saved to {output_file} for easy copying")
            
            print("\n🔧 Next steps:")
            print("1. Update your GMAIL_CREDENTIALS environment variable")
            print("2. Or add to GitHub Secrets if using GitHub Actions")
            print("3. Test with: DEV_MODE=true DRY_RUN=true python3 main.py")

        else:
            print("❌ Failed to generate valid credentials")

    except Exception as e:
        print(f"❌ Error during OAuth setup: {e}")
        print("\n💡 Common solutions:")
        print("1. Make sure your OAuth client ID is for 'Desktop application'")
        print("2. Check that Gmail API is enabled in your Google Cloud project")
        print("3. Try clearing your browser cookies and cache")
        print("4. Make sure you're using the same Google account")


if __name__ == "__main__":
    main()

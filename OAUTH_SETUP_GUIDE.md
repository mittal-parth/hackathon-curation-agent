# 🔐 OAuth Setup Guide for Personal Gmail Access

This guide will help you set up OAuth authentication for your personal Gmail account instead of using a service account.

## 📋 Prerequisites

1. **Google Cloud Project** with Gmail API enabled
2. **OAuth 2.0 Client ID** JSON file downloaded from GCP
3. **Python environment** with the required packages installed

## 🚀 Step-by-Step Setup

### Step 1: Prepare Your OAuth Client ID

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project
3. Go to **APIs & Services** → **Credentials**
4. Click **Create Credentials** → **OAuth 2.0 Client IDs**
5. Choose **Desktop application** as the application type
6. Give it a name (e.g., "Hackathon Curation Agent")
7. Download the JSON file

### Step 2: Run the OAuth Setup Script

```bash
cd src
python3 oauth_setup.py
```

When prompted, enter the path to your downloaded OAuth client ID JSON file.

### Step 3: Complete the OAuth Flow

1. The script will open your default web browser
2. Sign in with your Google account
3. Grant permission to access your Gmail
4. You'll see a success message

### Step 4: Get Your GitHub Secret

The script will output a JSON string that looks like this:

```json
{
  "token": "ya29.a0AfB_byC...",
  "refresh_token": "1//04dX...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "123456789-abc...",
  "client_secret": "GOCSPX-...",
  "scopes": [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send"
  ]
}
```

### Step 5: Add to GitHub Secrets / local env file

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `GMAIL_CREDENTIALS`
5. Value: Paste the entire JSON output from the script
6. Click **Add secret**

## 🧪 Testing Your Setup

### Local Testing
```bash
cd src
DEV_MODE=true DRY_RUN=true python3 main.py
```

### GitHub Actions Testing
1. Push your changes to trigger the workflow
2. Check the Actions tab for execution logs
3. Verify Gmail API access works correctly

You can now finish the rest of the setup mentioned in the README.md! 🚀

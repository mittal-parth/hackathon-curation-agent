# 🚀 AI Hackathon Curation Agent

An intelligent agent that automatically curates hackathons from your email newsletters, evaluates them using AI, and posts the best ones to Twitter.

🌐 [webclub.nitk.ac.in/hackclub_nitk](https://webclub.nitk.ac.in/hackclub_nitk)

<img width="16" alt="image" src="https://github.com/user-attachments/assets/f5a6c316-51c7-4da3-ba52-b55af7e177a7" /> [x.com/HackClubNITK](https://x.com/HackClubNITK)


<img width="839" height="843" alt="image" src="https://github.com/user-attachments/assets/6cc210e4-f865-4112-a315-11c8fd824000" />


## 📧 Sample Email Report
<img width="1310" height="869" alt="image" src="https://github.com/user-attachments/assets/5423d51a-5934-4408-910e-ee5344f89ac9" />


## 🎯 What It Does

1. **Email Processing**: Monitors Gmail for Hackathons with a specific label.
2. **AI Analysis and Curation**: Uses Google Gemini along with Grouding with Google Search to analyze hackathon URLs in real-time. Automatically extracts hackathon details (dates, prizes, themes, legitimacy) and curates them based on your criteria.
3. **Storage**: Stores approved hackathons in Google Sheets with duplicate detection.
4. **Social Sharing**: Automatically posts curated hackathons to Twitter.
5. **Reporting**: Sends a summary email to the configured recipients.
6. **Automated**: Runs via GitHub Actions.

## 🚀 Quick Start

### 1. Fork & Clone Repository

```bash
git clone https://github.com/yourusername/hackathon-curation-agent.git
cd hackathon-curation-agent
```

### 2. Set Up Dependencies

```bash
pip install -r requirements.txt
```

### 🔐 API Setup

#### 1. Gmail API

Follow the instructions in [OAUTH_SETUP_GUIDE.md](OAUTH_SETUP_GUIDE.md)

**Gmail Label Setup:**
- Create a label in Gmail called "Hackathons" 
- Set up filters to automatically label incoming Hackathons
- Or use a different label name and set `HACKATHON_EMAIL_LABEL` variable

#### 2. Google Gemini API
1. Go to Google AI Studio and create an API key.
2. Add the API key to GitHub Secrets as GEMINI_API_KEY.

#### 3. Google Sheets API

1. In the same Cloud project, go to APIs & Services → Library. Enable Google Sheets API.
2. Create a Service Account (if you don’t already have one).
3. Create a JSON key (Keys → Add key → JSON). Download it.
4. Store the entire JSON in GitHub Secrets as SHEETS_CREDENTIALS.
5. Create a Google Sheet (drive.google.com → New → Google Sheets). Open it.
6. From the URL, copy the Sheet ID (long string between /d/ and /edit).
6. Share the sheet with the service account’s client_email (found in the JSON key) with Editor access.
7. Add the Sheet ID to GitHub Secrets as GOOGLE_SHEETS_ID.

#### 4. Twitter API
1. Apply for [Twitter Developer Account](https://developer.x.com/en/docs/x-api)
2. Create a new app with Read/Write permissions
3. Generate API keys and tokens
4. Add the API keys to GitHub Secrets as TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET

### 🔧 Environment Variables

#### Required Variables
```
GMAIL_CREDENTIALS={"type":"service_account",...}  # Gmail API service account JSON
GEMINI_API_KEY=your_gemini_api_key                # Google Gemini API key
SHEETS_CREDENTIALS={"type":"service_account",...} # Google Sheets API service account JSON
GOOGLE_SHEETS_ID=your_sheet_id_from_url          # Google Sheets spreadsheet ID
TWITTER_API_KEY=your_api_key                      # Twitter API key
TWITTER_API_SECRET=your_api_secret                # Twitter API secret
TWITTER_ACCESS_TOKEN=your_access_token            # Twitter access token
TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret
```

#### Optional Variables
```
HACKATHON_EMAIL_LABEL=Hackathons                 # Gmail label to monitor
HACKATHON_INDICATORS=hackathon,hack,devpost      # Keywords to identify hackathon links
DRY_RUN=false                                     # Set to "true" for testing
MAX_EMAILS_PER_RUN=10                            # Limit emails processed per run
MAX_TWITTER_POSTS=3                              # Limit Twitter posts per run
LOG_LEVEL=INFO                                    # Logging level
SEND_SUMMARY_EMAIL=false                          # Enable summary emails
SUMMARY_EMAIL_RECIPIENTS=email1,email2           # Comma-separated email addresses
HACKATHON_BATCH_SIZE=4                           # URLs to analyze in each AI batch
HACKATHON_BATCH_DELAY=1.0                        # Delay between AI analysis batches
```

#### Setup Methods

**Local Development:**
```bash
# Set DEV_MODE flag
export DEV_MODE=true

# Add environment variables to a .env at the root of the project

# Run the agent
cd src
python3 main.py
```

**Production/CI (GitHub Actions):**
- Set all environment variables as repository secrets or vars as mentioned in the github actions yml
- No `.env` file needed - uses system environment variables directly

### 🔧 Configuration

#### Hackathon Criteria (`config/criteria.yaml`)

Customize what makes a "good" hackathon:

```yaml
hackathon_criteria:
  minimum_prize: 5000  # Minimum prize in USD
  preferred_themes:
    - "AI"
    - "Web3"
    - "Healthcare"
  duration:
    min_hours: 12
    max_hours: 72
  organizer_reputation:
    trusted_organizations:
      - "MLH"
      - "DevPost"
```

### Manual Testing
```bash
# Test with dry run
DEV_MODE=true DRY_RUN=true python3 src/main.py

# Test single email
DEV_MODE=true MAX_EMAILS_PER_RUN=1 python3 src/main.py

# Debug mode
DEV_MODE=true LOG_LEVEL=DEBUG python3 src/main.py
```

### Validating Google Sheets Connection
If you're experiencing issues with data not appearing in your Google Sheet, use the validation script:

```bash
# Validate Google Sheets connection (local)
DEV_MODE=true python3 src/validate_sheets_connection.py

# Or in production (uses system env vars)
python3 src/validate_sheets_connection.py
```

## 🤝 Contributing

Pull requests welcome! Please:
1. Test your changes locally
2. Update documentation
3. Add appropriate logging
4. Follow existing code style

---

**Happy Hacking! 🚀**

import os
from typing import Dict, List, Any, Callable
from datetime import datetime
import logging
import json
import yaml
import asyncio
import time
import random
from google import genai
from google.genai import types


class HackathonAnalyzer:
    def __init__(self, criteria_file: str = None):
        """Initialize AI-powered hackathon analyzer with Gemini API and Google Search grounding."""
        self.logger = logging.getLogger(__name__)

        # Initialize Gemini client
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        self.client = genai.Client(api_key=api_key)

        # Configure grounding tool
        self.grounding_tool = types.Tool(google_search=types.GoogleSearch())

        self.config = types.GenerateContentConfig(
            tools=[self.grounding_tool]
        )

        # Load criteria for evaluation
        if not criteria_file:
            criteria_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "config", "criteria.yaml"
            )

        with open(criteria_file, "r") as f:
            self.config_data = yaml.safe_load(f)

        self.criteria = self.config_data["hackathon_criteria"]
        
        # Batch processing configuration
        self.batch_size = int(os.getenv("HACKATHON_BATCH_SIZE", "4"))
        self.batch_delay = float(os.getenv("HACKATHON_BATCH_DELAY", "1.0"))

    def _retry_with_exponential_backoff(
        self, 
        func: Callable, 
        max_retries: int = 10, 
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: bool = True
    ):
        """
        Retry a function with exponential backoff for handling intermittent API failures.
        
        Args:
            func: Function to retry (should be a lambda or callable)
            max_retries: Maximum number of retry attempts (default: 10)
            base_delay: Initial delay in seconds (default: 1.0)
            max_delay: Maximum delay between retries in seconds (default: 60.0)
            backoff_factor: Factor to multiply delay by each retry (default: 2.0)
            jitter: Whether to add random jitter to delay (default: True)
            
        Returns:
            Result of the successful function call
            
        Raises:
            Last exception encountered if all retries fail
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):  # +1 because first attempt is not a retry
            try:
                # Call the function
                result = func()
                
                # If we get here, the call was successful
                if attempt > 0:
                    self.logger.info(f"✅ Gemini API call succeeded after {attempt} retries")
                
                return result
                
            except Exception as e:
                last_exception = e
                
                # Check if this is a retryable error
                error_str = str(e)
                is_retryable = (
                    "500" in error_str or 
                    "INTERNAL" in error_str or
                    "internal error" in error_str.lower() or
                    "timeout" in error_str.lower() or
                    "temporarily unavailable" in error_str.lower()
                )
                
                if not is_retryable or attempt >= max_retries:
                    # Don't retry for non-retryable errors or if max retries reached
                    if attempt >= max_retries:
                        self.logger.error(f"❌ Gemini API call failed after {max_retries} retries: {e}")
                    else:
                        self.logger.error(f"❌ Gemini API call failed with non-retryable error: {e}")
                    raise e
                
                # Calculate delay for next retry
                delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                
                # Add jitter to avoid thundering herd
                if jitter:
                    delay += random.uniform(0, delay * 0.1)  # Add up to 10% jitter
                
                self.logger.warning(
                    f"⚠️ Gemini API call failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                    f"Retrying in {delay:.2f} seconds..."
                )
                
                time.sleep(delay)
        
        # This should never be reached due to the logic above, but just in case
        raise last_exception

    async def analyze_hackathon_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Analyze all hackathon URLs using AI in batches of 4.
        Extracts data, applies criteria, and generates tweet content.

        Args:
            urls: List of URLs to analyze

        Returns:
            List of approved hackathon data dictionaries with tweet content
        """
        if not urls:
            self.logger.info("No URLs to analyze")
            return []

        self.logger.info(
            f"🤖 AI analyzing {len(urls)} hackathon URLs in batches of {self.batch_size}..."
        )

        # Process URLs in batches
        all_hackathons = []
        total_analyzed = 0
        total_rejected = 0
        failed_batches = 0

        for i in range(0, len(urls), self.batch_size):
            batch_urls = urls[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (len(urls) + self.batch_size - 1) // self.batch_size
            
            self.logger.info(f"📦 Processing batch {batch_num}/{total_batches} with {len(batch_urls)} URLs")
            
            try:
                batch_result = await self._analyze_batch(batch_urls)
                
                if batch_result:
                    batch_hackathons = batch_result.get("approved_hackathons", [])
                    batch_analyzed = batch_result.get("total_analyzed", len(batch_urls))
                    batch_rejected = batch_result.get("rejected_count", 0)
                    
                    all_hackathons.extend(batch_hackathons)
                    total_analyzed += batch_analyzed
                    total_rejected += batch_rejected
                    
                    self.logger.info(f"✅ Batch {batch_num}: {len(batch_hackathons)} approved, {batch_rejected} rejected")
                else:
                    self.logger.warning(f"⚠️ Batch {batch_num}: Analysis failed")
                    total_analyzed += len(batch_urls)
                    failed_batches += 1
                
                # Add small delay between batches to avoid rate limiting
                if batch_num < total_batches:
                    await asyncio.sleep(self.batch_delay)
                    
            except Exception as e:
                self.logger.error(f"❌ Batch {batch_num} analysis error: {e}")
                total_analyzed += len(batch_urls)
                failed_batches += 1

        # Add metadata to each hackathon
        current_time = datetime.now().isoformat()
        for hackathon in all_hackathons:
            hackathon["analyzed_at"] = current_time
            hackathon["ai_metadata"] = {
                "search_queries": [],
                "grounding_chunks": 0,
                "grounding_supports": 0,
                "ai_search_performed": True,
                "batch_processing": True,
                "total_batches": total_batches,
                "failed_batches": failed_batches
            }

        self.logger.info(f"🎯 AI analyzed {total_analyzed} URLs successfully across {total_batches} batches")
        self.logger.info(
            f"✅ Total approved: {len(all_hackathons)}, total rejected: {total_rejected}, failed batches: {failed_batches}"
        )

        # Log approved hackathons
        for hackathon in all_hackathons:
            self.logger.info(f"🚀 AI Approved: {hackathon.get('name', 'Unknown')}")

        return all_hackathons

    async def _analyze_batch(self, urls: List[str]) -> Dict[str, Any]:
        """
        Analyze a single batch of URLs.
        
        Args:
            urls: List of URLs to analyze.
            
        Returns:
            Dictionary with batch analysis results
        """
        if not urls:
            return {}
            
        if len(urls) > self.batch_size:
            self.logger.warning(f"Batch size {len(urls)} exceeds maximum of {self.batch_size}, truncating")
            urls = urls[:self.batch_size]

        try:
            # Create prompt for batch AI analysis
            prompt = self._create_ai_analysis_prompt(urls)

            # Use retry helper for API call
            response = self._retry_with_exponential_backoff(
                lambda: self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=self.config,
                )
            )

            # Parse JSON response - extract JSON from response text
            response_text = response.text.strip()
            self.logger.debug(f"Batch LLM Response: {response_text}")
            
            # Try to find JSON in the response
            try:
                # Look for JSON block in markdown format
                if "```json" in response_text:
                    start_idx = response_text.find("```json") + 7
                    end_idx = response_text.find("```", start_idx)
                    json_text = response_text[start_idx:end_idx].strip()
                else:
                    # Try to parse the entire response as JSON
                    json_text = response_text
                
                batch_result = json.loads(json_text)
                return batch_result
                
            except json.JSONDecodeError:
                # Fallback: try to find JSON object in the response
                start_idx = response_text.find("{")
                end_idx = response_text.rfind("}") + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_text = response_text[start_idx:end_idx]
                    batch_result = json.loads(json_text)
                    return batch_result
                else:
                    raise json.JSONDecodeError("No valid JSON found in response", response_text, 0)

        except json.JSONDecodeError as e:
            self.logger.error(f"Batch response JSON parsing error: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Batch analysis error: {e}")
            return {}

    def _create_ai_analysis_prompt(self, urls: List[str]) -> str:
        """Create an AI prompt for intelligent batch analysis of multiple hackathon URLs."""

        min_prize = self.criteria.get("minimum_prize_usd", 2000)

        urls_list = "\n".join([f"{i + 1}. {url}" for i, url in enumerate(urls)])

        prompt = f"""
You are an AI hackathon analyst. Analyze these {len(urls)} hackathon URLs and extract information for legitimate hackathons that meet our criteria:

URLS TO ANALYZE:
{urls_list}

EVALUATION CRITERIA:
- Minimum prize: ${min_prize} USD (convert from crypto/other currencies if needed)
- Registration/submission deadline must NOT be in the past OR within next 24 hours
- Must be a legitimate hackathon (no scams, MLMs, or suspicious events)
- Must be open to Indian participants

For each URL, search and extract the hackathon information. ONLY include hackathons that meet ALL criteria.

Return your response as a valid JSON object (wrap in ```json code block if needed) with this EXACT structure:

{{
    "total_analyzed": {len(urls)},
    "approved_hackathons": [
        {{
            "name": "Hackathon name",
            "link": "original URL",
            "dates": "Start date - End date (YYYY-MM-DD format)",
            "registration_deadline": "YYYY-MM-DD or null if not found",
            "theme": "Main theme (e.g., AI, Web3, FinTech, Healthcare)",
            "prizes": "Prize information with USD amount",
            "prize_amount_usd": <total prize value in USD as integer>,
            "mode": "virtual/in-person/hybrid",
            "tweet": "Simple tweet with format:\\n\\nName: [name]\\nLink: [link]\\n📅 Dates: [dates]\\n🎯 Theme: [theme]\\n💰 Prizes: [prizes]"
        }}
    ],
    "rejected_count": <number of hackathons that didn't meet criteria>,
    "rejection_reasons": ["reason1", "reason2", "..."]
}}

AI ANALYSIS GUIDELINES:
1. Convert all prize amounts to USD (use current exchange rates for crypto)
2. Verify registration deadlines are in the future
3. Only include legitimate, well-organized hackathons
4. Keep theme as a single main category
5. Make tweets concise and informative
6. If you can't find clear information, don't include the hackathon
7. This is batch {len(urls)} of {self.batch_size} - focus on quality analysis for each URL

Apply your AI intelligence to extract accurate information and evaluate criteria strictly.
"""
        return prompt

    def _extract_ai_metadata(self, response) -> Dict[str, Any]:
        """Extract AI processing metadata from Gemini response."""
        try:
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "grounding_metadata"):
                    metadata = candidate.grounding_metadata
                    return {
                        "search_queries": getattr(metadata, "web_search_queries", []),
                        "grounding_chunks": len(
                            getattr(metadata, "grounding_chunks", [])
                        ),
                        "grounding_supports": len(
                            getattr(metadata, "grounding_supports", [])
                        ),
                        "ai_search_performed": True,
                    }

            return {
                "search_queries": [],
                "grounding_chunks": 0,
                "grounding_supports": 0,
                "ai_search_performed": False,
            }

        except Exception as e:
            self.logger.warning(f"Could not extract AI metadata: {e}")
            return {
                "search_queries": [],
                "grounding_chunks": 0,
                "grounding_supports": 0,
                "ai_search_performed": False,
            }

    def test_ai_connection(self) -> bool:
        """Test AI connection and capabilities."""
        try:
            # Use retry helper for API call
            self._retry_with_exponential_backoff(
                lambda: self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents="What makes a hackathon legitimate and valuable for participants?",
                    config=self.config,
                )
            )

            self.logger.info("🤖 AI connection test successful")
            return True

        except Exception as e:
            self.logger.error(f"AI connection test failed: {e}")
            return False

    def test_gemini_api(self) -> bool:
        """Test the Google Search grounding tool specifically."""
        try:
            test_prompt = "What is the current date?"
            
            # self.logger.info("🔍 Testing Google Search grounding tool...")
            
            # Use retry helper for API call
            response = self._retry_with_exponential_backoff(
                lambda: self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=test_prompt,
                    config=self.config,
                )
            )
            
            self.logger.info(f"Response: {response.text}")
            return True
        
                
        except Exception as e:
            self.logger.error(f"❌ Grounding tool test failed: {e}")
            return False

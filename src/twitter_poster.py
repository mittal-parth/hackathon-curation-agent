import os
import tweepy
import logging
import time


class TwitterPoster:
    def __init__(self):
        """Initialize Twitter API client."""
        self.logger = logging.getLogger(__name__)
        self.client = None

        # Rate limiting
        self.last_post_time = 0
        self.min_interval = 20  # Minimum seconds between posts

    def authenticate(self) -> bool:
        """Authenticate with Twitter API v2 using OAuth 1.0a User Context."""
        try:
            # Get credentials from environment variables
            api_key = os.getenv("TWITTER_API_KEY")
            api_secret = os.getenv("TWITTER_API_SECRET")
            access_token = os.getenv("TWITTER_ACCESS_TOKEN")
            access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

            if not all([api_key, api_secret, access_token, access_token_secret]):
                self.logger.error("Missing Twitter API credentials")
                return False

            # Initialize Twitter API v2 client with OAuth 1.0a User Context
            self.client = tweepy.Client(
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_token_secret,
                wait_on_rate_limit=True,
            )

            # Test authentication
            try:
                user = self.client.get_me()
                self.logger.info(f"Authenticated as: @{user.data.username}")
                return True
            except Exception as e:
                self.logger.error(f"Authentication test failed: {e}")
                return False

        except Exception as e:
            self.logger.error(f"Twitter authentication failed: {e}")
            return False

    def post_tweet(self, tweet_text: str) -> bool:
        """
        Post a single tweet to Twitter.

        Args:
            tweet_text: The text content of the tweet

        Returns:
            True if successfully posted, False otherwise
        """
        if not self.client:
            self.logger.error("Twitter client not authenticated")
            return False

        # Check rate limiting
        current_time = time.time()
        if current_time - self.last_post_time < self.min_interval:
            wait_time = self.min_interval - (current_time - self.last_post_time)
            self.logger.info(f"Rate limiting: waiting {wait_time:.1f} seconds")
            time.sleep(wait_time)

        try:
            if len(tweet_text) > 280:
                self.logger.error("Tweet exceeds 280 characters; skipping post")
                return False

            response = self.client.create_tweet(text=tweet_text)
            tweet_id = response.data["id"]

            self.logger.info(f"Posted tweet: {tweet_id}")
            self.last_post_time = time.time()
            return True

        except tweepy.TooManyRequests:
            self.logger.warning("Twitter rate limit exceeded")
            return False
        except tweepy.Forbidden as e:
            self.logger.error(f"Twitter posting forbidden: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error posting to Twitter: {e}")
            return False

    def test_connection(self) -> bool:
        """Test Twitter API connection."""
        try:
            if not self.client:
                return False

            user = self.client.get_me()
            self.logger.info(
                f"Twitter connection test successful: @{user.data.username}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Twitter connection test failed: {e}")
            return False

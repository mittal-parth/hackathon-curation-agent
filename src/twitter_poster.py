import os
import tweepy
from typing import Dict, List, Any, Optional
import logging
import time
import json


class TwitterPoster:
    def __init__(self):
        """Initialize Twitter API client."""
        self.logger = logging.getLogger(__name__)
        self.client = None
        self.api = None

        # Rate limiting
        self.last_post_time = 0
        self.min_interval = 60  # Minimum seconds between posts

    def authenticate(self) -> bool:
        """Authenticate with Twitter API v2 and v1.1."""
        try:
            # Get credentials from environment variables
            bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
            api_key = os.getenv("TWITTER_API_KEY")
            api_secret = os.getenv("TWITTER_API_SECRET")
            access_token = os.getenv("TWITTER_ACCESS_TOKEN")
            access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

            if not all(
                [bearer_token, api_key, api_secret, access_token, access_token_secret]
            ):
                self.logger.error("Missing Twitter API credentials")
                return False

            # Initialize Twitter API v2 client (for posting tweets)
            self.client = tweepy.Client(
                bearer_token=bearer_token,
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_token_secret,
                wait_on_rate_limit=True,
            )

            # Initialize Twitter API v1.1 (for media uploads if needed)
            auth = tweepy.OAuth1UserHandler(
                api_key, api_secret, access_token, access_token_secret
            )
            self.api = tweepy.API(auth, wait_on_rate_limit=True)

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

    def post_hackathon(self, hackathon: Dict[str, Any]) -> bool:
        """
        Post a hackathon to Twitter.

        Args:
            hackathon: Hackathon data with twitter_content

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
            ai_analysis = hackathon.get("ai_analysis", {})
            twitter_content = ai_analysis.get("twitter_content", {})

            if not twitter_content:
                # Generate fallback content
                twitter_content = self._generate_fallback_content(hackathon)

            # Post main tweet
            main_tweet = twitter_content.get("main_tweet", "")
            hashtags = twitter_content.get("hashtags", [])

            # Add hashtags to main tweet if there's space
            tweet_text = self._format_tweet_with_hashtags(main_tweet, hashtags)

            response = self.client.create_tweet(text=tweet_text)
            tweet_id = response.data["id"]

            self.logger.info(f"Posted main tweet for: {hackathon['title']}")

            # Post follow-up tweet or thread if available
            follow_up = twitter_content.get("follow_up_tweet")
            thread_tweets = twitter_content.get("thread_tweets", [])

            if follow_up:
                self._post_reply(tweet_id, follow_up)

            if thread_tweets:
                self._post_thread(tweet_id, thread_tweets)

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

    def _format_tweet_with_hashtags(self, tweet_text: str, hashtags: List[str]) -> str:
        """Format tweet text with hashtags, respecting character limit."""
        if not hashtags:
            return tweet_text[:280]

        hashtags_text = " " + " ".join(hashtags)

        # Check if we can fit hashtags
        if len(tweet_text) + len(hashtags_text) <= 280:
            return tweet_text + hashtags_text
        else:
            # Try to fit as many hashtags as possible
            available_space = 280 - len(tweet_text) - 1  # -1 for space
            fitted_hashtags = []
            current_length = 0

            for hashtag in hashtags:
                if current_length + len(hashtag) + 1 <= available_space:  # +1 for space
                    fitted_hashtags.append(hashtag)
                    current_length += len(hashtag) + 1
                else:
                    break

            if fitted_hashtags:
                return tweet_text + " " + " ".join(fitted_hashtags)
            else:
                return tweet_text[:280]

    def _post_reply(self, reply_to_id: str, text: str) -> Optional[str]:
        """Post a reply tweet."""
        try:
            response = self.client.create_tweet(
                text=text[:280], in_reply_to_tweet_id=reply_to_id
            )
            self.logger.info("Posted reply tweet")
            return response.data["id"]
        except Exception as e:
            self.logger.error(f"Error posting reply: {e}")
            return None

    def _post_thread(
        self, original_tweet_id: str, thread_tweets: List[str]
    ) -> List[str]:
        """Post a Twitter thread."""
        thread_ids = [original_tweet_id]

        for i, tweet_text in enumerate(thread_tweets):
            try:
                # Add thread numbering
                numbered_text = f"{i + 2}/{len(thread_tweets) + 1} {tweet_text}"

                response = self.client.create_tweet(
                    text=numbered_text[:280], in_reply_to_tweet_id=thread_ids[-1]
                )

                thread_ids.append(response.data["id"])
                self.logger.info(f"Posted thread tweet {i + 2}")

                # Small delay between thread tweets
                time.sleep(2)

            except Exception as e:
                self.logger.error(f"Error posting thread tweet {i + 2}: {e}")
                break

        return thread_ids

    def _generate_fallback_content(self, hackathon: Dict[str, Any]) -> Dict[str, Any]:
        """Generate fallback Twitter content when AI-generated content is not available."""
        title = hackathon.get("title", "Hackathon")
        prize_info = hackathon.get("prize_info", "")
        url = hackathon.get("url", "")
        themes = hackathon.get("themes", [])

        # Create main tweet
        tweet_parts = [f"🚀 {title}"]

        if prize_info:
            tweet_parts.append(f"💰 {prize_info}")

        if themes:
            tweet_parts.append(f"🔥 Themes: {', '.join(themes[:3])}")

        tweet_parts.append(url)

        main_tweet = "\n".join(tweet_parts)

        # Generate hashtags based on themes
        hashtags = ["#hackathon", "#coding"]

        for theme in themes[:3]:
            theme_hashtag = f"#{theme.replace(' ', '').lower()}"
            if theme_hashtag not in hashtags:
                hashtags.append(theme_hashtag)

        return {
            "main_tweet": main_tweet,
            "hashtags": hashtags[:5],  # Limit to 5 hashtags
            "follow_up_tweet": None,
            "thread_tweets": [],
        }

    def post_multiple_hackathons(
        self,
        hackathons: List[Dict[str, Any]],
        max_posts: int = 5,
        interval_minutes: int = 30,
    ) -> Dict[str, Any]:
        """
        Post multiple hackathons with appropriate spacing.

        Args:
            hackathons: List of hackathon data
            max_posts: Maximum number of posts per run
            interval_minutes: Minutes between posts

        Returns:
            Dictionary with posting results
        """
        results = {
            "successful_posts": 0,
            "failed_posts": 0,
            "posted_hackathons": [],
            "failed_hackathons": [],
        }

        posts_made = 0

        for hackathon in hackathons:
            if posts_made >= max_posts:
                self.logger.info(f"Reached maximum posts limit ({max_posts})")
                break

            success = self.post_hackathon(hackathon)

            if success:
                results["successful_posts"] += 1
                results["posted_hackathons"].append(hackathon["title"])
                posts_made += 1

                # Wait between posts (except for the last one)
                if posts_made < min(max_posts, len(hackathons)):
                    wait_seconds = interval_minutes * 60
                    self.logger.info(
                        f"Waiting {interval_minutes} minutes before next post"
                    )
                    time.sleep(wait_seconds)
            else:
                results["failed_posts"] += 1
                results["failed_hackathons"].append(hackathon["title"])

        return results

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

    def get_tweet_engagement(self, tweet_id: str) -> Optional[Dict[str, int]]:
        """Get engagement metrics for a tweet."""
        try:
            tweet = self.client.get_tweet(tweet_id, tweet_fields=["public_metrics"])

            if tweet.data and hasattr(tweet.data, "public_metrics"):
                return {
                    "retweet_count": tweet.data.public_metrics["retweet_count"],
                    "like_count": tweet.data.public_metrics["like_count"],
                    "reply_count": tweet.data.public_metrics["reply_count"],
                    "quote_count": tweet.data.public_metrics["quote_count"],
                }

            return None

        except Exception as e:
            self.logger.error(f"Error getting tweet engagement: {e}")
            return None

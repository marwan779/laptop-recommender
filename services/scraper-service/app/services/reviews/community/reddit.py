"""Reddit community scraper with a strict 4-layer relevance gate.

Searches a fixed set of laptop-focused subreddits for each aspect query, then
applies:

    1. Model token match  - the post must mention the actual model/sub-model code.
    2. Negative filter    - discard deal/sale listings.
    3. Content depth      - skip one-liners and posts with no discussion.
    4. Ranking            - deduplicate by post id, rank by score, keep top N.

Top comments are then fetched for each surviving post.

Every network failure is fail-open: a failed subreddit, query, post body, or
comment thread is skipped rather than raising.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import quote_plus

from app.domain.reviews.subject import build_subject
from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import CommunityComment, RedditPost
from app.services.reviews.community.contracts import ICommunityPlatformScraper

logger = logging.getLogger("scraper.services.reviews.community.reddit")

REDDIT_BASE_URL = "https://www.reddit.com"

# Reddit rejects generic clients; this UA identifies the crawler honestly.
DEFAULT_USER_AGENT = "laptop-recommender/1.0 (community review collector; contact: ops@laptop-recommender.local)"

# Minimum length for a comment to be considered substantive.
MIN_COMMENT_LENGTH = 15

# Tokens that look code-like but are hardware components, not model codes.
_COMPONENT_TOKENS: frozenset[str] = frozenset(
    {
        "RTX",
        "GTX",
        "RAM",
        "SSD",
        "HDD",
        "NVME",
        "PCIE",
        "DDR4",
        "DDR5",
        "LPDDR5",
        "WIFI",
        "HDMI",
        "USB",
        "OLED",
        "IPS",
        "FHD",
        "QHD",
        "WQXGA",
        "INTEL",
        "AMD",
        "NVIDIA",
        "RYZEN",
        "CORE",
        "ULTRA",
        "TOPS",
        "WINDOWS",
        "RTX50",
        "RTX40",
    }
)

# Keywords indicating a deal/sale listing rather than a discussion.
_NEGATIVE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"\[deal\]",
        r"\bdeals?\b",
        r"\bsale\b",
        r"\bfor sale\b",
        r"\bdiscount",
        r"\bcoupons?\b",
        r"\bpromo(?:\s*code)?\b",
        r"\bvouchers?\b",
        r"\bclearance\b",
        r"\bblack friday\b",
        r"\bcyber monday\b",
        r"\bprice drop\b",
        r"\blowest price\b",
        r"\b(?:wts|wtb|fs)\b",
        r"\bbuy(?:ing)? now\b",
    )
)

_CODE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{2,}")
_HYPHENATED_CODE_RE = re.compile(r"\b([A-Za-z]{1,4}\d{3,5}[A-Za-z0-9]{0,4})-[A-Za-z0-9]{4,8}\b")


class SubTargets(StrEnum):
    """Subreddits searched for laptop discussions."""

    GAMING_LAPTOPS = "GamingLaptops"
    SUGGEST_A_LAPTOP = "SuggestALaptop"
    LAPTOPS = "laptops"
    LENOVO_LEGION = "LenovoLegion"
    ASUS_ROG = "ASUSROG"
    AMD_LAPTOPS = "AMDLaptops"


class RedditPlatformScraper(ICommunityPlatformScraper):
    """Scrape Reddit for laptop review discussions with strict relevance gating."""

    platform_name = "reddit"

    def __init__(
        self,
        max_posts: int = 10,
        min_body_length: int = 40,
        min_comments: int = 2,
        http_client: Any | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        request_delay_seconds: float = 0.5,
        max_comments_per_post: int = 5,
        subreddits: tuple[SubTargets, ...] = tuple(SubTargets),
    ) -> None:
        self.max_posts = max_posts
        self.min_body_length = min_body_length
        self.min_comments = min_comments
        self.http_client = http_client
        self.user_agent = user_agent
        # Politeness delay between Reddit requests; Reddit aggressively rate-limits.
        self.request_delay_seconds = request_delay_seconds
        self.max_comments_per_post = max_comments_per_post
        self.subreddits = subreddits

    async def scrape_for_target(
        self,
        laptop_target: LaptopReviewTarget,
        queries: list[str],
    ) -> list[RedditPost]:
        """Return gated, ranked Reddit posts for one laptop target."""
        model_tokens = self._model_tokens(laptop_target)
        fallback_terms = self._fallback_terms(laptop_target)

        if not model_tokens and not fallback_terms:
            logger.debug("No identifying tokens for target; skipping Reddit search.")
            return []

        candidates: dict[str, dict[str, Any]] = {}

        async with self._client_context() as client:
            for subreddit in self.subreddits:
                for query in queries:
                    posts = await self._search(client, subreddit.value, query)
                    for post in posts:
                        post_id = str(post.get("id") or "")
                        if not post_id or post_id in candidates:
                            continue
                        if not self._passes_gate(post, model_tokens, fallback_terms):
                            continue
                        candidates[post_id] = post

            ranked = sorted(
                candidates.values(),
                key=lambda p: int(p.get("score") or 0),
                reverse=True,
            )[: self.max_posts]

            results: list[RedditPost] = []
            for post in ranked:
                comments = await self._fetch_comments(client, post)
                results.append(self._to_reddit_post(post, comments))

        logger.info(
            "Reddit collected %d posts for '%s' (from %d gated candidates).",
            len(results),
            self._display_name(laptop_target),
            len(candidates),
        )
        return results

    # ── Relevance gate ─────────────────────────────────────────────────────

    def _passes_gate(
        self,
        post: dict[str, Any],
        model_tokens: set[str],
        fallback_terms: set[str],
    ) -> bool:
        """Apply the 4-layer relevance gate to a single post."""
        title = str(post.get("title") or "")
        body = str(post.get("selftext") or "")

        # Layer 1: model/sub-model code must appear in title or body.
        if not self._matches_identity(title, body, model_tokens, fallback_terms):
            return False

        # Layer 2: reject deal/sale listings.
        if self._is_deal_post(title, body):
            return False

        # Layer 3: require substantive content and at least some discussion.
        if len(body.strip()) < self.min_body_length:
            return False
        if int(post.get("num_comments") or 0) < self.min_comments:
            return False

        # Layer 4 (ranking) is applied after collection.
        return True

    @staticmethod
    def _matches_identity(
        title: str,
        body: str,
        model_tokens: set[str],
        fallback_terms: set[str],
    ) -> bool:
        """Layer 1: require a specific model code, else a distinctive phrase."""
        haystack = f"{title} {body}".upper()

        if model_tokens:
            return any(token in haystack for token in model_tokens)

        # No code available on the target: fall back to the identity phrase.
        normalized = re.sub(r"[^A-Z0-9]+", " ", haystack)
        return any(term in normalized for term in fallback_terms)

    @staticmethod
    def _is_deal_post(title: str, body: str) -> bool:
        """Layer 2: detect deal/sale listings."""
        haystack = f"{title}\n{body}".lower()
        return any(pattern.search(haystack) for pattern in _NEGATIVE_PATTERNS)

    # ── Identity token extraction ──────────────────────────────────────────

    @classmethod
    def _model_tokens(cls, target: LaptopReviewTarget) -> set[str]:
        """Extract model/sub-model codes that must appear in a relevant post."""
        tokens: set[str] = set()

        excluded = {
            *(target.brand or "").upper().split(),
            *(target.laptop_family or "").upper().split(),
            *_COMPONENT_TOKENS,
        }

        for source in (
            target.laptop_model,
            *target.skus,
            target.mpn,
            target.manufacturer_part_number,
        ):
            if not source:
                continue
            text = str(source)

            # Hyphenated SKUs: X1605VA-OACH007W -> also keep the chassis prefix X1605VA.
            for match in _HYPHENATED_CODE_RE.finditer(text):
                code = match.group(1).upper()
                if code not in excluded:
                    tokens.add(code)

            for raw in _CODE_TOKEN_RE.findall(text):
                token = raw.upper().strip("-")
                if len(token) < 4:
                    continue
                # Require at least one digit and at least one letter
                if not (any(char.isdigit() for char in token) and any(char.isalpha() for char in token)):
                    continue
                if token in excluded:
                    continue
                tokens.add(token)

                # For hyphenated tokens like 15-FA2352TX or FA507NV-LP023W:
                if "-" in token:
                    for part in token.split("-"):
                        part_clean = part.strip()
                        if (
                            len(part_clean) >= 4
                            and any(char.isdigit() for char in part_clean)
                            and any(char.isalpha() for char in part_clean)
                            and part_clean not in excluded
                        ):
                            tokens.add(part_clean)

        return tokens

    @classmethod
    def _fallback_terms(cls, target: LaptopReviewTarget) -> set[str]:
        """Build a distinctive phrase for targets that expose no model code."""
        subject = build_subject(target)
        normalized = re.sub(r"[^A-Z0-9]+", " ", subject.upper()).strip()
        terms: set[str] = set()
        if normalized:
            terms.add(normalized)
            # Also accept the subject tail without the brand prefix.
            brand_prefix = (target.brand or "").strip().upper()
            if brand_prefix and normalized.startswith(brand_prefix):
                tail = normalized[len(brand_prefix) :].strip()
                if tail:
                    terms.add(tail)
        return terms

    @staticmethod
    def _display_name(target: LaptopReviewTarget) -> str:
        return build_subject(target)

    # ── Network ────────────────────────────────────────────────────────────

    def _client_context(self) -> Any:
        """Yield an injected client, or create a short-lived one."""
        return _ClientContext(self.http_client, self.user_agent)

    async def _search(
        self,
        client: Any,
        subreddit: str,
        query: str,
    ) -> list[dict[str, Any]]:
        """Search one subreddit. Fail-open to an empty list."""
        url = f"{REDDIT_BASE_URL}/r/{subreddit}/search.json?q={quote_plus(query)}&restrict_sr=1&sort=relevance&limit=10"
        payload = await self._get_json(client, url)
        if not payload:
            return []

        children = (payload.get("data") or {}).get("children") or []
        return [
            child.get("data", {})
            for child in children
            if isinstance(child, dict) and isinstance(child.get("data"), dict)
        ]

    async def _fetch_comments(self, client: Any, post: dict[str, Any]) -> list[CommunityComment]:
        """Fetch top comments for a post. Fail-open to an empty list."""
        permalink = str(post.get("permalink") or "")
        if not permalink:
            return []

        url = f"{REDDIT_BASE_URL}{permalink}.json?sort=top&limit={self.max_comments_per_post}"
        payload = await self._get_json(client, url)
        if not isinstance(payload, list) or len(payload) < 2:
            return []

        comment_listing = payload[1]
        children = (comment_listing.get("data") or {}).get("children") or []

        comments: list[CommunityComment] = []
        for child in children:
            if len(comments) >= self.max_comments_per_post:
                break
            if not isinstance(child, dict):
                continue
            data = child.get("data") or {}
            if child.get("kind") != "t1":
                continue

            author = data.get("author")
            if not author or author in ("[deleted]", "[removed]"):
                continue

            text = str(data.get("body") or "").strip()
            if len(text) < MIN_COMMENT_LENGTH:
                continue

            comments.append(
                CommunityComment(
                    comment_id=str(data.get("id") or "") or None,
                    author=author,
                    comment_text=text,
                    score=data.get("score"),
                    published_at=self._to_datetime(data.get("created_utc")),
                )
            )

        return comments

    async def _get_json(self, client: Any, url: str) -> Any:
        """GET a JSON payload, tolerating every transport/HTTP failure."""
        if self.request_delay_seconds:
            await asyncio.sleep(self.request_delay_seconds)

        try:
            response = await client.get(url, headers={"User-Agent": self.user_agent})
        except Exception as exc:  # noqa: BLE001 - network failures are expected
            logger.debug("Reddit request failed for %s: %s", url, exc)
            return None

        status = getattr(response, "status_code", 200)
        if status == 429:
            logger.warning("Reddit rate limit hit (429) for %s", url)
            return None
        if status >= 400:
            logger.debug("Reddit returned HTTP %s for %s", status, url)
            return None

        try:
            return response.json()
        except Exception as exc:  # noqa: BLE001 - malformed payload
            logger.debug("Reddit returned invalid JSON for %s: %s", url, exc)
            return None

    # ── Mapping ────────────────────────────────────────────────────────────

    @staticmethod
    def _to_reddit_post(post: dict[str, Any], comments: list[CommunityComment]) -> RedditPost:
        permalink = str(post.get("permalink") or "")
        post_url = str(post.get("url") or "")
        if not post_url.startswith("http"):
            post_url = f"{REDDIT_BASE_URL}{permalink}" if permalink else ""

        return RedditPost(
            post_id=str(post.get("id") or ""),
            subreddit=str(post.get("subreddit") or ""),
            post_title=str(post.get("title") or ""),
            post_url=post_url,
            author=post.get("author") if post.get("author") not in ("[deleted]", None) else None,
            published_at=RedditPlatformScraper._to_datetime(post.get("created_utc")),
            score=post.get("score"),
            post_body=str(post.get("selftext") or ""),
            comments=comments,
        )

    @staticmethod
    def _to_datetime(value: Any) -> datetime | None:
        """Convert a Reddit epoch timestamp into a timezone-aware datetime."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (TypeError, ValueError, OSError):
            return None


class _ClientContext:
    """Async context manager providing an injected or self-owned HTTP client.

    An injected client is borrowed, never closed — the caller owns its lifecycle.
    """

    def __init__(self, injected: Any | None, user_agent: str) -> None:
        self._injected = injected
        self._user_agent = user_agent
        self._owned: Any | None = None

    async def __aenter__(self) -> Any:
        if self._injected is not None:
            return self._injected

        import httpx  # noqa: PLC0415 - optional at import time

        self._owned = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            follow_redirects=True,
            headers={"User-Agent": self._user_agent},
        )
        return self._owned

    async def __aexit__(self, *exc_info: Any) -> bool:
        if self._owned is not None:
            await self._owned.aclose()
            self._owned = None
        return False


__all__ = ["DEFAULT_USER_AGENT", "REDDIT_BASE_URL", "RedditPlatformScraper", "SubTargets"]

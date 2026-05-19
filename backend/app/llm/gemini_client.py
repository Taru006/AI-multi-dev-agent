"""
Gemini API Client — production-grade wrapper with:
- Retry logic with exponential backoff
- Streaming support
- Token usage tracking
- Model switching (pro vs flash)
- Context window management
"""

import asyncio
import time
from typing import AsyncIterator, Optional
import google.generativeai as genai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# Configure Gemini
genai.configure(api_key=settings.GEMINI_API_KEY)

# Generation config defaults
_DEFAULT_GENERATION_CONFIG = genai.types.GenerationConfig(
    max_output_tokens=settings.GEMINI_MAX_TOKENS,
    temperature=settings.GEMINI_TEMPERATURE,
)

# Safety settings — relaxed for code generation
_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
]


class TokenUsageTracker:
    """Thread-safe token usage accumulator."""

    def __init__(self):
        self._total_input = 0
        self._total_output = 0
        self._lock = asyncio.Lock()

    async def add(self, input_tokens: int, output_tokens: int):
        async with self._lock:
            self._total_input += input_tokens
            self._total_output += output_tokens

    @property
    def total_tokens(self) -> int:
        return self._total_input + self._total_output

    def summary(self) -> dict:
        return {
            "input_tokens": self._total_input,
            "output_tokens": self._total_output,
            "total_tokens": self.total_tokens,
        }


class GeminiClient:
    """
    Production-grade Gemini client for multi-agent use.

    Features:
    - Automatic retries with exponential backoff
    - Streaming + non-streaming generation
    - Model routing (pro for complex tasks, flash for quick ones)
    - Token tracking per session
    """

    def __init__(self, use_flash: bool = False):
        model_name = settings.GEMINI_FLASH_MODEL if use_flash else settings.GEMINI_MODEL
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=_DEFAULT_GENERATION_CONFIG,
            safety_settings=_SAFETY_SETTINGS,
        )
        self.model_name = model_name
        self.token_tracker = TokenUsageTracker()

    @retry(
        stop=stop_after_attempt(settings.GEMINI_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Generate a response for a given prompt.

        Args:
            prompt: User prompt
            system_prompt: Optional system instruction
            max_tokens: Override max output tokens
            temperature: Override temperature

        Returns:
            Generated text string
        """
        generation_config = genai.types.GenerationConfig(
            max_output_tokens=max_tokens or settings.GEMINI_MAX_TOKENS,
            temperature=temperature or settings.GEMINI_TEMPERATURE,
        )

        # Build conversation history with optional system context
        messages = []
        if system_prompt:
            messages.append({"role": "user", "parts": [f"[SYSTEM CONTEXT]\n{system_prompt}"]})
            messages.append({"role": "model", "parts": ["Understood. I am ready to assist."]})
        messages.append({"role": "user", "parts": [prompt]})

        start = time.time()
        try:
            chat = self.model.start_chat(history=messages[:-1])
            response = await asyncio.to_thread(
                chat.send_message,
                prompt,
                generation_config=generation_config,
            )
            elapsed = time.time() - start

            # Track tokens
            if hasattr(response, "usage_metadata"):
                await self.token_tracker.add(
                    response.usage_metadata.prompt_token_count,
                    response.usage_metadata.candidates_token_count,
                )

            logger.debug(
                "Gemini generation complete",
                model=self.model_name,
                elapsed_s=round(elapsed, 2),
                tokens=self.token_tracker.summary(),
            )
            return response.text

        except Exception as exc:
            logger.error("Gemini API error", error=str(exc), model=self.model_name)
            raise

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Stream generation token by token.
        Yields text chunks as they arrive.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "user", "parts": [f"[SYSTEM CONTEXT]\n{system_prompt}"]})
            messages.append({"role": "model", "parts": ["Understood. I am ready to assist."]})

        chat = self.model.start_chat(history=messages)

        def _stream():
            return chat.send_message(prompt, stream=True)

        response = await asyncio.to_thread(_stream)
        for chunk in response:
            if chunk.text:
                yield chunk.text

    def get_token_usage(self) -> dict:
        return self.token_tracker.summary()


# Module-level singleton clients
_pro_client: Optional[GeminiClient] = None
_flash_client: Optional[GeminiClient] = None


def get_gemini_client(use_flash: bool = False) -> GeminiClient:
    """Get or create a Gemini client singleton."""
    global _pro_client, _flash_client
    if use_flash:
        if _flash_client is None:
            _flash_client = GeminiClient(use_flash=True)
        return _flash_client
    else:
        if _pro_client is None:
            _pro_client = GeminiClient(use_flash=False)
        return _pro_client

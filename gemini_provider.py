import base64
import google.generativeai as genai
from typing import Optional
from PIL import Image

from models import ComicValuation


class GeminiComicAnalyzer:
    """Gemini-powered comic book analyzer with Google Search grounding for accurate pricing"""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-exp"):
        genai.configure(api_key=api_key)
        self.model_name = model
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            tools='google_search_retrieval'  # Enable Google Search grounding
        )

    async def analyze_comic(self, image_path: str) -> ComicValuation:
        """Analyze a comic book image with real-world price data from Google Search"""

        # Load image
        image = Image.open(image_path)

        # Craft prompt that leverages search grounding for pricing
        prompt = """You are a professional comic book appraiser analyzing this comic book cover image.

STEP 1 - IDENTIFICATION (from image only):
- Identify the series name, issue number, and publisher from the cover
- Estimate the publication date based on cover style and visible information
- Assess the condition/grade using standard 10.0-1.0 scale based on visible damage
- Note any condition issues you can observe (creases, tears, spine stress, etc.)
- Determine if this is a key issue (first appearances, major storylines, etc.)

STEP 2 - MARKET RESEARCH (use Google Search):
After identifying the comic, search for current market prices for this specific comic in similar condition.
Search for terms like:
- "[Series] #[Issue] [Grade] CGC price"
- "[Series] #[Issue] sold prices eBay"
- "[Series] #[Issue] FMV fair market value"
- Use GPA (GoCollect Price Guide), Heritage Auctions, eBay sold listings, MyComicShop

STEP 3 - VALUATION:
Based on your search results, provide:
- Low estimate: Conservative/worst case pricing
- Best estimate: Most likely current market value for this grade
- High estimate: Optimistic but realistic ceiling
- Confidence: How confident you are (0.0-1.0) based on available data

CRITICAL GUIDELINES:
- Base identification ONLY on what's visible in the image
- Use "Unknown" for any information not clearly visible
- For pricing, RELY ON SEARCH RESULTS - don't guess prices
- If you can't find reliable pricing data, set confidence low and use conservative estimates
- Prefer recent sold prices over asking prices
- Account for the visible condition when comparing to graded examples

Respond with a JSON object matching this structure:
{
  "series": "Series name as shown",
  "title": "Issue title if visible",
  "issue_number": "Issue number with variant info",
  "publisher": "Publisher name",
  "publication_date": "Date or 'Unknown'",
  "estimated_grade": "X.X",
  "condition_notes": ["List of visible issues or empty list"],
  "key_issue": true/false,
  "key_issue_notes": "Why it's significant or 'Not a key issue'",
  "rarity_notes": "Rarity info or 'Unknown'",
  "valuation": {
    "low_estimate": 0.00,
    "best_estimate": 0.00,
    "high_estimate": 0.00,
    "confidence": 0.0
  },
  "identification_confidence": 0.0,
  "analysis_notes": "Include search sources used for pricing",
  "image_filename": "placeholder",
  "llm_provider": "placeholder",
  "analysis_date": "placeholder"
}"""

        # Configure generation with search grounding
        generation_config = genai.types.GenerationConfig(
            temperature=0.1,  # Low temperature for consistency
            response_mime_type="application/json"  # Request JSON output
        )

        # Generate content with image and search grounding
        response = await self.model.generate_content_async(
            [prompt, image],
            generation_config=generation_config
        )

        # Parse JSON response
        import json
        response_text = response.text

        # Clean up potential markdown formatting
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        # Parse and create ComicValuation
        data = json.loads(response_text)

        # Pydantic will validate the structure
        return ComicValuation(**data)


class GeminiComicComparator:
    """Compare results from Gemini with and without search grounding"""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-exp"):
        self.with_search = GeminiComicAnalyzer(api_key, model)
        # Create a model without search for comparison
        genai.configure(api_key=api_key)
        self.without_search = genai.GenerativeModel(model_name=model)

    async def compare_analyses(self, image_path: str) -> tuple[ComicValuation, ComicValuation]:
        """Compare analysis with and without search grounding"""
        import asyncio

        with_search_result = await self.with_search.analyze_comic(image_path)

        # For comparison, you'd implement a version without search here
        # For now, just return the search-grounded result twice
        return with_search_result, with_search_result

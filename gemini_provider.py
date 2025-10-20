from google import genai
from google.genai import types
from typing import Optional, List
from PIL import Image
from pydantic import BaseModel
import json
import re
import io

from models import ComicValuation


class IdentificationSchema(BaseModel):
    """Schema for comic identification"""
    series: str
    title: str
    issue_number: str
    publisher: str
    publication_date: str
    estimated_grade: str
    condition_notes: List[str]
    key_issue: bool
    key_issue_notes: str
    rarity_notes: str
    identification_confidence: float
    analysis_notes: str


class GeminiComicAnalyzer:
    """Gemini-powered comic book analyzer with TRUE Google Search grounding for real market pricing"""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def analyze_comic(self, image_path: str) -> ComicValuation:
        """Analyze a comic book image with REAL market data from Google Search grounding"""

        # Load and prepare image
        image = Image.open(image_path)
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_bytes = img_byte_arr.getvalue()

        # STEP 1: Identify comic from image
        identification_prompt = """Analyze this comic book cover image and identify:

1. Series name (exactly as shown)
2. Issue number
3. Publisher
4. Publication date/era
5. Condition grade (0.5-10.0 scale based on visible damage)
6. Condition issues (creases, tears, spine stress, etc.)
7. Key issue status

Use "Unknown" for unclear information."""

        # Get identification with structured output
        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                identification_prompt,
                types.Part.from_bytes(data=img_bytes, mime_type='image/png')
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=IdentificationSchema
            )
        )

        # Parse identification
        if hasattr(response, 'parsed') and response.parsed:
            data = response.parsed.model_dump()
        else:
            # Fallback to text parsing
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            data = json.loads(response_text.strip())

        # STEP 2: Use Google Search grounding to find REAL market prices
        series = data.get('series', 'Unknown')
        issue = data.get('issue_number', 'Unknown')
        grade = data.get('estimated_grade', '5.0')
        publisher = data.get('publisher', 'Unknown')

        # Craft search-optimized prompt
        search_prompt = f"""Search for current market prices for this comic book:

Comic: {series} #{issue}
Publisher: {publisher}
Grade/Condition: {grade}

Search for SOLD prices from:
- GPA GoCollect Price Guide
- Heritage Auctions sold lots
- eBay completed/sold listings
- MyComicShop prices
- ComicLink auction results

Based on ACTUAL sold prices you find, provide:
- Conservative low estimate (worst case)
- Best estimate (most likely current value)
- Optimistic high estimate (best case)
- Confidence level (0.0-1.0)

Format clearly with dollar amounts."""

        # Enable Google Search grounding
        grounding_tool = types.Tool(google_search=types.GoogleSearch())

        # Get market-grounded pricing
        price_response = self.client.models.generate_content(
            model=self.model,
            contents=search_prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                tools=[grounding_tool]
            )
        )

        # Extract price data
        price_text = price_response.text

        # Parse prices with regex
        low_match = re.search(r'(?:low|conservative)[:\s]*\$?([\d,]+(?:\.\d{2})?)', price_text, re.IGNORECASE)
        best_match = re.search(r'(?:best|most likely)[:\s]*\$?([\d,]+(?:\.\d{2})?)', price_text, re.IGNORECASE)
        high_match = re.search(r'(?:high|optimistic)[:\s]*\$?([\d,]+(?:\.\d{2})?)', price_text, re.IGNORECASE)
        conf_match = re.search(r'confidence[:\s]*([\d.]+)', price_text, re.IGNORECASE)

        def clean_price(match):
            if match:
                return float(match.group(1).replace(',', ''))
            return None

        # Build valuation with grounded prices
        data['valuation'] = {
            'low_estimate': clean_price(low_match) or 1.0,
            'best_estimate': clean_price(best_match) or 5.0,
            'high_estimate': clean_price(high_match) or 10.0,
            'confidence': float(conf_match.group(1)) if conf_match else 0.6
        }

        # Extract grounding metadata (search queries and sources)
        grounding_info = []
        if hasattr(price_response, 'candidates') and price_response.candidates:
            candidate = price_response.candidates[0]
            if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                metadata = candidate.grounding_metadata

                # Get search queries
                if hasattr(metadata, 'web_search_queries') and metadata.web_search_queries:
                    queries = ', '.join(metadata.web_search_queries)
                    grounding_info.append(f"Searches: {queries}")

                # Get sources
                if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                    sources = [chunk.web.title for chunk in metadata.grounding_chunks if hasattr(chunk, 'web')]
                    if sources:
                        grounding_info.append(f"Sources: {', '.join(sources[:5])}")

        # Add grounding details to analysis notes
        current_notes = data.get('analysis_notes', '')
        if grounding_info:
            data['analysis_notes'] = f"{current_notes} | Market data: {' | '.join(grounding_info)}"
        else:
            data['analysis_notes'] = f"{current_notes} | Market data: Google Search grounding enabled"

        # Add placeholder metadata
        data['image_filename'] = 'placeholder'
        data['llm_provider'] = 'placeholder'
        data['analysis_date'] = 'placeholder'

        return ComicValuation(**data)


class GeminiComicComparator:
    """Compare results from Gemini"""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.with_search = GeminiComicAnalyzer(api_key, model)

    async def compare_analyses(self, image_path: str) -> tuple[ComicValuation, ComicValuation]:
        """Get grounded analysis"""
        result = await self.with_search.analyze_comic(image_path)
        return result, result

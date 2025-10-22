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

1. Series name (exactly as shown, including volume designation if present)
2. Issue number (including variant information if applicable)
3. Publisher
4. Publication date/year (CRITICAL: Be as specific as possible - look for date in cover price box, UPC area, or publisher info)
5. Volume/Era information (e.g., "Vol 2", "Heroes Reborn", "1996 relaunch", etc.)
6. Condition grade (0.5-10.0 scale based on visible damage)
7. Condition issues (creases, tears, spine stress, etc.)
8. Key issue status

IMPORTANT: For publication date, check:
- The cover price box (often shows month/year)
- UPC/barcode area
- Copyright information
- Cover design style (modern vs vintage)

This date is CRITICAL for accurate pricing. For example:
- Iron Man #1 from 1968 is worth thousands
- Iron Man #1 from 1996 (Heroes Reborn) is worth a few dollars

Use "Unknown" only if truly impossible to determine."""

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

        # Clean the estimated_grade field to remove descriptive text
        # Gemini sometimes returns "8.0 Very Fine" or "8.0 - Very Fine" instead of just "8.0"
        if 'estimated_grade' in data and isinstance(data['estimated_grade'], str):
            # Extract just the numeric part (e.g., "8.0" from "8.0 Very Fine")
            grade_str = data['estimated_grade'].strip()
            # Split on space, dash, or parenthesis and take first part
            grade_str = grade_str.split()[0].split('-')[0].split('(')[0].strip()
            data['estimated_grade'] = grade_str

        # STEP 2: Use Google Search grounding to find REAL market prices
        series = data.get('series', 'Unknown')
        issue = data.get('issue_number', 'Unknown')
        grade = data.get('estimated_grade', '5.0')
        publisher = data.get('publisher', 'Unknown')
        pub_date = data.get('publication_date', 'Unknown')

        # Craft search-optimized prompt with SPECIFIC publication details
        search_prompt = f"""Search for current market prices for this SPECIFIC comic book:

Comic: {series} #{issue}
Publisher: {publisher}
Publication Date/Year: {pub_date}
Grade/Condition: {grade}

IMPORTANT: Make sure to search for the EXACT issue from {pub_date}, NOT earlier volumes or first appearances with the same issue number.

For example:
- Iron Man #1 (1996 Heroes Reborn) is DIFFERENT from Iron Man #1 (1968 original)
- Spider-Man #1 (1990) is DIFFERENT from Amazing Spider-Man #1 (1963)
- Always include the year or era in your search to get the correct issue

Search for SOLD prices from GPA, GoCollect, Heritage Auctions, eBay sold listings, MyComicShop, and ComicLink.

Based on ACTUAL sold prices for the {pub_date} issue, provide a valuation summary in this EXACT format:

LOW ESTIMATE: $X.XX
BEST ESTIMATE: $X.XX
HIGH ESTIMATE: $X.XX
CONFIDENCE: 0.X

Use actual dollar amounts based on real sales data you find."""

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

        # Parse prices - match actual format from Gemini response
        # Format: "**Conservative Low Estimate (worst case):** $80.00"
        low_match = re.search(r'\*?\*?\s*(?:Conservative\s+)?Low\s+Estimate[^:$]*:?\*?\*?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)', price_text, re.IGNORECASE)
        best_match = re.search(r'\*?\*?\s*Best\s+Estimate[^:$]*:?\*?\*?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)', price_text, re.IGNORECASE)
        high_match = re.search(r'\*?\*?\s*(?:Optimistic\s+)?High\s+Estimate[^:$]*:?\*?\*?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)', price_text, re.IGNORECASE)
        conf_match = re.search(r'\*?\*?\s*Confidence\s+Level\*?\*?\s*:\*?\*?\s*(0?\.\d+|1\.0)', price_text, re.IGNORECASE)

        # Fallback patterns if the specific format doesn't match
        if not low_match:
            low_match = re.search(r'(?:low|conservative|minimum)[^:$]*[:\s]*\$?\s*([\d,]+(?:\.\d{1,2})?)', price_text, re.IGNORECASE)
        if not best_match:
            best_match = re.search(r'(?:best|likely|typical|average)[^:$]*[:\s]*\$?\s*([\d,]+(?:\.\d{1,2})?)', price_text, re.IGNORECASE)
        if not high_match:
            high_match = re.search(r'(?:high|optimistic|maximum)[^:$]*[:\s]*\$?\s*([\d,]+(?:\.\d{1,2})?)', price_text, re.IGNORECASE)
        if not conf_match:
            conf_match = re.search(r'confidence[^:]*[:\s]*(0?\.\d+|1\.0)', price_text, re.IGNORECASE)

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

        # Extract grounding metadata (search queries and sources WITH URLs)
        grounding_data = {
            'search_queries': [],
            'sources': [],
            'grounding_used': False
        }

        grounding_info = []
        if hasattr(price_response, 'candidates') and price_response.candidates:
            candidate = price_response.candidates[0]
            if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                metadata = candidate.grounding_metadata
                grounding_data['grounding_used'] = True

                # Get search queries
                if hasattr(metadata, 'web_search_queries') and metadata.web_search_queries:
                    grounding_data['search_queries'] = list(metadata.web_search_queries)
                    queries = ', '.join(metadata.web_search_queries)
                    grounding_info.append(f"Searches: {queries}")

                # Get sources WITH URLs
                if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                    for chunk in metadata.grounding_chunks:
                        if hasattr(chunk, 'web'):
                            source_data = {
                                'title': chunk.web.title if hasattr(chunk.web, 'title') else 'Unknown',
                                'url': chunk.web.uri if hasattr(chunk.web, 'uri') else None
                            }
                            grounding_data['sources'].append(source_data)

                    # Create readable summary
                    source_titles = [s['title'] for s in grounding_data['sources']]
                    if source_titles:
                        grounding_info.append(f"Sources: {', '.join(source_titles[:5])}")

        # Store full grounding metadata for export
        data['grounding_metadata'] = grounding_data

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

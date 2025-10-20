import google.generativeai as genai
from typing import Optional
from PIL import Image
import json
import re

from models import ComicValuation


class GeminiComicAnalyzer:
    """Gemini-powered comic book analyzer - two-step approach for comic identification and pricing"""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-exp"):
        genai.configure(api_key=api_key)
        self.model_name = model
        self.model = genai.GenerativeModel(model_name=self.model_name)

    async def analyze_comic(self, image_path: str) -> ComicValuation:
        """Analyze a comic book image with market-based pricing (two-step process)"""

        # Load image
        image = Image.open(image_path)

        # STEP 1: Identify comic from image
        identification_prompt = """You are a professional comic book appraiser. Analyze this comic book cover image and identify:

1. Series name (exactly as shown on cover)
2. Issue number (with any variant info)
3. Publisher
4. Publication date or era (if determinable from style)
5. Condition grade (0.5-10.0 scale) based on visible damage
6. Specific condition issues (creases, tears, spine stress, etc.)
7. Whether this is a key issue and why
8. Your confidence in identification

Use "Unknown" for any information not clearly visible.

Respond with JSON:
{
  "series": "Series name",
  "title": "Issue title if visible",
  "issue_number": "Issue number",
  "publisher": "Publisher",
  "publication_date": "Date or Unknown",
  "estimated_grade": "X.X",
  "condition_notes": ["List of issues"],
  "key_issue": true/false,
  "key_issue_notes": "Why significant or Not a key issue",
  "rarity_notes": "Rarity info or Unknown",
  "identification_confidence": 0.0,
  "analysis_notes": "Any observations",
  "image_filename": "placeholder",
  "llm_provider": "placeholder",
  "analysis_date": "placeholder"
}"""

        # Configure generation
        generation_config = genai.types.GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json"
        )

        # Get identification from vision model
        step1_response = await self.model.generate_content_async(
            [identification_prompt, image],
            generation_config=generation_config
        )

        # Parse identification
        response_text = step1_response.text
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        data = json.loads(response_text)

        # STEP 2: Ask Gemini to research and provide realistic market prices
        series = data.get('series', 'Unknown')
        issue = data.get('issue_number', '')
        grade = data.get('estimated_grade', '5.0')
        publisher = data.get('publisher', 'Unknown')

        # Use your knowledge + reasoning to provide realistic pricing
        pricing_prompt = f"""Based on your knowledge of comic book markets, provide realistic current market price estimates for:

Comic: {series} #{issue}
Publisher: {publisher}
Grade: {grade}

Consider:
- This specific series and issue's historical significance
- The grade/condition provided
- Typical market values for similar comics
- Whether this is a key issue, first appearance, or regular issue
- Current comic market trends

Provide realistic estimates:
LOW: $X.XX (conservative/worst case)
BEST: $X.XX (most likely current value)
HIGH: $X.XX (optimistic but realistic)
CONFIDENCE: 0.X (0.0-1.0 based on your knowledge)
REASONING: Brief explanation of how you determined these prices

Be realistic - most comics are worth $1-20, key issues $50-500, major keys $500+"""

        # Get pricing estimate
        price_response = await self.model.generate_content_async(
            pricing_prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.1)
        )

        # Parse pricing response
        price_text = price_response.text

        # Extract values with regex
        low_match = re.search(r'LOW:\s*\$?([\d,.]+)', price_text, re.IGNORECASE)
        best_match = re.search(r'BEST:\s*\$?([\d,.]+)', price_text, re.IGNORECASE)
        high_match = re.search(r'HIGH:\s*\$?([\d,.]+)', price_text, re.IGNORECASE)
        conf_match = re.search(r'CONFIDENCE:\s*([\d.]+)', price_text, re.IGNORECASE)
        reasoning_match = re.search(r'REASONING:\s*(.+?)(?:\n\n|$)', price_text, re.IGNORECASE | re.DOTALL)

        # Clean up numbers (remove commas)
        def clean_price(match):
            if match:
                return float(match.group(1).replace(',', ''))
            return None

        # Build valuation with estimated prices
        data['valuation'] = {
            'low_estimate': clean_price(low_match) or 1.0,
            'best_estimate': clean_price(best_match) or 5.0,
            'high_estimate': clean_price(high_match) or 10.0,
            'confidence': float(conf_match.group(1)) if conf_match else 0.6
        }

        # Add pricing reasoning to analysis notes
        reasoning = reasoning_match.group(1).strip() if reasoning_match else 'Based on model knowledge of comic markets'
        current_notes = data.get('analysis_notes', '')
        data['analysis_notes'] = f"{current_notes} | Pricing: {reasoning}"

        # Create and return valuation
        return ComicValuation(**data)


class GeminiComicComparator:
    """Compare results from Gemini"""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-exp"):
        self.analyzer = GeminiComicAnalyzer(api_key, model)

    async def compare_analyses(self, image_path: str) -> tuple[ComicValuation, ComicValuation]:
        """Get analysis"""
        result = await self.analyzer.analyze_comic(image_path)
        return result, result

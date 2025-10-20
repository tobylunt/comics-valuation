import base64
import openai
from typing import Optional
from pydantic import BaseModel

from models import ComicValuation, ConditionGrade, ValuationEstimate


class OpenAIComicAnalyzer:
    """OpenAI-powered comic book analyzer using structured outputs"""

    def __init__(self, api_key: str, model: str = "gpt-5-mini"):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model

    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    async def analyze_comic(self, image_path: str) -> ComicValuation:
        """Analyze a comic book image and return structured valuation data"""
        base64_image = self._encode_image(image_path)

        # Use OpenAI's structured outputs with our Pydantic model
        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": """You are a professional comic book appraiser with decades of experience.
                    Analyze comic book cover images and provide detailed, accurate assessments.

                    CRITICAL GUIDELINES:
                    - Base assessments ONLY on what's visible in the image
                    - If details aren't clear, use "Unable to determine" or appropriate defaults
                    - Don't guess at information not clearly visible
                    - Use conservative, realistic market valuations
                    - Grade condition based on visible damage only"""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Please analyze this comic book cover image and provide:

1. **Identification**: Series name, issue number, publisher (exactly as visible)
2. **Condition Assessment**: Grade using standard 10.0-1.0 scale based on visible damage
3. **Market Analysis**: Realistic price estimates (low/best/high) with confidence level
4. **Significance**: Whether it's a key issue and why

Focus on accuracy over completeness. If something isn't clearly visible, indicate uncertainty."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "comic_valuation",
                    "strict": True,
                    "schema": ComicValuation.model_json_schema()
                }
            },
            max_completion_tokens=2000
        )

        # Parse the structured response
        message = completion.choices[0].message

        # Try to get parsed content (newer versions) or content (older versions)
        if hasattr(message, 'parsed') and message.parsed:
            response_data = message.parsed
            if not isinstance(response_data, ComicValuation):
                response_data = ComicValuation(**response_data)
        else:
            # Fallback to parsing JSON from content
            import json
            content = message.content
            if content:
                response_dict = json.loads(content)
                response_data = ComicValuation(**response_dict)
            else:
                raise ValueError("No response content received")

        return response_data


# For comparison purposes, we can easily add a second model
class OpenAIComicComparator:
    """Compare results from multiple OpenAI models"""

    def __init__(self, api_key: str, primary_model: str = "gpt-4o", secondary_model: str = "gpt-4o-mini"):
        self.primary = OpenAIComicAnalyzer(api_key, primary_model)
        self.secondary = OpenAIComicAnalyzer(api_key, secondary_model)

    async def compare_analyses(self, image_path: str) -> tuple[ComicValuation, ComicValuation]:
        """Get analyses from both models for comparison"""
        import asyncio

        primary_result, secondary_result = await asyncio.gather(
            self.primary.analyze_comic(image_path),
            self.secondary.analyze_comic(image_path)
        )

        return primary_result, secondary_result

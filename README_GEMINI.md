# Comic Book Valuation System - Gemini Branch

AI-powered comic book valuation using **Google Gemini 2.0 Flash with Search Grounding** for accurate, real-world pricing data.

## Key Features of This Branch

🔍 **Google Search Grounding** - Gemini searches the web in real-time for actual comic book prices from:
- GPA (GoCollect Price Guide)
- Heritage Auctions sold listings
- eBay sold prices
- MyComicShop
- Other reputable comic pricing sources

💰 **Real Market Data** - Unlike GPT models that estimate prices, Gemini looks up actual sold prices and current market values

📊 **Transparent Sources** - Analysis notes include which sources were used for pricing

## Quick Start

### 1. Get a Gemini API Key

Get your free Gemini API key from: https://aistudio.google.com/app/apikey

### 2. Set Up API Key

Create a `.env` file:
```bash
echo "GEMINI_API_KEY=your-gemini-api-key-here" > .env
```

Or set environment variable:
```bash
export GEMINI_API_KEY="your-key-here"
```

### 3. Create Configuration

```bash
python cli.py init
```

Edit `config.json` to add your Gemini API key:
```json
{
  "images_directory": "./images",
  "output_directory": "./results",
  "provider": "gemini",
  "gemini_api_key": "your-gemini-api-key-here",
  "primary_model": "gemini-2.0-flash-exp",
  "max_concurrent": 5,
  "retry_attempts": 3,
  "save_json": true,
  "save_csv": true
}
```

### 4. Test Single Image

```bash
python cli.py analyze-single ~/path/to/comic-image.jpg
```

### 5. Process All Images

```bash
# Dry run first
python cli.py process --dry-run

# Run the full batch
python cli.py process
```

## How It Works

1. **Image Analysis** - Gemini identifies the comic from the cover image
2. **Search Grounding** - Gemini automatically searches Google for recent sales data
3. **Price Synthesis** - Combines multiple sources to provide low/best/high estimates
4. **Confidence Scoring** - Indicates reliability based on available market data

## Cost Estimation

Gemini 2.0 Flash pricing (approximate):
- **Input**: ~$0.0001 per 1K tokens
- **Output**: ~$0.0004 per 1K tokens
- **Search queries**: Included in regular pricing

Estimated cost per comic: **~$0.03-0.05**

For 325 images: **~$10-15** (significantly cheaper than GPT-5-mini)

## Comparison with Main Branch

| Feature | Main Branch (GPT-5-mini) | Gemini Branch |
|---------|-------------------------|---------------|
| Price Source | AI estimation | Real market data via Google Search |
| Accuracy | Moderate | High (based on actual sales) |
| Cost per image | ~$0.08 | ~$0.03-0.05 |
| Speed | ~30 sec/image | ~30-40 sec/image |
| API | OpenAI | Google Gemini |

## Output Format

Same as main branch - results saved as:
- `results/comic_valuations_TIMESTAMP.json`
- `results/comic_valuations_TIMESTAMP.csv`
- `results/intermediate/IMG_XXXX.json` (auto-saved during processing)

## Switching Between Providers

You can switch providers by editing `config.json`:

**For Gemini:**
```json
{
  "provider": "gemini",
  "gemini_api_key": "your-key",
  "primary_model": "gemini-2.0-flash-exp"
}
```

**For OpenAI:**
```json
{
  "provider": "openai",
  "openai_api_key": "your-key",
  "primary_model": "gpt-5-mini"
}
```

## Environment Variables

```bash
export GEMINI_API_KEY="your-key-here"
export COMICS_IMAGES_DIR="./images"
export COMICS_OUTPUT_DIR="./results"
export COMICS_PROVIDER="gemini"
export COMICS_MODEL="gemini-2.0-flash-exp"
```

## Troubleshooting

**API Key Error**: Make sure your Gemini API key is valid and has access to Gemini 2.0 Flash

**Search Grounding Not Working**: Ensure you're using `gemini-2.0-flash-exp` or newer model that supports grounding

**Rate Limiting**: Reduce `max_concurrent` if you hit rate limits

## Why Use This Branch?

✅ More accurate pricing based on actual market data
✅ Lower cost (~40% cheaper than GPT-5-mini)
✅ Transparent - shows which sources were used
✅ Better for rare/valuable comics where accurate pricing matters

Use the main branch (GPT) if:
- You prefer OpenAI's ecosystem
- You want slightly faster processing
- Search grounding is not critical for your use case

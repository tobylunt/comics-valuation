# Comic Book Valuation System

AI-powered comic book valuation using OpenAI's latest vision models with structured outputs for maximum reliability.

## Features

- **Reliable Analysis**: Uses OpenAI's structured outputs to guarantee valid JSON responses
- **Professional Prompting**: Anti-hallucination techniques for accurate valuations
- **Batch Processing**: Process 200-300 images efficiently with concurrency control
- **Model Comparison**: Compare results from different OpenAI models (e.g., gpt-4o vs gpt-4o-mini)
- **Structured Data**: Consistent schema for series, issue, grade, condition, and valuation
- **Cost Estimation**: Preview processing costs before running
- **Rich CLI**: Beautiful command-line interface with progress tracking

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up API Key

Create a `.env` file with your OpenAI API key:

```bash
echo "OPENAI_API_KEY=your-actual-api-key-here" > .env
```

### 3. Create Configuration

```bash
python cli.py init
```

This creates `config.json`. Edit the file to add your OpenAI API key and set your comics directory path.

### 4. Test Single Image

```bash
python cli.py analyze-single ~/Desktop/comics/IMG_4089.jpeg
```

### 5. Process All Images

```bash
# Dry run first to see what will be processed
python cli.py process --dry-run

# Run the full batch
python cli.py process
```

## Usage Examples

### Environment Variables

Instead of config file, you can use environment variables:

```bash
export OPENAI_API_KEY="your-key-here"
export COMICS_IMAGES_DIR="./images"
export COMICS_OUTPUT_DIR="./results"
export OPENAI_MODEL="gpt-4o"

python cli.py process
```

### Single Image Analysis

```bash
# Basic analysis
python cli.py analyze-single comic1.jpg

# Compare two models
python cli.py analyze-single comic1.jpg --compare

# Override model
python cli.py analyze-single comic1.jpg --model gpt-5
```

### Batch Processing

```bash
# Process all images with default settings
python cli.py process

# Override directories
python cli.py process --images-dir ./my-comics --output-dir ./my-results

# Use different model
python cli.py process --model gpt-5

# Preview what would be processed
python cli.py process --dry-run
```

## Output Format

Results are saved as structured JSON with this schema:

```json
{
  "series": "Amazing Spider-Man",
  "title": "The Night Gwen Stacy Died", 
  "issue_number": "121",
  "publisher": "Marvel Comics",
  "publication_date": "1973-06",
  "estimated_grade": "7.5",
  "condition_notes": ["Minor spine stress", "Small corner crease"],
  "key_issue": true,
  "key_issue_notes": "Death of Gwen Stacy",
  "valuation": {
    "low_estimate": 450.00,
    "best_estimate": 650.00, 
    "high_estimate": 850.00,
    "confidence": 0.8
  },
  "identification_confidence": 0.95
}
```

## Cost Estimation

Rough estimates per image:
- **gpt-5**: ~$0.20
- **gpt-5-mini**: ~$0.08
- **gpt-4o**: ~$0.15
- **gpt-4o-mini**: ~$0.05

For 300 images with gpt-5-mini: ~$24

## Configuration Options

```json
{
  "images_directory": "./images",           // Where your comic images are
  "output_directory": "./results",          // Where to save results
  "openai_api_key": "sk-...",              // Your OpenAI API key
  "primary_model": "gpt-5-mini",           // Main model to use
  "comparison_model": "gpt-5",             // Optional second model
  "image_extensions": [".jpg", ".png", ".gif", ".bmp", ".webp"],  // Supported file types
  "max_concurrent": 5,                     // Concurrent API requests
  "retry_attempts": 3,                     // Retries on failure
  "retry_delay": 1.0,                      // Delay between retries
  "save_json": true,                       // Save detailed JSON
  "save_csv": true                         // Save CSV summary (coming soon)
}
```

## Supported Models

- `gpt-5-mini` (default) - Latest mini model, good balance of speed and accuracy
- `gpt-5` - Latest full model, best accuracy
- `gpt-4o` - Previous generation, reliable
- `gpt-4o-mini` - Previous generation mini
- `gpt-4-turbo` - Legacy model

## Future Features

- [ ] CSV export for spreadsheet analysis
- [ ] Google Sheets integration via API
- [ ] Collection summary reports
- [ ] Market trend analysis
- [ ] Condition assessment improvements
- [ ] Bulk image preprocessing

## Troubleshooting

### Common Issues

1. **API Key Error**: Make sure your OpenAI API key is valid and has credits
2. **No Images Found**: Check that your images directory path is correct
3. **Rate Limiting**: Reduce `max_concurrent` if you hit rate limits
4. **JSON Parsing**: Should be rare with structured outputs, but check model compatibility

### Getting Help

The system logs detailed information. Check the console output for specific error messages and retry information.
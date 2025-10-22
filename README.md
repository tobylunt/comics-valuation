# Comic Book Valuation System

AI-powered comic book valuation system using state-of-the-art vision models to analyze, grade, and estimate values for comic book collections. Features resumable processing, batch operations, and support for both OpenAI and Google Gemini models.

## ✨ Key Features

- **🤖 Multi-Provider Support**: Works with OpenAI GPT-4o/GPT-4o-mini and Google Gemini models
- **📊 Structured Output**: Guaranteed valid JSON responses with comprehensive comic metadata
- **🔄 Resumable Processing**: Interrupt and resume batch processing without losing progress
- **⚡ Efficient Batch Processing**: Handle hundreds of images with configurable concurrency
- **💾 Smart Caching**: Automatically skips already-processed images
- **🔍 Google Search Grounding**: Gemini models can search for real-time pricing data
- **📈 Model Comparison**: Compare valuations between different AI models
- **💰 Cost Estimation**: Preview processing costs before running
- **🎨 Rich CLI**: Beautiful command-line interface with progress tracking
- **📝 Multiple Output Formats**: JSON and CSV exports with detailed metadata

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- OpenAI API key and/or Google Gemini API key
- Comic book images (JPEG, PNG, WEBP supported)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/comics-valuation.git
cd comics-valuation

# Install dependencies
pip install -r requirements.txt
```

### Initial Setup

```bash
# 1. Create configuration file
python cli.py init

# 2. Edit config.json with your settings:
#    - Add your API key(s)
#    - Set your images directory path
#    - Choose your AI provider and model

# 3. Test with a single image
python cli.py analyze-single path/to/comic.jpg

# 4. Process entire collection
python cli.py process
```

## 📖 Configuration

The system uses two configuration components:
- **`config.json`** - Your configuration file with API keys and settings
- **`config.py`** - Python module that loads, validates, and manages configuration

Create or edit `config.json`:

```json
{
  "provider": "gemini",              // "openai" or "gemini"
  "images_directory": "./images",    // Path to comic images
  "output_directory": "./results",   // Where to save results
  
  // OpenAI Configuration
  "openai_api_key": "sk-...",       
  "primary_model": "gpt-4o-mini",   // or "gpt-4o"
  
  // Gemini Configuration  
  "gemini_api_key": "...",
  "gemini_model": "gemini-2.5-flash",
  "enable_grounding": true,          // Enable Google search
  
  // Processing Settings
  "max_concurrent": 5,              // Parallel requests
  "retry_attempts": 3,               // Retries per image
  "retry_delay": 2.0,               // Seconds between retries
  
  // Output Settings
  "save_json": true,
  "save_csv": true,
  "save_intermediate": true          // Enable resumable processing
}
```

You can also use environment variables instead of or to override `config.json`:
```bash
export OPENAI_API_KEY="sk-..."
export GEMINI_API_KEY="..."
export COMICS_IMAGES_DIR="./my-comics"
export COMICS_OUTPUT_DIR="./my-results"
export COMICS_PROVIDER="gemini"
export COMICS_MODEL="gemini-2.0-flash-exp"
```

The `config.py` module handles loading from both sources, with environment variables taking precedence.

## 🎮 CLI Commands

### Basic Commands

```bash
# Initialize configuration
python cli.py init

# Process all images
python cli.py process [--dry-run]

# Analyze single image
python cli.py analyze-single <image_path> [--compare]

# Compare models on single image
python cli.py analyze-single comic.jpg --compare
```

### Resumable Processing Commands

```bash
# Check processing status
python cli.py status [--detailed]

# Resume interrupted processing
python cli.py resume

# Validate intermediate results
python cli.py validate

# Clean up failed/corrupted results
python cli.py clean [--failed] [--corrupted] [--dry-run]
```

## 🔄 Resumable Processing

The system saves progress after each image, allowing you to:

- **Interrupt safely** with Ctrl+C without losing work
- **Resume automatically** from where you left off
- **Skip completed images** on subsequent runs
- **Retry failed images** with transient errors
- **Clean corrupted results** before resuming

### How It Works

1. Each processed image gets saved to `results/intermediate/`
2. On resume, the system checks existing results
3. Successfully processed images are skipped
4. Failed images with retryable errors are reprocessed
5. Final results are compiled when processing completes

### Error Handling

**Retryable Errors** (automatically retried):
- Network timeouts
- Rate limiting
- Temporary API errors
- JSON parsing errors

**Permanent Errors** (skipped on resume):
- Invalid API responses
- Validation errors
- Authentication failures

## 📊 Output Format

### JSON Structure
```json
{
  "series": "The Amazing Spider-Man",
  "title": "The Final Chapter",
  "issue_number": "441",
  "publisher": "Marvel Comics",
  "publication_date": "1998-11",
  "estimated_grade": "8.0",
  "condition_notes": ["Minor spine stress", "Light corner wear"],
  "key_issue": true,
  "key_issue_notes": "Final issue before relaunch",
  "rarity_notes": "Common print run",
  "valuation": {
    "low_estimate": 15.00,
    "best_estimate": 25.00,
    "high_estimate": 40.00,
    "confidence": 0.75
  },
  "identification_confidence": 0.95,
  "grounding_metadata": {
    "grounding_used": true,
    "search_queries": ["Amazing Spider-Man 441 value"],
    "sources": [...]
  }
}
```

### CSV Columns
- Basic Info: Series, Title, Issue Number, Publisher, Publication Date
- Grading: Estimated Grade, Condition Notes
- Valuation: Low/Best/High Estimates, Confidence
- Metadata: Key Issue Status, Rarity Notes, Analysis Notes
- Processing: LLM Provider, Processing Time, Grounding Used

## 🏗️ Project Structure

```
comics-valuation/
├── cli.py                 # Main CLI interface
├── pipeline.py            # Core processing pipeline
├── models.py              # Data models and schemas
├── openai_provider.py     # OpenAI integration
├── gemini_provider.py     # Google Gemini integration
├── config.py              # Configuration loader/validator
├── requirements.txt       # Python dependencies
├── config.json            # Your configuration file (created by setup)
├── setup.py               # Interactive setup script
├── tests.py               # Unit tests
└── results/
    ├── intermediate/      # Individual image results
    ├── comic_valuations_*.json/csv  # Final outputs
    ├── results_summary.html          # Generated HTML report (moved from repo root)
    └── results_summary.ipynb         # Notebook copy (moved from repo root)
```

## 🔍 Examples

### Basic Processing
```bash
# Process with specific model
python cli.py process --model gpt-4o-mini

# Process specific directory
python cli.py process --images-dir ~/Desktop/comics

# Dry run to preview
python cli.py process --dry-run
```

### Status Management
```bash
# Check current progress
python cli.py status --detailed

# Clean and retry failures
python cli.py clean --failed
python cli.py resume
```

### Advanced Usage
```python
# Programmatic usage
from pipeline import ComicValuationPipeline
from config import load_config

config = load_config("config.json")
pipeline = ComicValuationPipeline(config)

# Process with resume support
results = await pipeline.process_all_images()

# Get status
status = pipeline.get_intermediate_status()
print(f"Processed: {status['successful']}/{status['total']}")
```

## 🐛 Troubleshooting

### Common Issues

**Processing seems stuck**
```bash
python cli.py status        # Check current state
python cli.py clean --corrupted
python cli.py resume
```

**Validation errors from LLM**
- The AI sometimes returns invalid data formats
- These are marked as permanent failures
- Review prompts or switch models if persistent

**Rate limiting**
- Reduce `max_concurrent` in config.json
- Increase `retry_delay` for better spacing

**Memory issues with large batches**
- Process in smaller chunks
- Use `--images-dir` to process subdirectories

## 📈 Performance Tips

1. **Optimal Settings**:
   - `max_concurrent`: 3-5 for most APIs
   - `retry_attempts`: 3 with exponential backoff
   - Gemini models are generally faster and cheaper

2. **Cost Management**:
   - GPT-4o-mini: ~$0.05-0.08 per image
   - Gemini Flash: ~$0.01-0.02 per image
   - Use `--dry-run` to preview costs

3. **Batch Processing**:
   - Process 50-100 images at a time for large collections
   - Monitor with `status` command between batches
   - Use intermediate saves for safety

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- OpenAI for GPT-4 Vision API
- Google for Gemini Vision API
- The comic collecting community for domain expertise

---

**Note**: This tool provides estimates based on AI analysis. Always consult professional grading services and current market data for accurate valuations.
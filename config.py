import os
import json
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()


class Config(BaseModel):
    """Configuration for comic valuation with support for OpenAI and Gemini"""

    # Core settings
    images_directory: str = Field(..., description="Directory containing comic book images")
    output_directory: str = Field(default="./results", description="Directory for output files")

    # LLM Provider settings
    provider: str = Field(default="gemini", description="LLM provider: 'openai' or 'gemini'")

    # API Keys (at least one required based on provider)
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    gemini_api_key: Optional[str] = Field(default=None, description="Google Gemini API key")

    # Model selection
    primary_model: str = Field(default="gemini-2.5-flash", description="Primary model to use")
    comparison_model: Optional[str] = Field(default=None, description="Optional second model for comparison")

    # Processing settings
    image_extensions: list[str] = Field(default=[".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"])
    max_concurrent: int = Field(default=5, ge=1, le=10, description="Max concurrent requests")
    retry_attempts: int = Field(default=3, ge=1, le=5)
    retry_delay: float = Field(default=1.0, ge=0.1, le=10.0)

    # Output settings
    save_json: bool = Field(default=True)
    save_csv: bool = Field(default=True)
    include_timestamp: bool = Field(default=True)


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration with environment variable fallbacks"""

    config_data = {}

    # Try to load from config file
    if config_path and Path(config_path).exists():
        with open(config_path, 'r') as f:
            config_data = json.load(f)
    elif Path("config.json").exists():
        with open("config.json", 'r') as f:
            config_data = json.load(f)

    # Override with environment variables
    env_config = {
        "images_directory": os.getenv("COMICS_IMAGES_DIR", config_data.get("images_directory", "./images")),
        "output_directory": os.getenv("COMICS_OUTPUT_DIR", config_data.get("output_directory", "./results")),
        "provider": os.getenv("COMICS_PROVIDER", config_data.get("provider", "gemini")),
        "openai_api_key": os.getenv("OPENAI_API_KEY", config_data.get("openai_api_key")),
        "gemini_api_key": os.getenv("GEMINI_API_KEY", config_data.get("gemini_api_key")),
        "primary_model": os.getenv("COMICS_MODEL", config_data.get("primary_model", "gemini-2.0-flash-exp")),
        "comparison_model": os.getenv("COMICS_COMPARISON_MODEL", config_data.get("comparison_model")),
    }

    # Merge configurations (env vars take precedence)
    final_config = {**config_data, **{k: v for k, v in env_config.items() if v is not None}}

    # Validate that appropriate API key is provided based on provider
    provider = final_config.get("provider", "gemini")

    if provider == "openai":
        if not final_config.get("openai_api_key"):
            raise ValueError("OpenAI API key must be provided via config file or OPENAI_API_KEY environment variable")
        api_key = final_config.get("openai_api_key", "")
        if not api_key.startswith("sk-") or len(api_key) < 20:
            raise ValueError("Invalid OpenAI API key format. API keys should start with 'sk-' and be at least 20 characters long.")

    elif provider == "gemini":
        if not final_config.get("gemini_api_key"):
            raise ValueError("Gemini API key must be provided via config file or GEMINI_API_KEY environment variable")
        api_key = final_config.get("gemini_api_key", "")
        if len(api_key) < 20:
            raise ValueError("Invalid Gemini API key format. API keys should be at least 20 characters long.")

    else:
        raise ValueError(f"Unknown provider: {provider}. Must be 'openai' or 'gemini'.")

    return Config(**final_config)


def create_example_config(path: str = "config.json") -> None:
    """Create an example configuration file"""
    example_config = {
        "images_directory": "./images",
        "output_directory": "./results",
        "provider": "gemini",
        "gemini_api_key": "your-gemini-api-key-here",
        "openai_api_key": None,
        "primary_model": "gemini-2.0-flash-exp",
        "comparison_model": None,
        "max_concurrent": 5,
        "retry_attempts": 3,
        "save_json": True,
        "save_csv": True
    }

    with open(path, 'w') as f:
        json.dump(example_config, f, indent=2)

    print(f"Example configuration created at: {path}")
    print("Edit this file with your OpenAI API key and image directory path.")

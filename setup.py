#!/usr/bin/env python3
"""
Setup script for Comic Book Valuation System.
Helps new users get started quickly with interactive configuration.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Optional
from config import Config, create_example_config

def check_python_version():
    """Check if Python version is 3.8 or higher."""
    if sys.version_info < (3, 8):
        print("❌ Error: Python 3.8 or higher is required.")
        print(f"   You have: Python {sys.version}")
        sys.exit(1)
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} detected")

def install_requirements():
    """Install required packages."""
    print("\n📦 Installing required packages...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ All packages installed successfully")
    except subprocess.CalledProcessError:
        print("❌ Failed to install packages. Please run manually:")
        print("   pip install -r requirements.txt")
        sys.exit(1)

def get_api_key(provider: str) -> Optional[str]:
    """Prompt for API key with validation."""
    providers = {
        "openai": {
            "name": "OpenAI",
            "prefix": "sk-",
            "length": 40,
            "url": "https://platform.openai.com/api-keys"
        },
        "gemini": {
            "name": "Google Gemini",
            "prefix": None,
            "length": 39,
            "url": "https://makersuite.google.com/app/apikey"
        }
    }

    info = providers[provider]
    print(f"\n🔑 {info['name']} API Key")
    print(f"   Get your key at: {info['url']}")

    while True:
        api_key = input(f"   Enter your {info['name']} API key (or press Enter to skip): ").strip()

        if not api_key:
            return None

        # Basic validation
        if info['prefix'] and not api_key.startswith(info['prefix']):
            print(f"   ⚠️  {info['name']} keys usually start with '{info['prefix']}'")

        if len(api_key) < info['length'] - 5:
            print(f"   ⚠️  Key seems too short (expected ~{info['length']} characters)")

        confirm = input("   Use this key? (y/n): ").lower()
        if confirm == 'y':
            return api_key

def create_config():
    """Create configuration file interactively."""
    print("\n⚙️  Configuration Setup")
    print("-" * 40)

    config = {}

    # Provider selection
    print("\n📡 Select AI Provider:")
    print("   1. Google Gemini (recommended - faster & cheaper)")
    print("   2. OpenAI GPT-4")
    print("   3. Both (compare results)")

    choice = input("   Choice (1-3): ").strip()

    if choice == "1":
        config["provider"] = "gemini"
        config["gemini_api_key"] = get_api_key("gemini") or "YOUR-GEMINI-API-KEY"
        config["gemini_model"] = "gemini-2.0-flash-exp"
        config["enable_grounding"] = True
        config["primary_model"] = "gemini-2.0-flash-exp"

    elif choice == "2":
        config["provider"] = "openai"
        config["openai_api_key"] = get_api_key("openai") or "YOUR-OPENAI-API-KEY"
        config["primary_model"] = "gpt-4o-mini"

    else:
        config["provider"] = "gemini"  # Default to Gemini
        config["gemini_api_key"] = get_api_key("gemini") or "YOUR-GEMINI-API-KEY"
        config["openai_api_key"] = get_api_key("openai") or "YOUR-OPENAI-API-KEY"
        config["gemini_model"] = "gemini-2.0-flash-exp"
        config["enable_grounding"] = True
        config["primary_model"] = "gemini-2.0-flash-exp"
        config["comparison_model"] = "gpt-4o-mini"

    # Directory setup
    print("\n📁 Directory Configuration:")

    default_images = "./images"
    images_dir = input(f"   Images directory [{default_images}]: ").strip() or default_images
    config["images_directory"] = images_dir

    default_output = "./results"
    output_dir = input(f"   Output directory [{default_output}]: ").strip() or default_output
    config["output_directory"] = output_dir

    # Processing settings
    print("\n⚡ Processing Settings:")

    try:
        max_concurrent = int(input("   Max concurrent requests [5]: ").strip() or "5")
    except ValueError:
        max_concurrent = 5
    config["max_concurrent"] = max_concurrent

    # Complete configuration
    config.update({
        "image_extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"],
        "retry_attempts": 3,
        "retry_delay": 2.0,
        "save_json": True,
        "save_csv": True,
        "save_intermediate": True,
        "grounding_threshold": 0.7
    })

    # Save configuration
    config_path = Path("config.json")
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"\n✅ Configuration saved to {config_path}")

    # Validate configuration using Pydantic
    try:
        Config(**config)
        print("✅ Configuration validated successfully")
    except Exception as e:
        print(f"⚠️  Configuration validation warning: {e}")

    # Create directories
    for dir_path in [images_dir, output_dir]:
        Path(dir_path).mkdir(exist_ok=True, parents=True)
    print(f"✅ Created directories: {images_dir}, {output_dir}")

    return config

def test_setup(config):
    """Test the setup with a simple import check."""
    print("\n🧪 Testing setup...")

    try:
        # Try importing main modules
        import models
        import pipeline
        import cli
        from config import load_config

        # Test loading the config
        try:
            loaded_config = load_config("config.json")
            print("✅ All modules import successfully")
            print("✅ Configuration loads successfully")
        except Exception as e:
            print(f"⚠️  Configuration loading issue: {e}")

        # Check if API key is configured
        provider = config.get("provider", "gemini")
        if provider == "gemini":
            if config.get("gemini_api_key", "").startswith("YOUR-"):
                print("⚠️  Remember to add your Gemini API key to config.json")
        else:
            if config.get("openai_api_key", "").startswith("YOUR-"):
                print("⚠️  Remember to add your OpenAI API key to config.json")

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

    return True

def main():
    """Main setup process."""
    print("=" * 60)
    print("  Comic Book Valuation System - Setup")
    print("=" * 60)

    # Check Python version
    check_python_version()

    # Check if config already exists
    config_path = Path("config.json")
    if config_path.exists():
        print("\n⚠️  config.json already exists.")
        print("   Options:")
        print("   1. Keep existing configuration")
        print("   2. Create new configuration")
        print("   3. Create example configuration (config.example.json)")

        choice = input("   Choice (1-3): ").strip()

        if choice == "1":
            print("   Using existing configuration.")
            with open(config_path) as f:
                config = json.load(f)
        elif choice == "3":
            create_example_config("config.example.json")
            print("   Example configuration created at config.example.json")
            print("   Copy it to config.json and edit with your settings.")
            return
        else:
            config = create_config()
    else:
        # Install requirements
        install_requirements()

        # Create configuration
        config = create_config()

    # Test setup
    if test_setup(config):
        print("\n" + "=" * 60)
        print("🎉 Setup Complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Add comic images to your images directory")
        print("2. Test with a single image:")
        print("   python cli.py analyze-single <image_path>")
        print("3. Process your collection:")
        print("   python cli.py process")
        print("\nFor help, see README.md or run:")
        print("   python cli.py --help")
    else:
        print("\n❌ Setup incomplete. Please check errors above.")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Setup cancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

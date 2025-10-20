import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import Config, load_config, create_example_config
from pipeline import ComicValuationPipeline

app = typer.Typer(help="Comic Book Valuation System")
console = Console()


@app.command()
def init(
    output_path: str = typer.Option("config.json", help="Path for the config file")
):
    """Create an example configuration file"""
    try:
        create_example_config(output_path)
        console.print(f"✓ Configuration template created at: {output_path}", style="green")
        console.print("Edit the file with your OpenAI API key and image directory path.")
    except Exception as e:
        console.print(f"✗ Error creating config: {e}", style="red")
        raise typer.Exit(1)


@app.command()
def process(
    config_path: Optional[str] = typer.Option(None, help="Path to config file"),
    images_dir: Optional[str] = typer.Option(None, help="Override images directory"),
    output_dir: Optional[str] = typer.Option(None, help="Override output directory"),
    model: Optional[str] = typer.Option(None, help="Override OpenAI model"),
    dry_run: bool = typer.Option(False, help="Show what would be processed without running")
):
    """Process all comic book images in the configured directory"""
    try:
        # Load configuration
        config = load_config(config_path)

        # Apply CLI overrides
        if images_dir:
            config.images_directory = images_dir
        if output_dir:
            config.output_directory = output_dir
        if model:
            config.primary_model = model

        console.print("🚀 Starting Comic Book Valuation System", style="bold blue")
        console.print(f"📁 Images directory: {config.images_directory}")
        console.print(f"📤 Output directory: {config.output_directory}")
        console.print(f"🤖 Model: {config.primary_model}")

        if dry_run:
            pipeline = ComicValuationPipeline(config)
            image_files = pipeline.get_image_files()
            console.print(f"\n📸 Found {len(image_files)} images to process:")
            for img in image_files[:10]:  # Show first 10
                console.print(f"  • {img.name}")
            if len(image_files) > 10:
                console.print(f"  ... and {len(image_files) - 10} more")
            console.print(f"\n💰 Estimated cost: ~${estimate_cost(len(image_files), config.primary_model):.2f}")
            return

        # Run the processing pipeline
        results = asyncio.run(process_all(config))

        console.print("\n📊 Processing Summary:", style="bold")
        console.print(f"✓ Successful: {results.successful}")
        console.print(f"✗ Failed: {results.failed}")
        console.print(f"⏱ Total time: {results.total_processing_time:.1f}s")

        if results.failed > 0:
            console.print("\n❌ Failed images:", style="red")
            for result in results.results:
                if not result.success:
                    console.print(f"  • {result.image_filename}: {result.error_message}")

        # Show some sample results
        successful_results = [r for r in results.results if r.success]
        if successful_results:
            console.print(f"\n💎 Sample valuations:")
            for result in successful_results[:3]:
                if result.valuation:
                    val = result.valuation
                    console.print(f"  • {result.image_filename}")
                    console.print(f"    {val.series} #{val.issue_number} - Grade: {val.estimated_grade}")
                    console.print(f"    Value: ${val.valuation.low_estimate:.2f} - ${val.valuation.high_estimate:.2f}")

    except Exception as e:
        console.print(f"✗ Error: {e}", style="red")
        raise typer.Exit(1)


@app.command()
def analyze_single(
    image_path: str = typer.Argument(..., help="Path to comic book image"),
    config_path: Optional[str] = typer.Option(None, help="Path to config file"),
    model: Optional[str] = typer.Option(None, help="Override OpenAI model"),
    compare: bool = typer.Option(False, help="Compare with secondary model if configured")
):
    """Analyze a single comic book image"""
    try:
        config = load_config(config_path)
        if model:
            config.primary_model = model

        image_file = Path(image_path)
        if not image_file.exists():
            console.print(f"✗ Image not found: {image_path}", style="red")
            raise typer.Exit(1)

        console.print(f"🔍 Analyzing {image_file.name}...", style="blue")

        if compare and config.comparison_model:
            results = asyncio.run(compare_single(config, image_path))
            primary, secondary = results

            console.print("\n📊 Comparison Results:", style="bold")
            console.print(f"\n🥇 {config.primary_model}:")
            display_valuation(primary)
            console.print(f"\n🥈 {config.comparison_model}:")
            display_valuation(secondary)

        else:
            result = asyncio.run(analyze_single_image(config, image_path))
            if result.success:
                console.print("\n📊 Analysis Results:", style="bold green")
                display_valuation(result.valuation)
            else:
                console.print(f"✗ Analysis failed: {result.error_message}", style="red")

    except Exception as e:
        console.print(f"✗ Error: {e}", style="red")
        raise typer.Exit(1)


def display_valuation(valuation: Optional[object]) -> None:
    """Display a valuation in a nice format"""
    if not valuation:
        console.print("No valuation data available")
        return

    console.print(f"  📖 Series: {valuation.series}")
    console.print(f"  🔢 Issue: #{valuation.issue_number}")
    console.print(f"  🏢 Publisher: {valuation.publisher}")
    console.print(f"  📅 Date: {valuation.publication_date or 'Unknown'}")
    console.print(f"  ⭐ Grade: {valuation.estimated_grade}")
    console.print(f"  🔑 Key Issue: {'Yes' if valuation.key_issue else 'No'}")

    val = valuation.valuation
    console.print(f"  💰 Valuation:")
    console.print(f"    Low:  ${val.low_estimate:.2f}")
    console.print(f"    Best: ${val.best_estimate:.2f}")
    console.print(f"    High: ${val.high_estimate:.2f}")
    console.print(f"    Confidence: {val.confidence:.1%}")


def estimate_cost(num_images: int, model: str) -> float:
    """Rough cost estimate based on OpenAI pricing"""
    # Rough estimates - actual costs may vary
    cost_per_image = {
        "gpt-5": 0.20,
        "gpt-5-mini": 0.08,
        "gpt-4o": 0.15,
        "gpt-4o-mini": 0.05,
        "gpt-4-turbo": 0.12
    }
    return num_images * cost_per_image.get(model, 0.08)


async def process_all(config: Config):
    """Run the full processing pipeline"""
    pipeline = ComicValuationPipeline(config)
    results = await pipeline.process_all_images()
    pipeline.save_results(results)
    return results


async def analyze_single_image(config: Config, image_path: str):
    """Analyze a single image"""
    pipeline = ComicValuationPipeline(config)
    return await pipeline.process_single_file(image_path)


async def compare_single(config: Config, image_path: str):
    """Compare analysis from two models"""
    pipeline = ComicValuationPipeline(config)
    return await pipeline.compare_models(image_path)


if __name__ == "__main__":
    app()

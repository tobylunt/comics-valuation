import asyncio
import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import logging

from models import ComicValuation, ProcessingResult, BatchResults
from openai_provider import OpenAIComicAnalyzer, OpenAIComicComparator
from gemini_provider import GeminiComicAnalyzer, GeminiComicComparator
from config import Config

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ComicValuationPipeline:
    """Main pipeline for processing comic book images"""

    def __init__(self, config: Config):
        self.config = config

        # Initialize analyzer based on provider
        if config.provider == "openai":
            if not config.openai_api_key:
                raise ValueError("OpenAI API key required for OpenAI provider")
            self.analyzer = OpenAIComicAnalyzer(
                api_key=config.openai_api_key,
                model=config.primary_model
            )
            self.comparator = None
            if config.comparison_model:
                self.comparator = OpenAIComicComparator(
                    api_key=config.openai_api_key,
                    primary_model=config.primary_model,
                    secondary_model=config.comparison_model
                )

        elif config.provider == "gemini":
            if not config.gemini_api_key:
                raise ValueError("Gemini API key required for Gemini provider")
            self.analyzer = GeminiComicAnalyzer(
                api_key=config.gemini_api_key,
                model=config.primary_model
            )
            self.comparator = None
            if config.comparison_model:
                self.comparator = GeminiComicComparator(
                    api_key=config.gemini_api_key,
                    model=config.primary_model
                )

        else:
            raise ValueError(f"Unknown provider: {config.provider}")

    def get_image_files(self) -> List[Path]:
        """Get all supported image files from the configured directory"""
        image_dir = Path(self.config.images_directory)

        if not image_dir.exists():
            raise FileNotFoundError(f"Images directory not found: {image_dir}")

        image_files = []
        for ext in self.config.image_extensions:
            # Check both lowercase and uppercase extensions
            image_files.extend(image_dir.glob(f"*{ext}"))
            image_files.extend(image_dir.glob(f"*{ext.upper()}"))

        # Remove duplicates and sort
        image_files = sorted(set(image_files))

        logger.info(f"Found {len(image_files)} image files in {image_dir}")
        return image_files

    def _save_intermediate_result(self, result: ProcessingResult) -> None:
        """Save a single result immediately to disk"""
        output_dir = Path(self.config.output_directory) / "intermediate"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save as JSON with image filename
        filename = Path(result.image_filename).stem
        json_path = output_dir / f"{filename}.json"

        result_data = {
            "image_filename": result.image_filename,
            "success": result.success,
            "processing_time": result.processing_time,
            "error_message": result.error_message
        }

        if result.valuation:
            result_data["valuation"] = result.valuation.model_dump()

        with open(json_path, 'w') as f:
            json.dump(result_data, f, indent=2, default=str)

    async def process_single_image(self, image_path: Path, save_intermediate: bool = False) -> ProcessingResult:
        """Process a single image file"""
        start_time = time.time()

        try:
            logger.info(f"Processing {image_path.name}...")

            # Analyze with retry logic
            valuation = await self._analyze_with_retry(image_path)

            processing_time = time.time() - start_time
            logger.info(f"✓ Completed {image_path.name} in {processing_time:.1f}s")

            result = ProcessingResult(
                image_filename=image_path.name,
                success=True,
                valuation=valuation,
                processing_time=processing_time
            )

            # Save intermediate result if requested
            if save_intermediate:
                self._save_intermediate_result(result)

            return result

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"✗ Failed to process {image_path.name}: {e}")

            result = ProcessingResult(
                image_filename=image_path.name,
                success=False,
                error_message=str(e),
                processing_time=processing_time
            )

            # Save intermediate result even on failure
            if save_intermediate:
                self._save_intermediate_result(result)

            return result

    async def _analyze_with_retry(self, image_path: Path) -> ComicValuation:
        """Analyze image with retry logic"""
        last_error = None

        for attempt in range(self.config.retry_attempts):
            try:
                # Add metadata that the OpenAI provider might not set
                valuation = await self.analyzer.analyze_comic(str(image_path))

                # Ensure metadata is set correctly
                valuation.image_filename = image_path.name
                valuation.llm_provider = f"{self.config.provider}-{self.config.primary_model}"
                valuation.analysis_date = datetime.now().isoformat()

                return valuation

            except Exception as e:
                last_error = e
                if attempt < self.config.retry_attempts - 1:
                    wait_time = self.config.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Attempt {attempt + 1} failed for {image_path.name}: {e}")
                    logger.info(f"Retrying in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)

        raise last_error

    async def process_all_images(self) -> BatchResults:
        """Process all images in the configured directory"""
        batch_start = datetime.now()
        logger.info("Starting batch processing...")

        # Get all image files
        image_files = self.get_image_files()
        if not image_files:
            logger.warning("No image files found to process")
            return BatchResults(
                total_processed=0,
                successful=0,
                failed=0,
                results=[],
                batch_start_time=batch_start,
                batch_end_time=datetime.now(),
                total_processing_time=0.0
            )

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.config.max_concurrent)

        async def process_with_semaphore(image_path: Path) -> ProcessingResult:
            async with semaphore:
                return await self.process_single_image(image_path, save_intermediate=True)

        # Process all images
        logger.info(f"Processing {len(image_files)} images with max {self.config.max_concurrent} concurrent requests")

        tasks = [process_with_semaphore(img) for img in image_files]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Calculate statistics
        batch_end = datetime.now()
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_time = (batch_end - batch_start).total_seconds()

        logger.info(f"Batch processing complete!")
        logger.info(f"✓ Successful: {successful}/{len(results)}")
        logger.info(f"✗ Failed: {failed}/{len(results)}")
        logger.info(f"⏱ Total time: {total_time:.1f}s")

        return BatchResults(
            total_processed=len(results),
            successful=successful,
            failed=failed,
            results=results,
            batch_start_time=batch_start,
            batch_end_time=batch_end,
            total_processing_time=total_time
        )

    async def process_single_file(self, image_path: str) -> ProcessingResult:
        """Process a single image file by path"""
        image_file = Path(image_path)

        if not image_file.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        return await self.process_single_image(image_file)

    async def compare_models(self, image_path: str) -> tuple[ComicValuation, ComicValuation]:
        """Compare results from primary and comparison models"""
        if not self.comparator:
            raise ValueError("No comparison model configured")

        image_file = Path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        logger.info(f"Comparing models for {image_file.name}...")
        primary, secondary = await self.comparator.compare_analyses(str(image_file))

        return primary, secondary

    def save_results(self, batch_results: BatchResults) -> None:
        """Save results to configured output directory"""
        output_dir = Path(self.config.output_directory)
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self.config.save_json:
            json_path = output_dir / f"comic_valuations_{timestamp}.json"

            # Convert to serializable format
            results_data = {
                "metadata": {
                    "total_processed": batch_results.total_processed,
                    "successful": batch_results.successful,
                    "failed": batch_results.failed,
                    "batch_start_time": batch_results.batch_start_time.isoformat(),
                    "batch_end_time": batch_results.batch_end_time.isoformat(),
                    "total_processing_time": batch_results.total_processing_time
                },
                "results": []
            }

            for result in batch_results.results:
                result_data = {
                    "image_filename": result.image_filename,
                    "success": result.success,
                    "processing_time": result.processing_time,
                    "error_message": result.error_message
                }

                if result.valuation:
                    result_data["valuation"] = result.valuation.model_dump()

                results_data["results"].append(result_data)

            with open(json_path, 'w') as f:
                json.dump(results_data, f, indent=2, default=str)

            logger.info(f"Results saved to {json_path}")

        # CSV export
        if self.config.save_csv:
            csv_path = output_dir / f"comic_valuations_{timestamp}.csv"

            # Prepare CSV data - only successful results
            successful_results = [r for r in batch_results.results if r.success and r.valuation]

            if successful_results:
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)

                    # Header row
                    writer.writerow([
                        'Image Filename',
                        'Series',
                        'Title',
                        'Issue Number',
                        'Publisher',
                        'Publication Date',
                        'Grade',
                        'Key Issue',
                        'Key Issue Notes',
                        'Condition Notes',
                        'Rarity Notes',
                        'Low Estimate ($)',
                        'Best Estimate ($)',
                        'High Estimate ($)',
                        'Valuation Confidence',
                        'Identification Confidence',
                        'Analysis Notes',
                        'LLM Provider',
                        'Analysis Date',
                        'Processing Time (s)'
                    ])

                    # Data rows
                    for result in successful_results:
                        val = result.valuation
                        writer.writerow([
                            result.image_filename,
                            val.series,
                            val.title,
                            val.issue_number,
                            val.publisher,
                            val.publication_date,
                            val.estimated_grade,
                            'Yes' if val.key_issue else 'No',
                            val.key_issue_notes,
                            '; '.join(val.condition_notes) if val.condition_notes else '',
                            val.rarity_notes,
                            f"{val.valuation.low_estimate:.2f}",
                            f"{val.valuation.best_estimate:.2f}",
                            f"{val.valuation.high_estimate:.2f}",
                            f"{val.valuation.confidence:.2f}",
                            f"{val.identification_confidence:.2f}",
                            val.analysis_notes,
                            val.llm_provider,
                            val.analysis_date,
                            f"{result.processing_time:.1f}"
                        ])

                logger.info(f"CSV saved to {csv_path}")
            else:
                logger.warning("No successful results to export to CSV")


# Convenience function for simple usage
async def analyze_comics(images_dir: str, openai_api_key: str, model: str = "gpt-5-mini") -> BatchResults:
    """Simple function to analyze all comics in a directory"""
    from config import Config

    config = Config(
        images_directory=images_dir,
        openai_api_key=openai_api_key,
        primary_model=model
    )

    pipeline = ComicValuationPipeline(config)
    return await pipeline.process_all_images()

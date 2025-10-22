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

        try:
            with open(json_path, 'w') as f:
                json.dump(result_data, f, indent=2, default=str)
            logger.debug(f"Saved intermediate result to {json_path}")
        except Exception as e:
            logger.error(f"Failed to save intermediate result for {result.image_filename}: {e}")

    async def process_single_image(self, image_path: Path, save_intermediate: bool = False, skip_existing: bool = True) -> ProcessingResult:
        """Process a single image file"""
        start_time = time.time()

        # Check if we already have an intermediate result for this image
        if skip_existing and save_intermediate:
            output_dir = Path(self.config.output_directory) / "intermediate"
            filename = Path(image_path).stem
            json_path = output_dir / f"{filename}.json"

            if json_path.exists():
                try:
                    with open(json_path, 'r') as f:
                        existing_data = json.load(f)

                    # Check if this was a successful processing
                    if existing_data.get('success'):
                        logger.info(f"⊙ Skipping {image_path.name} (already completed successfully)")

                        # Reconstruct the valuation if present
                        valuation = None
                        if 'valuation' in existing_data and existing_data['valuation']:
                            try:
                                valuation = ComicValuation(**existing_data['valuation'])
                            except Exception as e:
                                logger.warning(f"Could not reconstruct valuation for {image_path.name}: {e}")

                        return ProcessingResult(
                            image_filename=existing_data.get('image_filename', image_path.name),
                            success=True,
                            valuation=valuation,
                            processing_time=existing_data.get('processing_time', 0.0),
                            error_message=None
                        )
                    else:
                        # Check if this was a known error that we should skip
                        error_msg = existing_data.get('error_message', '').strip()

                        # List of errors that indicate we should retry
                        retryable_errors = [
                            "could not convert string to float: ''",
                            "timeout",
                            "rate limit",
                            "connection error"
                        ]

                        should_retry = any(err in error_msg.lower() for err in retryable_errors) if error_msg else True

                        if should_retry:
                            logger.info(f"⟳ Retrying {image_path.name} (previous error: {error_msg or 'unknown'})")
                        else:
                            logger.info(f"⊗ Skipping {image_path.name} (permanent error: {error_msg})")
                            return ProcessingResult(
                                image_filename=existing_data.get('image_filename', image_path.name),
                                success=False,
                                valuation=None,
                                processing_time=existing_data.get('processing_time', 0.0),
                                error_message=error_msg
                            )

                except json.JSONDecodeError as e:
                    logger.warning(f"Corrupted JSON for {image_path.name}: {e}. Will reprocess.")
                except Exception as e:
                    logger.warning(f"Could not load existing result for {image_path.name}: {e}. Will reprocess.")

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

        # Check for existing intermediate results
        output_dir = Path(self.config.output_directory) / "intermediate"
        if output_dir.exists():
            existing_count = len(list(output_dir.glob("*.json")))
            logger.info(f"Found {existing_count} existing intermediate results")

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.config.max_concurrent)

        async def process_with_semaphore(image_path: Path) -> ProcessingResult:
            async with semaphore:
                return await self.process_single_image(image_path, save_intermediate=True, skip_existing=True)

        # Process all images
        logger.info(f"Processing {len(image_files)} images with max {self.config.max_concurrent} concurrent requests")

        tasks = [process_with_semaphore(img) for img in image_files]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Calculate statistics
        batch_end = datetime.now()
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_time = (batch_end - batch_start).total_seconds()

        # Count skipped vs newly processed
        newly_processed = sum(1 for r in results if r.processing_time > 0)
        skipped = len(results) - newly_processed

        logger.info(f"Batch processing complete!")
        logger.info(f"✓ Successful: {successful}/{len(results)}")
        logger.info(f"✗ Failed: {failed}/{len(results)}")
        if skipped > 0:
            logger.info(f"⊙ Skipped (already processed): {skipped}")
            logger.info(f"🆕 Newly processed: {newly_processed}")
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
                        'Processing Time (s)',
                        'Grounding Used',
                        'Search Queries',
                        'Source URLs'
                    ])

                    # Data rows
                    for result in successful_results:
                        val = result.valuation

                        # Extract grounding metadata if available
                        grounding_used = 'No'
                        search_queries = ''
                        source_urls = ''

                        if val.grounding_metadata:
                            grounding_used = 'Yes' if val.grounding_metadata.get('grounding_used') else 'No'

                            # Format search queries
                            queries = val.grounding_metadata.get('search_queries', [])
                            search_queries = ' | '.join(queries) if queries else ''

                            # Format source URLs
                            sources = val.grounding_metadata.get('sources', [])
                            if sources:
                                url_list = [f"{s.get('title', 'Unknown')}: {s.get('url', 'N/A')}" for s in sources]
                                source_urls = ' | '.join(url_list)

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
                            f"{result.processing_time:.1f}",
                            grounding_used,
                            search_queries,
                            source_urls
                        ])

                logger.info(f"CSV saved to {csv_path}")
            else:
                logger.warning("No successful results to export to CSV")


    def get_intermediate_status(self) -> dict:
        """Get status of intermediate results"""
        output_dir = Path(self.config.output_directory) / "intermediate"

        if not output_dir.exists():
            return {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "corrupted": 0,
                "details": []
            }

        status = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "corrupted": 0,
            "details": []
        }

        for json_path in output_dir.glob("*.json"):
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)

                status["total"] += 1

                detail = {
                    "filename": json_path.name,
                    "image": data.get("image_filename", "unknown"),
                    "success": data.get("success", False),
                    "error": data.get("error_message", None),
                    "has_valuation": "valuation" in data and data["valuation"] is not None
                }

                if data.get("success"):
                    status["successful"] += 1
                else:
                    status["failed"] += 1

                status["details"].append(detail)

            except json.JSONDecodeError:
                status["corrupted"] += 1
                status["details"].append({
                    "filename": json_path.name,
                    "image": "unknown",
                    "success": False,
                    "error": "Corrupted JSON",
                    "has_valuation": False
                })
            except Exception as e:
                status["corrupted"] += 1
                status["details"].append({
                    "filename": json_path.name,
                    "image": "unknown",
                    "success": False,
                    "error": str(e),
                    "has_valuation": False
                })

        return status

    def clean_intermediate_results(self, remove_failed: bool = False, remove_corrupted: bool = True) -> dict:
        """Clean up intermediate results

        Args:
            remove_failed: Remove results where success=False
            remove_corrupted: Remove corrupted JSON files

        Returns:
            Dictionary with cleanup statistics
        """
        output_dir = Path(self.config.output_directory) / "intermediate"

        if not output_dir.exists():
            return {"removed": 0, "failed": [], "corrupted": []}

        removed_count = 0
        failed_removed = []
        corrupted_removed = []

        for json_path in output_dir.glob("*.json"):
            should_remove = False

            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)

                # Check if this is a failed result we should remove
                if remove_failed and not data.get("success", False):
                    # Check for specific errors that might be retryable
                    error_msg = data.get("error_message", "").strip()
                    retryable_errors = [
                        "could not convert string to float: ''",
                        "timeout",
                        "rate limit",
                        "connection error"
                    ]

                    is_retryable = any(err in error_msg.lower() for err in retryable_errors) if error_msg else True

                    if is_retryable:
                        should_remove = True
                        failed_removed.append(json_path.name)

            except (json.JSONDecodeError, Exception):
                if remove_corrupted:
                    should_remove = True
                    corrupted_removed.append(json_path.name)

            if should_remove:
                try:
                    json_path.unlink()
                    removed_count += 1
                    logger.info(f"Removed intermediate result: {json_path.name}")
                except Exception as e:
                    logger.error(f"Failed to remove {json_path.name}: {e}")

        return {
            "removed": removed_count,
            "failed": failed_removed,
            "corrupted": corrupted_removed
        }

    def validate_intermediate_results(self) -> dict:
        """Validate all intermediate results and check for issues"""
        output_dir = Path(self.config.output_directory) / "intermediate"

        if not output_dir.exists():
            return {"valid": 0, "invalid": 0, "issues": []}

        valid_count = 0
        invalid_count = 0
        issues = []

        for json_path in output_dir.glob("*.json"):
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)

                # Check required fields
                required_fields = ["image_filename", "success", "processing_time"]
                missing_fields = [field for field in required_fields if field not in data]

                if missing_fields:
                    invalid_count += 1
                    issues.append({
                        "file": json_path.name,
                        "issue": f"Missing fields: {', '.join(missing_fields)}"
                    })
                elif data.get("success") and "valuation" in data:
                    # Try to validate the valuation structure
                    try:
                        if data["valuation"]:
                            ComicValuation(**data["valuation"])
                        valid_count += 1
                    except Exception as e:
                        invalid_count += 1
                        issues.append({
                            "file": json_path.name,
                            "issue": f"Invalid valuation structure: {str(e)}"
                        })
                elif data.get("success") and "valuation" not in data:
                    invalid_count += 1
                    issues.append({
                        "file": json_path.name,
                        "issue": "Success=True but no valuation present"
                    })
                elif not data.get("success") and not data.get("error_message"):
                    invalid_count += 1
                    issues.append({
                        "file": json_path.name,
                        "issue": "Success=False but no error message"
                    })
                else:
                    valid_count += 1

            except json.JSONDecodeError as e:
                invalid_count += 1
                issues.append({
                    "file": json_path.name,
                    "issue": f"Corrupted JSON: {str(e)}"
                })
            except Exception as e:
                invalid_count += 1
                issues.append({
                    "file": json_path.name,
                    "issue": f"Unexpected error: {str(e)}"
                })

        return {
            "valid": valid_count,
            "invalid": invalid_count,
            "issues": issues
        }


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

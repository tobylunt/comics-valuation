#!/usr/bin/env python3
"""
Unit tests for resumable processing functionality.
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime

from models import ComicValuation, ValuationEstimate, ProcessingResult, BatchResults, ConditionGrade
from pipeline import ComicValuationPipeline
from config import Config


class TestResumableProcessing(unittest.TestCase):
    """Test resumable processing features"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temporary directories
        self.temp_dir = tempfile.mkdtemp()
        self.images_dir = Path(self.temp_dir) / "images"
        self.output_dir = Path(self.temp_dir) / "results"
        self.intermediate_dir = self.output_dir / "intermediate"

        self.images_dir.mkdir(parents=True)
        self.output_dir.mkdir(parents=True)
        self.intermediate_dir.mkdir(parents=True)

        # Create test config
        self.config = Config(
            images_directory=str(self.images_dir),
            output_directory=str(self.output_dir),
            provider="openai",
            openai_api_key="test-key",
            primary_model="gpt-4o-mini",
            max_concurrent=2,
            retry_attempts=2,
            retry_delay=0.1
        )

        # Create test images
        self.test_images = []
        for i in range(5):
            img_path = self.images_dir / f"comic_{i:03d}.jpg"
            img_path.touch()
            self.test_images.append(img_path)

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_test_valuation(self, image_filename: str) -> ComicValuation:
        """Create a test ComicValuation object"""
        return ComicValuation(
            series="Test Series",
            title="Test Title",
            issue_number="1",
            publisher="Test Publisher",
            publication_date="2024-01",
            estimated_grade=ConditionGrade.NEAR_MINT,
            condition_notes=[],
            key_issue=False,
            key_issue_notes="Not a key issue",
            rarity_notes="Common",
            valuation=ValuationEstimate(
                low_estimate=10.0,
                best_estimate=15.0,
                high_estimate=20.0,
                confidence=0.8
            ),
            image_filename=image_filename,
            analysis_date=datetime.now().isoformat(),
            llm_provider="openai-gpt-4o-mini",
            identification_confidence=0.9,
            analysis_notes="Test notes"
        )

    def create_intermediate_result(self, image_name: str, success: bool = True, error: str = None):
        """Create an intermediate result JSON file"""
        result_data = {
            "image_filename": image_name,
            "success": success,
            "processing_time": 1.23,
            "error_message": error
        }

        if success:
            valuation = self.create_test_valuation(image_name)
            result_data["valuation"] = valuation.model_dump()

        filename = Path(image_name).stem
        json_path = self.intermediate_dir / f"{filename}.json"

        with open(json_path, 'w') as f:
            json.dump(result_data, f, indent=2, default=str)

        return json_path

    def test_get_intermediate_status(self):
        """Test getting status of intermediate results"""
        # Create some intermediate results
        self.create_intermediate_result("comic_001.jpg", success=True)
        self.create_intermediate_result("comic_002.jpg", success=False, error="Test error")

        # Create a corrupted JSON file
        corrupted_path = self.intermediate_dir / "comic_003.json"
        with open(corrupted_path, 'w') as f:
            f.write("{invalid json}")

        # Test status retrieval
        with patch('pipeline.OpenAIComicAnalyzer'):
            pipeline = ComicValuationPipeline(self.config)
            status = pipeline.get_intermediate_status()

        self.assertEqual(status["total"], 3)
        self.assertEqual(status["successful"], 1)
        self.assertEqual(status["failed"], 1)
        self.assertEqual(status["corrupted"], 1)
        self.assertEqual(len(status["details"]), 3)

    def test_skip_existing_successful(self):
        """Test that successfully processed images are skipped"""
        # Create a successful intermediate result
        self.create_intermediate_result("comic_000.jpg", success=True)

        with patch('pipeline.OpenAIComicAnalyzer') as mock_analyzer:
            pipeline = ComicValuationPipeline(self.config)

            # Process the image that already has a result
            result = asyncio.run(pipeline.process_single_image(
                self.test_images[0],
                save_intermediate=True,
                skip_existing=True
            ))

        # Should skip and not call the analyzer
        self.assertTrue(result.success)
        self.assertEqual(result.image_filename, "comic_000.jpg")
        mock_analyzer.return_value.analyze_comic.assert_not_called()

    def test_retry_failed_with_retryable_error(self):
        """Test that failed results with retryable errors are retried"""
        # Create a failed result with retryable error
        self.create_intermediate_result(
            "comic_000.jpg",
            success=False,
            error="could not convert string to float: ''"
        )

        with patch('pipeline.OpenAIComicAnalyzer') as mock_analyzer:
            mock_valuation = self.create_test_valuation("comic_000.jpg")
            mock_analyzer.return_value.analyze_comic = AsyncMock(return_value=mock_valuation)

            pipeline = ComicValuationPipeline(self.config)

            # Process should retry the failed image
            result = asyncio.run(pipeline.process_single_image(
                self.test_images[0],
                save_intermediate=True,
                skip_existing=True
            ))

        # Should retry and call the analyzer
        self.assertTrue(result.success)
        mock_analyzer.return_value.analyze_comic.assert_called_once()

    def test_skip_failed_with_permanent_error(self):
        """Test that failed results with permanent errors are skipped"""
        # Create a failed result with permanent error
        self.create_intermediate_result(
            "comic_000.jpg",
            success=False,
            error="Invalid API key"
        )

        with patch('pipeline.OpenAIComicAnalyzer') as mock_analyzer:
            pipeline = ComicValuationPipeline(self.config)

            # Process should skip the permanently failed image
            result = asyncio.run(pipeline.process_single_image(
                self.test_images[0],
                save_intermediate=True,
                skip_existing=True
            ))

        # Should skip and not retry
        self.assertFalse(result.success)
        self.assertEqual(result.error_message, "Invalid API key")
        mock_analyzer.return_value.analyze_comic.assert_not_called()

    def test_clean_intermediate_results(self):
        """Test cleaning intermediate results"""
        # Create various results
        self.create_intermediate_result("comic_001.jpg", success=True)
        self.create_intermediate_result("comic_002.jpg", success=False, error="timeout")
        self.create_intermediate_result("comic_003.jpg", success=False, error="Invalid image")

        # Create corrupted file
        corrupted_path = self.intermediate_dir / "comic_004.json"
        with open(corrupted_path, 'w') as f:
            f.write("{corrupted}")

        with patch('pipeline.OpenAIComicAnalyzer'):
            pipeline = ComicValuationPipeline(self.config)

            # Clean only corrupted
            result = pipeline.clean_intermediate_results(
                remove_failed=False,
                remove_corrupted=True
            )

        self.assertEqual(result["removed"], 1)
        self.assertEqual(len(result["corrupted"]), 1)
        self.assertEqual(len(result["failed"]), 0)

        # Clean retryable failures
        with patch('pipeline.OpenAIComicAnalyzer'):
            pipeline = ComicValuationPipeline(self.config)

            result = pipeline.clean_intermediate_results(
                remove_failed=True,
                remove_corrupted=False
            )

        self.assertEqual(result["removed"], 1)  # Only "timeout" error
        self.assertEqual(len(result["failed"]), 1)

    def test_validate_intermediate_results(self):
        """Test validation of intermediate results"""
        # Create valid result
        self.create_intermediate_result("comic_001.jpg", success=True)

        # Create result missing valuation
        invalid_data = {
            "image_filename": "comic_002.jpg",
            "success": True,
            "processing_time": 1.0
            # Missing valuation!
        }
        with open(self.intermediate_dir / "comic_002.json", 'w') as f:
            json.dump(invalid_data, f)

        # Create result missing error message
        invalid_data2 = {
            "image_filename": "comic_003.jpg",
            "success": False,
            "processing_time": 1.0
            # Missing error_message!
        }
        with open(self.intermediate_dir / "comic_003.json", 'w') as f:
            json.dump(invalid_data2, f)

        with patch('pipeline.OpenAIComicAnalyzer'):
            pipeline = ComicValuationPipeline(self.config)
            validation = pipeline.validate_intermediate_results()

        self.assertEqual(validation["valid"], 1)
        self.assertEqual(validation["invalid"], 2)
        self.assertEqual(len(validation["issues"]), 2)

    def test_save_intermediate_result(self):
        """Test saving intermediate results"""
        with patch('pipeline.OpenAIComicAnalyzer'):
            pipeline = ComicValuationPipeline(self.config)

            # Test successful result
            valuation = self.create_test_valuation("test.jpg")
            result = ProcessingResult(
                image_filename="test.jpg",
                success=True,
                valuation=valuation,
                processing_time=1.5
            )

            pipeline._save_intermediate_result(result)

        # Check saved file
        json_path = self.intermediate_dir / "test.json"
        self.assertTrue(json_path.exists())

        with open(json_path, 'r') as f:
            data = json.load(f)

        self.assertEqual(data["image_filename"], "test.jpg")
        self.assertTrue(data["success"])
        self.assertEqual(data["processing_time"], 1.5)
        self.assertIn("valuation", data)

    def test_handle_corrupted_json(self):
        """Test handling of corrupted JSON files"""
        # Create corrupted file
        corrupted_path = self.intermediate_dir / "comic_000.json"
        with open(corrupted_path, 'w') as f:
            f.write("not valid json at all")

        with patch('pipeline.OpenAIComicAnalyzer') as mock_analyzer:
            mock_valuation = self.create_test_valuation("comic_000.jpg")
            mock_analyzer.return_value.analyze_comic = AsyncMock(return_value=mock_valuation)

            pipeline = ComicValuationPipeline(self.config)

            # Should reprocess corrupted file
            result = asyncio.run(pipeline.process_single_image(
                self.test_images[0],
                save_intermediate=True,
                skip_existing=True
            ))

        # Should reprocess
        self.assertTrue(result.success)
        mock_analyzer.return_value.analyze_comic.assert_called_once()

    @patch('pipeline.logger')
    def test_logging_output(self, mock_logger):
        """Test that appropriate logging messages are generated"""
        # Create existing successful result
        self.create_intermediate_result("comic_000.jpg", success=True)

        with patch('pipeline.OpenAIComicAnalyzer'):
            pipeline = ComicValuationPipeline(self.config)

            # Process with skip
            asyncio.run(pipeline.process_single_image(
                self.test_images[0],
                save_intermediate=True,
                skip_existing=True
            ))

        # Check for skip message
        mock_logger.info.assert_any_call("⊙ Skipping comic_000.jpg (already completed successfully)")

    def test_batch_processing_with_resume(self):
        """Test batch processing with some already completed"""
        # Create some existing results
        self.create_intermediate_result("comic_000.jpg", success=True)
        self.create_intermediate_result("comic_001.jpg", success=False, error="timeout")

        with patch('pipeline.OpenAIComicAnalyzer') as mock_analyzer:
            mock_valuation = self.create_test_valuation("test.jpg")
            mock_analyzer.return_value.analyze_comic = AsyncMock(return_value=mock_valuation)

            pipeline = ComicValuationPipeline(self.config)

            # Process all
            results = asyncio.run(pipeline.process_all_images())

        # Should skip 1, retry 1, process 3 new ones
        self.assertEqual(results.total_processed, 5)
        # One was already successful, and we retry the rest
        self.assertEqual(mock_analyzer.return_value.analyze_comic.call_count, 4)


class TestErrorCategories(unittest.TestCase):
    """Test error categorization logic"""

    def test_retryable_errors(self):
        """Test identification of retryable errors"""
        retryable = [
            "could not convert string to float: ''",
            "Request timeout",
            "Rate limit exceeded",
            "Connection error: refused"
        ]

        permanent = [
            "Invalid API key",
            "Image format not supported",
            "File not found",
            "Permission denied"
        ]

        for error in retryable:
            # These should be identified as retryable
            retryable_patterns = ["could not convert string to float: ''", "timeout", "rate limit", "connection error"]
            is_retryable = any(pattern in error.lower() for pattern in retryable_patterns)
            self.assertTrue(is_retryable, f"{error} should be retryable")

        for error in permanent:
            retryable_patterns = ["could not convert string to float: ''", "timeout", "rate limit", "connection error"]
            is_retryable = any(pattern in error.lower() for pattern in retryable_patterns)
            self.assertFalse(is_retryable, f"{error} should be permanent")


if __name__ == "__main__":
    unittest.main()

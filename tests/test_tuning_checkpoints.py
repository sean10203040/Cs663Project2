import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from model_dev.tune_gemini import main


class CheckpointSubmissionTests(unittest.TestCase):
    def test_two_epochs_export_intermediate_checkpoints_and_save_job(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "job.json"
            job = Mock()
            job.model_dump.return_value = {"name": "projects/fixture/locations/us/tuningJobs/123", "state": "JOB_STATE_PENDING"}
            client = Mock()
            client.tunings.tune.return_value = job
            args = ["tune", "--project", "fixture", "--train-uri", "gs://fixture/train.jsonl", "--validation-uri", "gs://fixture/validation.jsonl", "--epochs", "2", "--export-intermediate-checkpoints", "--output", str(output)]
            with patch("sys.argv", args), patch("google.genai.Client", return_value=client), contextlib.redirect_stdout(io.StringIO()):
                main()
            client.tunings.tune.assert_called_once()
            config = client.tunings.tune.call_args.kwargs["config"]
            self.assertEqual(config.epoch_count, 2)
            self.assertFalse(config.export_last_checkpoint_only)
            self.assertEqual(json.loads(output.read_text())["name"], job.model_dump.return_value["name"])
            client.close.assert_called_once()

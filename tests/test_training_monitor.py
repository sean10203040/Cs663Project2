import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch
from google.auth.exceptions import TransportError,RefreshError
from model_dev.watch_product_run import watch


class MonitorTests(unittest.TestCase):
    def setup_monitor(self, root):
        path=root/"job.json";path.write_text(json.dumps({"name":"projects/fixture/locations/us/tuningJobs/one","state":"JOB_STATE_RUNNING"}))
        client=MagicMock();client.__enter__.return_value=client
        credentials=SimpleNamespace(valid=True)
        return path,client,credentials

    def test_temporary_network_failure_retries_only_the_read(self):
        with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()) as output:
            path,client,credentials=self.setup_monitor(Path(directory))
            data={"name":"projects/fixture/locations/us/tuningJobs/one","state":"JOB_STATE_SUCCEEDED","tuned_model":{"endpoint":"projects/fixture/locations/us/endpoints/model"}}
            job=MagicMock();job.model_dump.return_value=data
            client.tunings.get.side_effect=[TransportError("network unavailable"),job]
            with patch("model_dev.watch_product_run.genai.Client",return_value=client),patch("model_dev.watch_product_run.google.auth.default",return_value=(credentials,"fixture")),patch("model_dev.watch_product_run.time.sleep") as sleep:
                result=watch(path,"fixture",30)
            self.assertEqual(result["state"],"JOB_STATE_SUCCEEDED")
            self.assertEqual(client.tunings.get.call_count,2)
            client.tunings.tune.assert_not_called();client.tunings.cancel.assert_not_called()
            sleep.assert_called_once_with(30)
            self.assertEqual(json.loads(path.read_text())["state"],"JOB_STATE_SUCCEEDED")
            self.assertIn("Retrying",output.getvalue())

    def test_expired_sign_in_stops_monitor_without_changing_saved_job(self):
        with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()):
            path,client,credentials=self.setup_monitor(Path(directory))
            client.tunings.get.side_effect=RefreshError("reauthentication needed")
            with patch("model_dev.watch_product_run.genai.Client",return_value=client),patch("model_dev.watch_product_run.google.auth.default",return_value=(credentials,"fixture")):
                result=watch(path,"fixture",30)
            self.assertEqual(result["monitor_error"],"authentication")
            self.assertEqual(json.loads(path.read_text())["state"],"JOB_STATE_RUNNING")
            client.tunings.tune.assert_not_called();client.tunings.cancel.assert_not_called()

import os
import subprocess
import tempfile
import requests
import warcprox.warcprox as warcprox
import thread
import errno
from socket import error as socket_error

from celery import Celery
from celery.utils.log import get_task_logger


### CELERY SETUP ###

app = Celery()
app.config_from_object('celeryconfig')

logger = get_task_logger(__name__)

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

SCRIPT_PATH = os.environ.get('WARC_CREATOR_SCRIPT_PATH', os.path.join(__location__, 'simple_capture.js'))


### HELPERS ###

class ConfigError(Exception):
    pass


### TASKS ###

@app.task
def proxy_capture(target_url, callback_url, extra_info='', script_path=SCRIPT_PATH):
    """
        Start proxy, call PhantomJS with a javascript file to load requested url, send WARC file to callback_url.
    """
    # set up paths
    storage_path = tempfile.mkdtemp()
    cert_path = os.path.join(storage_path, 'cert.pem')

    if not script_path:
        raise ConfigError("Script path is not set (did you set WARC_CREATOR_SCRIPT_PATH env variable?)")

    # connect warcprox to an open port
    warcprox_port = 27500
    warcprox_url_queue = warcprox.queue.Queue()
    for i in xrange(500):
        try:
            proxy = warcprox.WarcProxy(
                server_address=("127.0.0.1", warcprox_port),
                ca=warcprox.CertificateAuthority(cert_path, storage_path),
                recorded_url_q=warcprox_url_queue
            )
            break
        except socket_error as e:
            if e.errno != errno.EADDRINUSE:
                raise
        warcprox_port += 1
    else:
        raise Exception("WarcProx couldn't find an open port.")

    # create a WarcWriterThread subclass that knows how to send warc file to callback_url after closing proxy
    class WarcWriter(warcprox.WarcWriterThread):
        def _close_writer(self):
            if self._fpath:
                super(WarcWriter, self)._close_writer()
                warc_file_path = os.path.join(storage_path, self._f_finalname)
                callback_params = {'type':'warc'}
                try:
                    with open(warc_file_path, 'rb') as warc_file:
                        requests.post(callback_url, params=callback_params, files={'file':warc_file})
                except OSError:
                    logger.warning("Web Archive File creation failed for %s" % target_url)
                    callback_params['error'] = 1
                    requests.get(callback_url, params=callback_params)
                os.rmdir(storage_path)

    # start warcprox listener
    warc_writer = WarcWriter(recorded_url_q=warcprox_url_queue,
                             directory=storage_path, gzip=True,
                             port=warcprox_port,
                             rollover_idle_time=15)
    warcprox_controller = warcprox.WarcproxController(proxy, warc_writer)
    thread.start_new_thread(warcprox_controller.run_until_shutdown, ())

    # run phantomjs
    try:
        subprocess.call([
            'phantomjs',
            "--proxy=127.0.0.1:%s" % warcprox_port,
            "--ssl-certificates-path=%s" % cert_path,
            "--ignore-ssl-errors=true",
            script_path,
            target_url,
            storage_path,
            callback_url,
            extra_info
        ])
        #time.sleep(.5)  # give warcprox a chance to save everything
    finally:
        # shutdown warcprox process
        warcprox_controller.stop.set()

import os
import tempfile
import requests
from selenium import webdriver
import time
import warcprox.warcprox as warcprox
import thread
import errno
from socket import error as socket_error

from celery import Celery
from celery.utils.log import get_task_logger


### CELERY SETUP ###

app = Celery()

logger = get_task_logger(__name__)

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

SCRIPT_PATH = os.environ.get('WARC_CREATOR_SCRIPT_PATH', os.path.join(__location__, 'simple_capture.js'))


### HELPERS ###

class ConfigError(Exception):
    pass

def send_result(url, params, file_path=None):
    if file_path:
        with open(file_path, 'rb') as f:
            resp = requests.post(url, params=params, files={'file': f})
            print resp, dir(resp), resp.content, resp.text
    else:
        requests.post(url, params=params)


### TASKS ###

@app.task
def proxy_capture(target_url, callback_url, user_agent='Perma', script_path=SCRIPT_PATH):
    """
        Start proxy, call PhantomJS with a javascript file to load requested url, send WARC file to callback_url.
    """
    # set up paths
    storage_path = tempfile.mkdtemp()
    print "Saving to", storage_path
    image_path = os.path.join(storage_path, 'cap.png')
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
                warc_path = os.path.join(storage_path, self._f_finalname)
                try:
                    send_result(callback_url, {'type':'warc'}, warc_path)
                except OSError:
                    logger.warning("Web Archive File creation failed for %s" % target_url)
                    send_result(callback_url, {'type': 'warc', 'error':1})
                #os.rmdir(storage_path)

    # start warcprox listener
    warc_writer = WarcWriter(recorded_url_q=warcprox_url_queue,
                             directory=storage_path, gzip=True,
                             port=warcprox_port,
                             rollover_idle_time=15)
    warcprox_controller = warcprox.WarcproxController(proxy, warc_writer)
    thread.start_new_thread(warcprox_controller.run_until_shutdown, ())

    try:

        # run selenium/phantomjs
        from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
        desired_capabilities = dict(DesiredCapabilities.PHANTOMJS)
        desired_capabilities["phantomjs.page.settings.userAgent"] = user_agent
        driver = webdriver.PhantomJS(desired_capabilities=desired_capabilities,
                                     service_args=[
                                         "--proxy=127.0.0.1:%s" % warcprox_port,
                                         "--ssl-certificates-path=%s" % cert_path,
                                         "--ignore-ssl-errors=true",
                                     ])

        driver.set_window_size(1024, 800)
        print "Getting", target_url
        driver.get(target_url) # returns after onload
        time.sleep(.8) # finish rendering
        driver.save_screenshot(image_path)
        driver.quit()

        send_result(callback_url, {'type': 'image'}, image_path)



        #     subprocess.call([
        #         'node',
        #         script_path,
        #         "--proxy=127.0.0.1:%s;--ssl-certificates-path=%s;--ignore-ssl-errors=true" % warcprox_port,
        #         "" % cert_path,
        #         "",
        #         target_url,
        #         storage_path,
        #         callback_url,
        #         extra_info
        #     ])
        #     #time.sleep(.5)  # give warcprox a chance to save everything
    finally:
        # shutdown warcprox process
        warcprox_controller.stop.set()

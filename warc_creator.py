import json
from urlparse import parse_qs

from .celery import proxy_capture


def application(environ, start_response):

    # read query string
    d = parse_qs(environ['QUERY_STRING'])
    target_url = d.get('target_url', [''])[0]
    callback_url = d.get('callback_url', [''])[0]
    extra_info = d.get('extra_info', [''])[0]

    # send task
    proxy_capture.delay(target_url, callback_url, extra_info)

    # return response
    response_body = json.dumps({'success':1})
    response_headers = [('Content-Type', "application/json"),
                  ('Content-Length', str(len(response_body)))]
    start_response('202 Accepted', response_headers)
    return [response_body]

Warc Creator
=====

Warc Creator is a simple web server to asynchronously archive web pages and post them to a callback URL.

## Install ##

Install PhantomJS.

Install warc_creator:

    pip install warc_creator

## Quick Start ##

Start web server:

    gunicorn -b '127.0.0.1:8001' warc_creator

Start celery:

    celery --app=warc_creator worker

Begin warc-creation job:

    curl http://127.0.0.1:8001/target_url=http://example.com&callback_url=http://127.0.0.1/handle_warc&user_agent=foo
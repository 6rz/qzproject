#!/bin/sh

uwsgi --http :8092 --file ./app.py  --callable app  --master --processes 1 --threads 2 --stats 127.0.0.1:9292 &
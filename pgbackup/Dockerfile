FROM alpine:3.20

RUN apk add --no-cache postgresql16-client tzdata bash

COPY crontab /etc/crontabs/root
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
